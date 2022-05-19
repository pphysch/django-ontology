from django.dispatch import receiver
from django.db.models import signals, Q

from .models import *

import logging

logger = logging.getLogger(__name__)


# This handler hits the DB a lot and may need to be rewritten using raw SQL if causing problems.
# However, Policies should not be changed too often in practice.
@receiver(signals.post_save, sender=Policy)
def on_policy_save(instance, **kwargs):
    permission_ids = set()

    if instance.is_active():
        for action in instance.actions.all():
            subjects = Entity.objects.filter(
                content_type=action.subject_type, tags__in=instance.subject_tags.all()
            )
            objects = Entity.objects.filter(
                content_type=action.target_type, tags__in=instance.target_tags.all()
            )

            for subject in subjects:
                for target in objects:
                    permission, created = Permission.objects.get_or_create(
                        policy=instance,
                        subject=subject,
                        action=action,
                        target=target,
                        defaults={
                            "priority": instance.priority,
                            "deny": instance.deny,
                        },
                    )

                    if (
                        permission.priority != instance.priority
                        or permission.deny != instance.deny
                    ):
                        permission.priority = instance.priority
                        permission.deny = instance.deny
                        permission.save()

                    permission_ids.add(permission.id)

    orphaned_permissions = Permission.objects.filter(policy=instance).exclude(
        id__in=permission_ids
    )
    orphaned_permissions.delete()


@receiver(signals.m2m_changed, sender=Policy.subject_tags.through)
def on_policy_subject_tags_change(instance, **kwargs):
    on_policy_save(instance)


@receiver(signals.m2m_changed, sender=Policy.target_tags.through)
def on_policy_target_tags_change(instance, **kwargs):
    on_policy_save(instance)


@receiver(signals.m2m_changed, sender=Policy.actions.through)
def on_policy_actions_change(instance, **kwargs):
    on_policy_save(instance)


@receiver(signals.m2m_changed, sender=Entity.tags.through)
def on_tag_change(action, instance, pk_set, **kwargs):
    if action == "post_add":
        for policy in Policy.objects.by_entity(instance):
            on_policy_save(instance=policy)
    elif action == "pre_remove":
        for policy in Policy.objects.by_entity(instance):
            Permission.objects.filter(
                Q(subject=instance) | Q(target=instance), policy=policy
            ).delete()


@receiver(signals.post_save, sender=Permission)
def on_permission_save(instance: Permission, **kwargs):
    peers = Permission.objects.peer_of(instance)

    if instance == peers.first():
        # This Permission instance is the current leader
        if peers.count() > 1:
            follower = peers[1]
            if follower.deny == instance.deny:
                instance.is_synced = follower.is_synced
                instance.last_sync_attempt_time = follower.last_sync_attempt_time
            else:
                instance.sync()
        else:
            # This Permission has no peers, so make sure it is synced.
            instance.sync()


@receiver(signals.post_delete, sender=Permission)
def on_permission_delete(instance: Permission, **kwargs):
    incumbent: Permission = Permission.objects.peer_of(instance).first()
    if incumbent:
        # The incumbent is the Permission replacing the instance
        if instance.deny == incumbent.deny:
            incumbent.is_synced = instance.is_synced
            incumbent.last_sync_attempt_time = instance.last_sync_attempt_time
        else:
            incumbent.sync()
    else:
        if not instance.deny:
            instance.deny = True
            instance.sync()
