from django.contrib import admin
from ontology.admin import ComponentModelAdmin

from . import models

# Register your models here.

#@admin.register(models.Person)
#class PersonAdmin(admin.ModelAdmin):
#    inlines = [EntityAdminInline]

@admin.register(models.Person)
class PersonAdmin(ComponentModelAdmin):
    inlines = []
    pass

@admin.register(models.Place)
class PlaceAdmin(ComponentModelAdmin):
    pass

@admin.register(models.Thing)
class ThingAdmin(ComponentModelAdmin):
    pass