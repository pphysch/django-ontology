from functools import cached_property
import logging
from django.conf import settings
from django.db import IntegrityError, models
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.dispatch import receiver

# Create your models here.

logger = logging.getLogger(__name__)

class ComponentModel(models.Model):
    """
    Abstract class that overrides the default `id` primary key with a OneToOne field to the Entity table called `entity_id`.

    Therefore, all ComponentModel subclasses share a global entity ID space, enabling fast and powerful new behaviors.

    Additionally, ComponentModel subclasses are soft-deleted by default, and "deleted" objects are excluded from the default Manager.
    To permanently remove a ComponentModel and its Entity from the database, specify `obj.delete(hard_delete=True)`.

    Otherwise, this ComponentModel behaves like any other base Model subclass.
    """
    class Meta:
        abstract = True

    class QuerySet(models.QuerySet):
        def cast(self, model: "ComponentModel"):
            """
            Casts the objects to the specified model, assuming they share an `entity_id`.
            """
            return model.objects.filter(entity_id=self.entity_id)

        def with_attr(self, domain, key, value):
            """
            Include only entities with the specified Attribute.
            """
            if isinstance(domain, str):
                domain = Domain.objects.get(slug=domain)

            return self.filter(entity__attrs__domain=domain, entity__attrs__key=key, entity__attrs__value=value)

        def delete(self, hard_delete=False):
            if hard_delete:
                Entity.objects_archive.filter(pk__in=self).delete(hard_delete=hard_delete)
                return super().delete()
            else:
                self.update(deleted=True)
                Entity.objects_archive.filter(pk__in=self).update(deleted_time=timezone.now())

        def undelete(self):
            """
            Reverses the soft-deletion of objects in the queryset.
            
            Note that the default `objects` manager won't select soft-deleted objects, so make sure to use the `objects_archive` manager instead.
            """
            with transaction.atomic():
                self.update(deleted=False)
                Entity.objects_archive.filter(pk__in=self).update(deleted_time=None)

    class ArchiveManager(models.Manager.from_queryset(QuerySet)):
        use_in_migrations = False  # Not worth the hassle/footguns

    class Manager(ArchiveManager):
        def get_queryset(self):
            return super().get_queryset().exclude(deleted=True)

    objects = Manager()
    objects_archive = ArchiveManager()

    entity = models.OneToOneField(
        "ontology.Entity",
        on_delete=models.CASCADE,
        primary_key=True,
        editable=False,
    )
    deleted = models.BooleanField(
        default=False,
        editable=False,
        db_index=True,
        help_text="True indicates the component has been soft-deleted and won't appear in most queries."
    )

    def cast(self, model: "ComponentModel"):
        """
        Casts the object to the specified model, assuming they share an `entity_id`.
        """
        return model.objects.get(entity=self.entity)

    @cached_property
    def content_type(self):
        return ContentType.objects.get_for_model(type(self))

    def add_to_domain(self, domain):
        """
        Add this entity to the specified domain.
        """
        if isinstance(domain, str):
            domain = Domain.objects.get(slug=domain)

        return self.entity.domains.add(domain)

    def is_in_domain(self, domain, recursive=False):
        """
        Check whether this entity is in the specified domain.

        If `recursive=True`, recursively check all subdomains.
        """
        try:
            if isinstance(domain, str):
                domain = Domain.objects.get(slug=domain)
            elif isinstance(domain, int):
                domain = Domain.objects.get(pk=domain)
        except Domain.DoesNotExist:
            return False

        if recursive:
            for subdomain in self.entity.domains.all():
                if domain.has_subdomain_recursive(subdomain):
                    return True

        return self.entity.domains.filter(entity=domain.entity).exists()

    def remove_from_domain(self, domain):
        """
        Remove this entity from the specified domain, and remove all its Attributes associated with that domain.
        """
        if isinstance(domain, str):
            domain = Domain.objects.get(slug=domain)

        with transaction.atomic():
            self.entity.attrs.remove(*self.entity.attrs.filter(domain=domain))
            return self.entity.domains.remove(domain)

    def add_attr(self, domain, key, value) -> "Attribute":
        """
        Add the attribute to this entity.
        """
        if isinstance(domain, str):
            domain = Domain.objects.get(slug=domain)
        
        if not self.is_in_domain(domain):
            raise ValueError("cannot assign domain attributes unless the entity is part of that domain.")

        attr, _ = Attribute.objects.get_or_create(domain=domain, key=key, value=value)
        self.entity.attrs.add(attr)
        return attr

    def has_attr(self, domain, key, value) -> bool:
        """
        Check if this entity has the attribute.
        """
        if isinstance(domain, str):
            domain = Domain.objects.get(slug=domain)

        return self.entity.attrs.filter(domain=domain, key=key, value=value).exists()

    def remove_attr(self, domain, key, value) -> None:
        """
        Remove the attribute from this entity.
        """
        try:
            if isinstance(domain, str):
                domain = Domain.objects.get(slug=domain)
            attr = Attribute.objects.get(domain=domain, key=key, value=value)
        except Attribute.DoesNotExist:
            return

        return self.entity.attrs.remove(attr)

    def attrs_with_key(self, domain, key):
        """
        Return a QuerySet of attributes on this entity with the specified key.
        """
        if isinstance(domain, str):
            domain = Domain.objects.get(slug=domain)

        return self.entity.attrs.filter(key=key, domain=domain)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self._state.adding:
                if not hasattr(self, "entity"):
                    self.entity = Entity.objects.create()
                self.entity.content_types.add(self.content_type)
            return super().save(*args, **kwargs)

    def delete(self, hard_delete=False, isolated=False, *args, **kwargs):
        """
        Soft-deletes the Component, its Entity, and all its Entity's Components, keeping them in the database but marking them deleted, causing the default Manager to exclude them.

        Specify `hard_delete=True` to permanently delete the associated Entity and all its Components.

        Specify `isolated=True` to surgically delete this Component from its Entity without affecting the Entity or its other Components. 
        """
        self.deleted = True
        
        if not isolated:
            return self.entity.delete(hard_delete=hard_delete)
        else:
            if hard_delete:
                self.entity.content_types.remove(self.content_type)
                return super().delete(*args, **kwargs)
            else:
                self.save()


