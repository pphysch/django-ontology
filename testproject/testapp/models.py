from django.db import models
from ontology.models import EntityModel

# Create your models here.

class Person(EntityModel):
    class Meta:
        verbose_name_plural = "people"

    slug = models.SlugField(unique=True)

    location = models.ForeignKey(
        "Place",
        null=True,
        on_delete=models.SET_NULL,
    )

    items = models.ManyToManyField(
        "Thing",
        blank=True,
    )

    friends = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
    )

    def __str__(self):
        return self.slug


class Place(EntityModel):
    slug = models.SlugField(unique=True)

    parent = models.ForeignKey(
        "self",
        null=True,
        on_delete=models.SET_NULL,
        blank=True,
    )

    def __str__(self):
        return self.slug

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~models.Q(entity=models.F('parent')),
                name="no_self_parent",
            )
        ]


class Thing(EntityModel):
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.slug