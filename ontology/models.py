from django.conf import settings
from django.db import models
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.contrib import admin
import networkx
import collections

# Create your models here.

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
            return super().get_queryset().filter(entity__deleted_time__isnull=True)

    class QuerySet(models.QuerySet):
        def with_tag(self, tag: "Tag"):
            """
            Include only entities with the specified Tag.

            `tag` may be a string of the form `"key:value"`.
            """
            if isinstance(tag, str):
                tag = Tag.objects.from_string(tag)
            return self.filter(entity__tags=tag)

    objects = Manager.from_queryset(QuerySet)()
    objects_archive = ArchiveManager.from_queryset(QuerySet)()

    entity = models.OneToOneField(
        "ontology.Entity",
        on_delete=models.CASCADE,
        primary_key=True,
        editable=False,
    )

    def add_tag(self, tag: "Tag") -> "Tag":
        """
        Add the tag to this object.

        `tag` may be a string of the form `"key:value"`.
        """
        if isinstance(tag, str):
            tag = Tag.objects.from_string(tag)

        self.entity.tags.add(tag)
        return tag

    def has_tag(self, tag: "Tag") -> bool:
        """
        Check if this object has the tag.

        `tag` may be a string of the form `"key:value"`.
        """
        if isinstance(tag, str):
            try:
                tag = Tag.objects.from_string(tag, may_create=False)
            except Tag.DoesNotExist:
                return False

        return self.entity.tags.filter(pk=tag.pk).exists()

    def remove_tag(self, tag: "Tag") -> None:
        """
        Remove the tag from this object.

        `tag` may be a string of the form `"key:value"`.
        """
        if isinstance(tag, str):
            try:
                tag = Tag.objects.from_string(tag, may_create=False)
            except Tag.DoesNotExist:
                return

        return self.entity.tags.remove(tag)

    def tags_with_key(self, key):
        """
        Return a QuerySet of tags on this object with the specified key.
        """
        return self.entity.tags.filter(key=key)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self._state.adding:
                self.entity = Entity.objects.create(object=self)
            return super().save(*args, **kwargs)

    def delete(self, hard_delete=False, *args, **kwargs):
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
        def with_tag(self, tag: "Tag"):
            """
            Include only entities with the specified Tag.

            `tag` may be a string of the form `"key:value"`.
            """
            if isinstance(tag, str):
                tag = Tag.objects.from_string(tag)
            return self.filter(tags=tag)

        def as_objects(self):
            """
            Returns a dictionary mapping ContentTypes to sets of objects of that type.

            >>> Entity.objects.all().as_objects()
            {
                <ContentType: auth | user>: {<User: alice>, <User: bob>, ...},
                <ContentType: gis | region>: {<Region: fredonia>, ...},
                ...
            }
            """
            result = collections.defaultdict(set)
            for entity in self.order_by('content_type'):
                ct = entity.content_type
                result[ct].add(entity.object)
            return result

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
    contacts = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="listed_as_contact",
    )
    tags = models.ManyToManyField(
        "ontology.Tag",
        blank=True,
    )

    def delete(self, hard_delete=False, *args, **kwargs):
        if hard_delete:
            return super().delete(*args, **kwargs)
        elif self.deleted_time != None:
            self.deleted_time = timezone.now()
            return self.save()
        else:
            return

    def __str__(self):
        return f"{self.content_type} | {self.object}"

class Tag(models.Model):
    """
    A tag composed of a key-value text pair.

    Use keys for domains or namespaces, and values for the actual "tag".

    Examples:
     - "state":"utah"
     - "organization_type":"university"
     - "incident-83526371":"investigate"
     - "__subapp__tags":"foobar"
    """

    class Manager(models.Manager):
        def from_string(self, tag_string: str, may_create=True) -> "Tag":
            tokens = tag_string.split(":")
            if len(tokens) < 2:
                raise ValueError("tag_string must be in the format 'key:value'")
            key = tokens[0]
            value = ":".join(tokens[1:])
            if may_create:
                tag, created = self.get_or_create(key=key, value=value)
            else:
                tag = self.get(key=key, value=value)
            return tag

    objects = Manager()

    key = models.SlugField()
    value = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.key}:{self.value}"

    class Meta:
        indexes = [
            models.Index(fields=["key", "value"])
        ]
        constraints = [
            models.UniqueConstraint(fields=["key", "value"], name="%(app_label)s_%(class)s_unique_kv")
        ]