class Entity(models.Model):
    class Meta:
        verbose_name_plural = "entities"

    class ArchiveManager(models.Manager):
        pass

    class Manager(ArchiveManager):
        def get_queryset(self):
            return super().get_queryset().exclude(deleted_time__isnull=False)

    class QuerySet(models.QuerySet):
        def with_attr(self, domain, key, value):
            """
            Include only entities with the specified Attribute.
            """
            if isinstance(domain, str):
                domain = Domain.objects.get(slug=domain)

            return self.filter(attrs__domain=domain, attrs__key=key, attrs__value=value)

        def delete(self, hard_delete=False):
            if hard_delete:
                return super().delete()
            else:
                for entity in self:
                    entity.delete(hard_delete=hard_delete)

        def by_model(self, *models: models.Model):
            """
            Returns a dictionary mapping Models to querysets of objects of that type.

            Example:
            >>> Entity.objects.filter(...).by_model(User, Region, ...)
            {
                User: {<User: alice>, <User: bob>, ...},
                Region: {<Region: fredonia>, ...},
                ...
            }
            """
            results = dict()
            if not models:
                models = {ct.model_class() for ct in ContentType.objects.filter(pk__in=self.values_list("content_types", flat=True).distinct())}
            for model in models:
                ct = ContentType.objects.get_for_model(model)
                results[model] = model.objects.filter(entity__in=self.filter(content_types=ct))
            return results

        def all_subdomains(self):
            """
            Recursively replace all Domain entities in the QuerySet with their constituent entities.
            """
            domain_ct = ContentType.objects.get_for_model(Domain)
            subdomains = self.filter(content_types=domain_ct)
            return self.exclude(content_types=domain_ct).union(*[subdomain.object.entities.all_subdomains() for subdomain in subdomains])


    objects = Manager.from_queryset(QuerySet)()
    objects_archive = ArchiveManager.from_queryset(QuerySet)()

    id = models.AutoField(
        primary_key=True,
    )

    content_types = models.ManyToManyField(
        ContentType,
        editable=False,
        )

    created_time = models.DateTimeField(
        auto_now_add=True,
    )
    updated_time = models.DateTimeField(
        auto_now=True,
    )
    deleted_time = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        db_index=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )
    attrs = models.ManyToManyField(
        "ontology.Attribute",
        verbose_name="attributes",
        blank=True,
        related_name="entities",
    )

    def cast(self, model: ComponentModel):
        """
        Return this Entity's component of the specified type.
        """
        return model.objects.get(entity=self)

    def components(self):
        """
        Returns a dictionary of this Entity's components, mapping the ComponentModel subclass to the instance.
        """
        components = dict()
        for ct in self.content_types.all():
            model = ct.model_class()
            components[model] = model.objects.get(entity=self)
        return components

    def delete(self, hard_delete=False, *args, **kwargs):
        if hard_delete:
            # hard deletes all associated components by CASCADE
            return super().delete(*args, **kwargs)
        elif self.deleted_time == None:
            for component in self.components().values():
                component.deleted = True
                component.save()
            self.deleted_time = timezone.now()
            return self.save()
        else:
            return

    def __str__(self):
        return f"{self.id} ({', '.join([str(k)+':'+str(v) for k,v in self.components().items()])})"

