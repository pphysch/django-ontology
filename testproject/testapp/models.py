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
    )

    friends = models.ManyToManyField(
        "self",
        symmetrical=False,
    )

    def __str__(self):
        return self.slug


class Place(EntityModel):
    slug = models.SlugField(unique=True)

    parent = models.ForeignKey(
        "self",
        null=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return self.slug


class Thing(EntityModel):
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.slug