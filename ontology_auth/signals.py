from django.db.models import signals
from django.dispatch import receiver
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models import Q
from . import models

# These are essential receivers for keeping Entitlements in sync with Policies.

@receiver(signals.m2m_changed, sender=models.Entity.attrs.through)
def on_entity_attribute_change(instance, action, pk_set, **kwargs):
    """
    When an Entity's attributes change, update Entitlements accordingly.
    """
    print(action, instance, pk_set)
    if action == "post_add":
        if isinstance(instance, models.Entity):
            entities = [instance]
            added_attrs = models.Attribute.objects.filter(pk__in=pk_set)
        else:
            entities = models.Entity.objects.filter(pk__in=pk_set)
            added_attrs = [instance]

        new_entitlements = []
        for entity in entities:
            for added_attr in added_attrs:
                for policy in added_attr.policies_as_source.all():
                    other_attrs = policy.source_attrs.exclude(pk=added_attr.pk)
                    if set(other_attrs).issubset(entity.attrs.all()):
                        new_entitlements.extend(policy._extrude_source(entity))
                for policy in added_attr.policies_as_target.all():
                    other_attrs = policy.target_attrs.exclude(pk=added_attr.pk)
                    if set(other_attrs).issubset(entity.attrs.all()):
                        new_entitlements.extend(policy._extrude_target(entity))

        models.Entitlement.objects.bulk_create(new_entitlements, batch_size=64, ignore_conflicts=True)

    elif action == "post_remove":
        if isinstance(instance, models.Entity):
            entities = [instance]
            removed_attrs = models.Attribute.objects.filter(pk__in=pk_set)
        else:
            entities = models.Entity.objects.filter(pk__in=pk_set)
            removed_attrs = [instance]

        for removed_attr in removed_attrs:
            for entity in entities:
                for policy in (removed_attr.policies_as_source.all() | removed_attr.policies_as_target.all()):
                    policy.entitlements.filter(Q(source=entity)|Q(target=entity)).delete()


@receiver(signals.m2m_changed, sender=models.Policy.allow_permissions.through)
def on_policy_allow_permissions_change(instance, action, pk_set, **kwargs):
    """
    When a Policy's Permission set changes, update the Entitlements accordingly.
    """
    print("allow_perms", action, instance, pk_set)
    if action == "post_add":
        if isinstance(instance, models.Policy):
            policies = [instance]
            permissions = Permission.objects.filter(pk__in=pk_set)
        else:
            policies = models.Policy.objects.filter(pk__in=pk_set)
            permissions = [instance]

        print("got here")
        new_entitlements = []
        for policy in policies:
            for permission in permissions:
                print(policy, permission)
                entitlements = policy.entitlements.filter(target__content_types=permission.content_type)
                print(policy, permission, entitlements)
                for d in entitlements.values("source_id", "target_id").distinct():
                    new_entitlements.append(
                        models.Entitlement(
                            policy=policy,
                            source_id=d["source_id"],
                            permission=permission,
                            target_id=d["target_id"],
                        )
                    )
        models.Entitlement.objects.bulk_create(new_entitlements, batch_size=64)

    elif action == "post_remove":
        if isinstance(instance, models.Policy):
            policies = [instance]
            permissions = Permission.objects.filter(pk__in=pk_set)
        else:
            policies = models.Policy.objects.filter(pk__in=pk_set)
            permissions = [instance]
        for policy in policies:
            for permission in permissions:
                policy.entitlements.filter(permission=permission).delete()


@receiver(signals.m2m_changed, sender=models.Policy.source_attrs.through)
@receiver(signals.m2m_changed, sender=models.Policy.target_attrs.through)
def on_policy_attrs_change(instance, action, pk_set, **kwargs):
    """
    When a Policy's source or target Attribute sets change, reset the associated Entitlements.
    """
    print(action, instance, pk_set)
    if action == "post_add" or action == "post_remove":
        if isinstance(instance, models.Policy):
            policies = [instance]
        else:
            policies = models.Policy.objects.filter(pk__in=pk_set)
        for policy in policies:
            with transaction.atomic():
                policy.entitlements.all().delete()
                policy.create_entitlements()


@receiver(signals.m2m_changed, sender=models.Domain.entities.through)
def on_entity_domain_change(instance, action, pk_set, **kwargs):
    """
    When a Domain gets or loses Entities, update Entitlements accordingly.
    """
    print(action, instance, pk_set)
    if action == "post_add":
        if isinstance(instance, models.Entity):
            entities = [instance]
            domains = models.Domain.objects.filter(pk__in=pk_set)
        else:
            entities = models.Entity.objects.filter(pk__in=pk_set)
            domains = [instance]
        new_entitlements = []
        for domain in domains:
            # Add the entity to any "catch-all" policies in the domain
            for entity in entities:
                for policy in domain.policies.filter(source_attrs=None):
                    new_entitlements.extend(policy._extrude_source(entity))
                for policy in domain.policies.filter(target_attrs=None):
                    new_entitlements.extend(policy._extrude_target(entity))

        models.Entitlement.objects.bulk_create(new_entitlements, batch_size=64)
        
    elif action == "post_remove":
        if isinstance(instance, models.Entity):
            entities = [instance]
            domains = models.Domain.objects.filter(pk__in=pk_set)
        else:
            entities = models.Entity.objects.filter(pk__in=pk_set)
            domains = [instance]
        # Delete all entitlements associated with the entity and domain
        for domain in domains:
            for entity in models.Entity.objects.filter(pk__in=pk_set):
                entity.entitlements_as_source.filter(policy__domain=domain).delete()
                entity.entitlements_as_target.filter(policy__domain=domain).delete()