from django.conf import settings
from django.db import models
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone

# Create your models here.

class EntityModel(models.Model):
    """Abstract class for inheriting Entity behavior."""
    class Meta:
        abstract = True

    entity = models.OneToOneField(
        "core.Entity",
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

class Tag(models.Model):
    key = models.SlugField()
    value = models.CharField(max_length=255)

class EntityM2MTag(models.Model):
    class Meta:
        db_table = f"{Tag._meta.app_label}_{Entity._meta.model_name}_{Tag._meta.model_name}"

    entity = models.ForeignKey(
        "core.Entity",
        on_delete=models.CASCADE,
        related_name="tags",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="entities",
    )

class Comment(models.Model):
    class Meta:
        ordering = ['-score', '-created_time']
        indexes = [
            models.Index(fields=['entity', '-score', '-created_time']),
            models.Index(fields=['author']),
            ]

    entity = models.ForeignKey(
        "core.Entity",
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
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
    

class Dummy(EntityModel):
    class Meta:
        verbose_name_plural = "dummies"

    slug = models.SlugField(unique=True)