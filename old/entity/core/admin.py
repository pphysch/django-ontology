from django.contrib import admin
from . import models

class CommentAdminInline(admin.StackedInline):
    model=models.Comment
    extra=1

class TagAdminInline(admin.TabularInline):
    model=models.EntityM2MTag
    extra=1

# Register your models here.
@admin.register(models.Entity)
class EntityAdmin(admin.ModelAdmin):
    readonly_fields = ['object']
    inlines = [TagAdminInline, CommentAdminInline]

admin.site.register(models.Dummy)
