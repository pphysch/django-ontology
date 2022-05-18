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
    """Abstract class for inheriting Entity behavior."""
    class Meta:
        abstract = True

    class ArchiveManager(models.Manager):
        pass

    class Manager(ArchiveManager):
        def get_queryset(self):
            return super().get_queryset().filter(deleted_time__isnull=True)

    class QuerySet(models.QuerySet):
        def with_tag(self, key, value):
            return self.filter(entity__tags__key=key, entity__tags__value=value)

    objects = Manager.from_queryset(QuerySet)()
    objects_archive = ArchiveManager.from_queryset(QuerySet)()

    entity = models.OneToOneField(
        "ontology.Entity",
        on_delete=models.CASCADE,
        primary_key=True,
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

    def has_permission(self, action: "Action", target: "EntityModel") -> bool:
        """
        Check whether this object is allowed to perform the action on the target.
        """

        if isinstance(action, str):
            action = Action.objects.from_objects(self, action, target)

        permission = (
            self.entity.permissions_as_subject.order_by("-priority", "-id")
            .filter(action=action, target=target.entity)
            .first()
        )

        if permission == None:
            return False

        return not permission.deny

    def get_actionable_targets(self, action: "Action"):
        """
        Return a queryset of objects that this object is allowed to perform the specified action on.

        Example - Get set of Projects that the logged-in user has manager permissions over:
        >>> request.user.get_actionable_targets(manage_action)
        <QuerySet [<Project: example-project>, <Project: foobar>]>
        """

        target_model = action.target_type.model_class()
        targets = target_model.objects.filter(
            entity__permissions_as_target__subject=self.entity,
            entity__permissions_as_target__action=action,
        ).distinct()
        valid_target_ids = {
            t.entity_id for t in targets if self.has_permission(action, t)
        }
        return target_model.objects.filter(entity_id__in=valid_target_ids)

    def get_actionable_subjects(self, action: "Action"):
        """
        Return a queryset of objects that are allowed to perform the specified action targeted at this object.

        Not to be confused with `get_actionable_targets()`!

        Example - Get set of users that have manager permissions over <Project: foobar>:
        >>> project_foobar.get_actionable_subjects(action_manage)
        <QuerySet [<User:django_admin>, <User:foobar_admin>]>
        """
        model = action.subject_type.model_class()
        subjects = model.objects.filter(
            entity__permissions_as_subject__target=self.entity,
            entity__permissions_as_subject__action=action,
        ).distinct()
        valid_subject_ids = {
            s.entity_id for s in subjects if s.has_permission(action, self)
        }
        return model.objects.filter(entity_id__in=valid_subject_ids)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self._state.adding:
                self.entity = Entity.objects.create(object=self)
            return super().save(*args, **kwargs)

    def delete(self, hard_delete=False, *args, **kwargs):
        with transaction.atomic():
            if hard_delete:
                if self.entity != None:
                    self.entity.delete()
                return super().delete(*args, **kwargs)
            elif self.deleted_time != None:
                self.deleted_time = timezone.now()
                self.save()
            else:
                # NOOP if the object was already soft-deleted.
                pass


class Entity(models.Model):
    class Meta:
        verbose_name_plural = "entities"

    class QuerySet(models.QuerySet):
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

    objects = QuerySet.as_manager()

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

    tags = models.ManyToManyField(
        "ontology.Tag",
    )

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


class Note(models.Model):
    """
    A note or comment left by a user.
    """
    class Meta:
        ordering = ['-score', '-created_time']
        indexes = [
            models.Index(fields=['entity', '-score', '-created_time']),
            models.Index(fields=['author']),
            ]

    entity = models.ForeignKey(
        "ontology.Entity",
        on_delete=models.CASCADE,
        related_name = "notes",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name = "comments",
    )
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    score = models.IntegerField(
        default=0,
    )
    text = models.TextField(
        null=True,
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
    )

    def delete(self, hard_delete=False, *args, **kwargs):
        if hard_delete:
            super().delete(*args, **kwargs)
        else:
            self.text = None
            self.deleted_time = timezone.now()
            self.save()


class Action(models.Model):
    """
    A "ContentType-safe" representation of an arbitrary action.

    For instance, "access" (a file) is a different Action than "access" (a building).
    """
    class Manager(models.Manager):
        def from_objects(self, subject, slug, target, may_create=False):
            fields = {
                "slug": slug,
                "subject_type": ContentType.objects.get_for_model(subject),
                "target_type": ContentType.objects.get_for_model(target),
                }
            if may_create:
                action, created = self.get_or_create(**fields)
            else:
                action = self.get(**fields)
            return action

    objects = Manager()

    slug = models.SlugField(
        max_length=255,
        unique=True,
    )
    description = models.TextField()

    subject_type = models.ForeignKey(
        ContentType,
        on_delete=models.RESTRICT,
        related_name="actions_as_subject",
    )
    target_type = models.ForeignKey(
        ContentType,
        on_delete=models.RESTRICT,
        related_name="actions_as_target",
    )

    def __str__(self):
        return self.slug


class Policy(models.Model):
    """
    A basic policy for allowing or denying actions.

    IMPORTANT: The subject_tags, actions, and target_tags sets are viewed as ANY rather than ALL. For example, a policy with subject_tags of {"role:manager","role:employee"} will apply to all users that have EITHER role, not BOTH roles.
    """

    class QuerySet(models.QuerySet):
        def by_entity(self, entity: Entity):
            tags = entity.tags.all()
            ct = entity.content_type
            return self.filter(
                (models.Q(subject_tags__in=tags) | models.Q(target_tags__in=tags))
                & (models.Q(actions__subject_type=ct) | models.Q(actions__target_type=ct))
            ).distinct()

    objects = QuerySet.as_manager()

    class Meta:
        verbose_name_plural = "policies"

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="A unique name to identify this policy.",
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    subject_tags = models.ManyToManyField(
        "Tag",
        related_name="policies_as_subject",
    )
    actions = models.ManyToManyField(
        "Action",
    )
    target_tags = models.ManyToManyField(
        "Tag",
        related_name="policies_as_target",
    )

    deny = models.BooleanField(
        default=False,
    )

    priority = models.IntegerField(
        default=0,
    )

    expiration_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    @admin.display(boolean=True)
    def is_active(self):
        return self.expiration_time == None or self.expiration_time > timezone.now()

    def related_subject_entities(self):
        """
        Return the set of entities that share one or more `subject_tags`.
        """
        pass

    def recompile_by_action(self, action):
        pass

    def __str__(self):
        return self.name


class Permission(models.Model):
    """
    A read-only model for concrete Permissions. To modify these, modify the corresponding Policy or its Tags' associations, and these will update automatically.
    """
    class QuerySet(models.QuerySet):
        def peer_of(self, permission):
            """
            Returns all permissions that have the same subject, action, and target.
            """

            return self.order_by("-priority", "-id").filter(
                subject=permission.subject,
                action=permission.action,
                target=permission.target,
            )

    objects = QuerySet.as_manager()

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        editable=False,
    )
    deny = models.BooleanField(
        editable=False,
    )
    priority = models.IntegerField(
        editable=False,
    )
    subject = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        editable=False,
        related_name="permissions_as_subject",
    )
    action = models.ForeignKey(
        Action,
        on_delete=models.RESTRICT,
        editable=False,
    )
    target = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        editable=False,
        related_name="permissions_as_target",
    )
    is_synced = models.BooleanField(
        default=False,
        editable=False,
    )
    last_sync_attempt_at = models.DateTimeField(
        default=None,
        null=True,
        editable=False,
    )

    def sync(self):
        """
        Attempt to synchronize this permission with a remote authorization system, if necessary.
        """
        pass

    def __str__(self):
        return f"{self.priority} ({self.subject}) -[{'DENY ' if self.deny else ''}{self.action}]-> ({self.target})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "subject", "action", "target"],
                name="unique_permission",
            ),
        ]
        indexes = [
            models.Index(fields=["subject", "action", "target", "priority"]),
        ]
