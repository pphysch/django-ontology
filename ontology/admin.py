from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline, GenericTabularInline
from . import models

# Register your models here.

class EntityModelAdmin(admin.ModelAdmin):
    def get_inlines(self, request, obj):
        inlines = super().get_inlines(request, obj=obj)
        if EntityAdminInline not in inlines:
            return inlines + [EntityAdminInline]
        return inlines

class EntityAdminInline(GenericStackedInline):
    model = models.Entity
    ct_fk_field = "id"
    extra = 0
    autocomplete_fields = ["contacts", "attrs"]
    readonly_fields = ['id', 'created_time', 'updated_time', 'deleted_time']
    fieldsets = (
        (None, {
            "fields": ('notes', 'attrs')
        }),
        ("Timestamps", {
            "fields": ('created_time', 'updated_time', 'deleted_time'),
            "classes": ('collapse',),
        })
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(models.Attribute)
class AttributeAdmin(admin.ModelAdmin):
    search_fields = ["key", "value"]

@admin.register(models.Domain)
class DomainAdmin(EntityModelAdmin):
    pass