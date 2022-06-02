from django.contrib import admin
from ontology.admin import EntityModelAdmin

from . import models

# Register your models here.

#@admin.register(models.Person)
#class PersonAdmin(admin.ModelAdmin):
#    inlines = [EntityAdminInline]

@admin.register(models.Person)
class PersonAdmin(EntityModelAdmin):
    inlines = []
    pass

@admin.register(models.Place)
class PlaceAdmin(EntityModelAdmin):
    pass

@admin.register(models.Thing)
class ThingAdmin(EntityModelAdmin):
    pass