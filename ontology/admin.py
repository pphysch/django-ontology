from django.contrib import admin
from . import models
from .indirect_inline import IndirectStackedInline

# Register your models here.

class ComponentModelAdmin(admin.ModelAdmin):
    def get_inlines(self, request, obj):
        inlines = super().get_inlines(request, obj=obj)
        if EntityAdminInline not in inlines:
            return inlines + [EntityAdminInline]
        return inlines

class EntityAdminInline(IndirectStackedInline):
    model = models.Entity
    extra = 3
    autocomplete_fields = ["attrs"]
    readonly_fields = ['id', 'content_types', 'created_time', 'updated_time', 'deleted_time']
    fieldsets = (
        (None, {
            "fields": ('notes', 'attrs', 'content_types')
        }),
        ("Timestamps", {
            "fields": ('created_time', 'updated_time', 'deleted_time'),
            "classes": ('collapse',),
        })
    )

    def get_form_queryset(self, obj):
        return self.model.objects.filter(id=obj.entity_id)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(models.Attribute)
class AttributeAdmin(admin.ModelAdmin):
    search_fields = ["domain__slug", "key", "value"]

@admin.register(models.Domain)
class DomainAdmin(ComponentModelAdmin):
    filter_horizontal = ["entities"]
    pass