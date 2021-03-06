from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from ontology.admin import ComponentModelAdmin
from . import models

# Register your models here.

@admin.register(models.User)
class UserAdmin(BaseUserAdmin, ComponentModelAdmin):
    pass

@admin.register(models.Policy)
class PolicyAdmin(admin.ModelAdmin):
    filter_horizontal = ["source_attrs", "allow_permissions", "target_attrs"]