import logging
from django.conf import settings
from django.db import IntegrityError, models
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.dispatch import receiver
import networkx
import collections

# Create your models here.

logger = logging.getLogger(__name__)

class EntityModel(models.Model):
    """
    Abstract class that overrides the default `id` primary key with a OneToOne field to the Entity table called `entity_id`.

    Therefore, all EntityModel subclasses share a global entity ID space, enabling fast and powerful new behaviors.

    Additionally, EntityModel subclasses are soft-deleted by default, and "deleted" objects are excluded from the default Manager.
    To permanently remove and object and its Entity from the database, specify `obj.delete(hard_delete=True)`.

    Otherwise, this object behaves like any other base Model subclass.
    """
    class Meta:
        abstract = True

    class ArchiveManager(models.Manager):
        pass

    class Manager(ArchiveManager):
        def get_queryset(self):
            return super().get_queryset().filter(deleted=False)

    class QuerySet(models.QuerySet):
        def with_attr(self, domain, key, value):
            """
            Include only entities with the specified Attribute.
            """
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

    objects = Manager.from_queryset(QuerySet)()
    objects_archive = ArchiveManager.from_queryset(QuerySet)()

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
        help_text="True indicates the object has been soft-deleted and won't appear in most queries."
    )

    def add_to_domain(self, domain):
        """
        Add this object to the specified domain.
        """
        if isinstance(domain, str):
            domain, _ = Domain.objects.get_or_create(slug=domain)
        return domain.entities.add(self.entity)

    def is_in_domain(self, domain, recursive=False):
        """
        Check whether this object is in the specified domain.

        If `recursive=True`, recursively check all subdomains.
        """
        if isinstance(domain, str):
            try:
                domain = Domain.objects.get(slug=domain)
            except Domain.DoesNotExist:
                return False

        if recursive:
            for subdomain in self.entity.domains.all():
                if domain.has_subdomain_recursive(subdomain):
                    return True

        return domain.entities.filter(id=self.entity_id).exists()

    def remove_from_domain(self, domain):
        """
        Remove this object to the specified domain, and remove all its Attributes associated with that domain.
        """
        if isinstance(domain, str):
            try:
                domain = Domain.objects.get(slug=domain)
            except Domain.DoesNotExist:
                return
        with transaction.atomic():
            self.entity.attrs.remove(*self.entity.attrs.filter(domain=domain))
            return domain.entities.remove(self.entity)

    def add_attr(self, domain, key, value) -> "Attribute":
        """
        Add the attribute to this object.
        """
        if domain != None:
            if isinstance(domain, str):
                domain = Domain.objects.get(slug=domain)
            
            if not self.is_in_domain(domain):
                raise ValueError("cannot assign domain attributes unless the object is part of that domain.")

        attr, _ = Attribute.objects.get_or_create(domain=domain, key=key, value=value)
        self.entity.attrs.add(attr)
        return attr

    def has_attr(self, domain, key, value) -> bool:
        """
        Check if this object has the attribute.
        """
        if isinstance(domain, str):
            domain = Domain.objects.get(slug=domain)

        return self.entity.attrs.filter(domain=domain, key=key, value=value).exists()

    def remove_attr(self, domain, key, value) -> None:
        """
        Remove the attribute from this object.
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
        Return a QuerySet of attributes on this object with the specified key.
        """
        return self.entity.attrs.filter(key=key, domain=domain)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self._state.adding:
                self.entity = Entity.objects.create(object=self)
            return super().save(*args, **kwargs)

    def delete(self, hard_delete=False, *args, **kwargs):
        self.deleted = True
        return self.entity.delete(hard_delete=hard_delete)


