from django.contrib.auth.backends import BaseBackend
from ontology.models import Entity, ComponentModel
from . import models

class DomainAuthorizationBackend(BaseBackend):
    def has_perm(self, user_obj, perm: str, obj=None) -> bool:
        """
        Returns True if the User has permission to the entity, and False otherwise.
        """
        if obj == None:
            return False

        # `match` would be nice here...
        if isinstance(obj, ComponentModel):
            target = obj.entity
        elif isinstance(obj, Entity):
            target = obj
        else:
            return False

        source = user_obj.entity

        app_label, codename = perm.split('.')
        return models.Entitlement.objects.filter(
            source=source,
            target=target,
            permission__codename=codename,
            permission__content_type__app_label=app_label,
            source__deleted_time__isnull=True,
            target__deleted_time__isnull=True,
            policy__disabled=False,
            ).exists()