class Domain(ComponentModel):
    """
    A set of Entities, which is itself an Entity.
    """
    slug = models.SlugField(unique=True)
    entities = models.ManyToManyField(
        Entity,
        related_name="domains",
        blank=True,
    )

    def superdomains(self):
        return Domain.objects.filter(pk__in=self.entity.domains.all())

    def subdomains(self):
        return Domain.objects.filter(pk__in=self.entities.filter(content_types=ContentType.objects.get_for_model(Domain)))

    def has_subdomain_recursive(self, subdomain):
        """
        Returns True if `subdomain` is a subdomain of this domain or any of its subdomains, recursively.
        """
        if subdomain == self:
            return True

        for domain in self.subdomains():
            if domain.has_subdomain_recursive(subdomain):
                return True

        return False

    def __str__(self):
        return self.slug


@receiver(models.signals.m2m_changed, sender=Domain.entities.through)
def on_domain_entities_m2m_changed(action, instance, pk_set, **kwargs):
    """
    Prevent cycles from forming in the domain graph.
    """
    if action == "pre_add":
        if isinstance(instance, Domain):
            superdomains = [instance]
            subdomains = Domain.objects.filter(pk__in=pk_set)
        else:
            superdomains = Domain.objects.filter(pk__in=pk_set)
            subdomains = Domain.objects.filter(pk=instance)

        for subdomain in subdomains:
            for superdomain in superdomains:
                if subdomain.has_subdomain_recursive(superdomain):
                    pk_set.remove(superdomain.pk)
                    logger.warning(f"prevented a subdomain cycle between {superdomain} and {subdomain}")


class Attribute(models.Model):
    """
    An attribute composed as a domain-key-value triple.
    """

    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
    )
    key = models.SlugField()
    value = models.CharField(max_length=255)

    def __str__(self):
        _domain = f"[{self.domain}] " if self.domain else ""
        return f"{_domain}{self.key}:{self.value}"

    class Meta:
        indexes = [
            models.Index(fields=["domain", "key", "value"])
        ]
        constraints = [
            models.UniqueConstraint(fields=["key", "value", "domain"], name="%(app_label)s_%(class)s_unique")
        ]

