from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import AbstractUser, Permission, UserManager
from ontology.models import ComponentModel, Entity, Domain, Attribute
from django.db import transaction

class User(ComponentModel, AbstractUser):
    pass


class Policy(models.Model):
    class Manager(models.Manager):
        def create_from_strs(self, domain, label, source_attr_strs=(), perm_strs=(), target_attr_strs=()):
            source_attrs = set()
            for s in source_attr_strs:
                tokens = s.split(':')
                attr, created = Attribute.objects.get_or_create(domain=domain, key=tokens[0], value=':'.join(tokens[1:]))
                source_attrs.add(attr.id)

            target_attrs = set()
            for s in target_attr_strs:
                tokens = s.split(':')
                attr, created = Attribute.objects.get_or_create(domain=domain, key=tokens[0], value=':'.join(tokens[1:]))
                target_attrs.add(attr.id)


            allow_permissions = set()
            for s in perm_strs:
                app_label, codename = s.split('.')
                allow_permissions.add(Permission.objects.get(codename=codename, content_type__app_label=app_label).id)

            obj = self.create(
                domain=domain,
                label=label,
            )
            obj.source_attrs.add(*source_attrs)
            obj.target_attrs.add(*target_attrs)
            obj.allow_permissions.add(*allow_permissions)

            return obj

    class QuerySet(models.QuerySet):
        def reset_entitlements(self):
            """
            Delete and recreate all Entitlements associated with the selected Policies. May take a while, so use with care!
            """
            for policy in self:
                with transaction.atomic():
                    policy.entitlements.all().delete()
                    policy.create_entitlements()
                

    objects = Manager.from_queryset(QuerySet)()

    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="policies",
    )
    label = models.SlugField()

    source_attrs = models.ManyToManyField(
        Attribute,
        related_name="policies_as_source",
        help_text="Objects must have all attributes to be included in this policy."
    )
    allow_permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="policies",
    )
    target_attrs = models.ManyToManyField(
        Attribute,
        related_name="policies_as_target",
        help_text="Objects must have all attributes to be included in this policy."
    )
    disabled = models.BooleanField(
        default=False,
        help_text="When this policy is disabled, it will not be considered when checking permissions."
    )

    def sources(self):
        # For now, sources are only Users, but in theory they could be any ComponentModel
        qs = self.domain.entities.filter(content_types=ContentType.objects.get_for_model(get_user_model()))
        for attr in self.source_attrs.all():
            qs = qs.filter(attrs=attr)
        return qs

    def targets(self):
        qs = self.domain.entities.all()
        for attr in self.target_attrs.all():
            qs = qs.filter(attrs=attr)
        return qs

    def create_entitlements(self):
        """
        Attempts to create all Entitlements described by this Policy.
        """
        new_entitlements = []
        sources = self.sources()
        targets = self.targets()
        permissions = self.allow_permissions.all()
        for source in sources:
            for target in targets:
                for permission in permissions:
                    if permission.content_type == target.content_type:
                        new_entitlements.append(
                            Entitlement(
                                policy=self,
                                source=source,
                                permission=permission,
                                target=target,
                            )
                        )
        return Entitlement.objects.bulk_create(new_entitlements, batch_size=64, ignore_conflicts=True)

    def _extrude_source(self, source):
        """
        Efficiently specifies the entitlements that should be created when an Entity is added as a source to a policy.
        """
        new_entitlements = []
        references = self.entitlements.values("permission_id", "target_id").distinct()
        if len(references) == 0:
            # If there are no Entitlements to extrude, we have to do a bit more work.
            for target in self.targets():
                for permission in self.allow_permissions.filter(content_type__in=target.content_types.all()):
                    new_entitlements.append(
                        Entitlement(
                            policy=self,
                            source=source,
                            permission=permission,
                            target=target
                        )
                    )
        for d in references:
            new_entitlements.append(
                Entitlement(
                    policy=self,
                    source=source,
                    permission_id=d["permission_id"],
                    target_id=d["target_id"],
                )
            )
        return new_entitlements

    def _extrude_target(self, target):
        """
        Efficiently specifies the entitlements that should be created when an Entity is added as a target to a policy.
        """
        new_entitlements = []
        references = self.entitlements.filter(permission__content_type__in=target.content_types.all()).values("permission_id", "source_id").distinct()
        if len(references) == 0:
            # If there are no Entitlements to extrude, we have to do a bit more work.
            for source in self.sources():
                for permission in self.allow_permissions.all():
                    new_entitlements.append(
                        Entitlement(
                            policy=self,
                            source=source,
                            permission=permission,
                            target=target
                        )
                    )
        for d in references:
            new_entitlements.append(
                Entitlement(
                    policy=self,
                    source=d["source_id"],
                    permission_id=d["permission_id"],
                    target=target,
                )
            )
        return new_entitlements

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.create_entitlements()

    def __str__(self):
        return f"[{self.domain}] {self.label}"

    class Meta:
        verbose_name_plural = "policies"
        constraints = [
            models.UniqueConstraint(fields=["label", "domain"], name="%(app_label)s_%(class)s_unique")
        ]


class Entitlement(models.Model):
    """
    A generated Entitlement based on a policy; do not edit!
    """
    source = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="entitlements_as_source",
        editable=False,
    )
    permission = models.ForeignKey(
        "auth.Permission",
        on_delete=models.CASCADE,
        related_name="entitlements",
        editable=False,
    )
    target = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="entitlements_as_target",
        editable=False,
    )

    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name="entitlements",
    )

    def __str__(self):
        return f"{self.policy} ({self.id})"
    
    class Meta:
        indexes = [
            models.Index(fields=["source", "permission", "target"])
        ]
        constraints = [
            models.UniqueConstraint(fields=["source", "permission", "target", "policy"], name="%(app_label)s_%(class)s_unique")
        ]