class Entity(models.Model):
    class Meta:
        verbose_name_plural = "entities"

    class ArchiveManager(models.Manager):
        pass

    class Manager(ArchiveManager):
        def get_queryset(self):
            return super().get_queryset().filter(deleted_time__isnull=True)

    class QuerySet(models.QuerySet):
        def with_attr(self, key, value, domain=None):
            """
            Include only entities with the specified Attribute.
            """
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
                models = {ct.model_class() for ct in ContentType.objects.filter(pk__in=self.values_list("content_type", flat=True).distinct())}
            for model in models:
                ct = ContentType.objects.get_for_model(model)
                results[model] = model.objects.filter(entity__in=self.filter(content_type=ct))
            return results


        def all_subdomains(self):
            """
            Recursively replace all Domain entities in the QuerySet with their constituent entities.
            """
            qs = super().all()
            domain_ct = ContentType.objects.get_for_model(Domain)
            subdomains = qs.filter(content_type=domain_ct)
            return qs.exclude(content_type=domain_ct).union(*[subdomain.object.entities.all_subdomains() for subdomain in subdomains])


        def as_graph(self) -> networkx.MultiDiGraph:
            """
            Returns a NetworkX graph of entities and their relationships contained in the QuerySet.
            Entities adjacent to those in the QuerySet may also be included in the graph.
            Non-entity nodes and their relationships to entities are not included.

            Documentation: https://networkx.org/
            """
            graph = networkx.MultiDiGraph()
            related_entity_fields = dict()

            for entity in self:
                obj = entity.object
                if entity.content_type not in related_entity_fields:
                    # Only use fields that are relations to other EntityModels.
                    # We only have to do this once per ContentType!
                    d = {"fk": dict(), "m2m": dict()}
                    for field in obj._meta.fields:
                        if (not field.is_relation) or (field.primary_key) or (field.related_model._meta.pk.related_model != Entity):
                            continue
                        d["fk"][field.name] = field.verbose_name

                    for m2mfield in obj._meta.local_many_to_many:
                        if m2mfield.related_model._meta.pk.related_model != Entity:
                            continue
                        d["m2m"][m2mfield.name] = m2mfield.verbose_name

                    related_entity_fields[entity.content_type] = d
                
                for name, verbose_name in related_entity_fields[entity.content_type]["fk"].items():
                    target = getattr(obj, name)
                    if target != None:
                        graph.add_edge(obj, target, label=verbose_name)

                for name, verbose_name in related_entity_fields[entity.content_type]["m2m"].items():
                    for target in getattr(obj, name).all():
                        graph.add_edge(obj, target, label=verbose_name)

            return graph

    objects = Manager.from_queryset(QuerySet)()
    objects_archive = ArchiveManager.from_queryset(QuerySet)()

    id = models.AutoField(
        primary_key=True,
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.RESTRICT,
        )
    object = GenericForeignKey(
        fk_field='id',
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

    def delete(self, hard_delete=False, *args, **kwargs):
        if hard_delete:
            return super().delete(*args, **kwargs)
        elif self.deleted_time == None:
            self.object.deleted = True
            self.object.save()
            self.deleted_time = timezone.now()
            return self.save()
        else:
            return

    def __str__(self):
        return f"{self.content_type} | {self.object}"

class Domain(EntityModel):
    """
    A set of Entities, which is itself an Entity.
    """
    slug = models.SlugField(unique=True)
    entities = models.ManyToManyField(
        Entity,
        related_name="domains",
        through="Domain_Entities"
    )

    def superdomains(self):
        return Domain.objects.filter(pk__in=self.entity.domains.all())

    def subdomains(self):
        return Domain.objects.filter(pk__in=self.entities.filter(content_type=ContentType.objects.get_for_model(Domain)))

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

class Domain_Entities(models.Model):
    """
    M2M `through` model for Domain.entities
    """
    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
    )
    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~models.Q(domain_id=models.F("entity_id")),
                name="%(app_label)s_%(class)s_no_self_reference"
            )
        ]

@receiver(models.signals.m2m_changed, sender=Domain_Entities)
def on_domain_entities_m2m_changed(action, instance, pk_set, **kwargs):
    """
    Prevent cycles from forming in the domain graph.
    """
    if action == "pre_add":
        for domain in Domain.objects.filter(pk__in=pk_set):
            if domain.has_subdomain_recursive(instance):
                raise IntegrityError("cycle detected in domain graph!")


class Attribute(models.Model):
    """
    An attribute composed as a domain-key-value triple.
    """

    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
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

