from django.db import models
from ontology.models import ComponentModel

# Create your models here.

class Person(ComponentModel):
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


class Place(ComponentModel):
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


class Thing(ComponentModel):
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.slug

    class Meta:
        permissions = [('can_use_thing', 'Can use thing')]