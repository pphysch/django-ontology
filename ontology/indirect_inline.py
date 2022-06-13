#MIT License
#
#Copyright (c) 2020 Ben Homnick, (c) 2022 Paul Fischer
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

# NOTE: This file can hopefully be removed once Django gets support for truly generic Inline Admin models.

import functools
from django.contrib import admin
from django import forms
from django import db
from django.utils.text import get_text_list
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

class IndirectInlineModelAdmin(admin.options.InlineModelAdmin):
    class Checks(admin.checks.InlineModelAdminChecks):
        def _check_exclude_of_parent_model(self, obj, parent_model):
            return list()

        def _check_relation(self, obj, parent_model):
            return list()

    class FormSet(forms.models.BaseModelFormSet):
        def __init__(self, instance=None, save_as_new=None, **kwargs):
            self.instance = instance
            super().__init__(**kwargs)
            self.queryset = self.real_queryset

        @classmethod
        def get_default_prefix(cls):
            opts = cls.model._meta
            return (
                opts.app_label + '-' + opts.model_name
            )

        def save_new(self, form, commit=True):
            obj = super().save_new(form, commit=False)
            self.save_new_instance(self.instance, obj)
            if commit:
                obj.save()
            return obj

    checks_class = Checks
    formset = FormSet

    @staticmethod
    def formset_factory(
        model, obj=None,
        queryset=None,
        formset=FormSet,
        save_new_instance=None,
        **kwargs
    ):
        FormSet = forms.modelformset_factory(model, formset=formset, **kwargs)
        FormSet.real_queryset = queryset
        FormSet.save_new_instance = save_new_instance
        return FormSet

    def get_form_queryset(self, obj):
        raise NotImplementedError()

    def save_new_instance(self, parent, instance):
        raise NotImplementedError()

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            self.update_instance(formset.instance, instance)
            instance.save()
        formset.save_m2m()

    def get_formset(self, request, obj=None, **kwargs):
        """Return a BaseInlineFormSet class for use in admin add/change views."""
        if "fields" in kwargs:
            fields = kwargs.pop("fields")
        else:
            fields = admin.options.flatten_fieldsets(self.get_fieldsets(request, obj))
        excluded = self.get_exclude(request, obj)
        exclude = [] if excluded is None else list(excluded)
        exclude.extend(self.get_readonly_fields(request, obj))
        if excluded is None and hasattr(self.form, "_meta") and self.form._meta.exclude:
            # Take the custom ModelForm's Meta.exclude into account only if the
            # InlineModelAdmin doesn't define its own.
            exclude.extend(self.form._meta.exclude)
        # If exclude is an empty list we use None, since that's the actual
        # default.
        exclude = exclude or None
        can_delete = self.can_delete and self.has_delete_permission(request, obj)
        queryset = self.model.objects.none()
        if obj:
            queryset = self.get_form_queryset(obj)
        defaults = {
            "form": self.form,
            "formset": self.formset,
            "fields": fields,
            "exclude": exclude,
            "formfield_callback": functools.partial(self.formfield_for_dbfield, request=request),
            "extra": self.get_extra(request, obj, **kwargs),
            "min_num": self.get_min_num(request, obj, **kwargs),
            "max_num": self.get_max_num(request, obj, **kwargs),
            "can_delete": can_delete,
            "queryset": queryset,
            **kwargs,
        }

        base_model_form = defaults["form"]
        can_change = self.has_change_permission(request, obj) if request else True
        can_add = self.has_add_permission(request, obj) if request else True

        class DeleteProtectedModelForm(base_model_form):
            def hand_clean_DELETE(self):
                """
                We don't validate the 'DELETE' field itself because on
                templates it's not rendered using the field information, but
                just using a generic "deletion_field" of the InlineModelAdmin.
                """
                if self.cleaned_data.get(forms.formsets.DELETION_FIELD_NAME, False):
                    using = db.router.db_for_write(self._meta.model)
                    collector = admin.utils.NestedObjects(using=using)
                    if self.instance._state.adding:
                        return
                    collector.collect([self.instance])
                    if collector.protected:
                        objs = []
                        for p in collector.protected:
                            objs.append(
                                # Translators: Model verbose name and instance
                                # representation, suitable to be an item in a
                                # list.
                                _("%(class_name)s %(instance)s")
                                % {"class_name": p._meta.verbose_name, "instance": p}
                            )
                        params = {
                            "class_name": self._meta.model._meta.verbose_name,
                            "instance": self.instance,
                            "related_objects": get_text_list(objs, _("and")),
                        }
                        msg = _(
                            "Deleting %(class_name)s %(instance)s would require "
                            "deleting the following protected related objects: "
                            "%(related_objects)s"
                        )
                        raise ValidationError(
                            msg, code="deleting_protected", params=params
                        )

            def is_valid(self):
                result = super().is_valid()
                self.hand_clean_DELETE()
                return result

            def has_changed(self):
                # Protect against unauthorized edits.
                if not can_change and not self.instance._state.adding:
                    return False
                if not can_add and self.instance._state.adding:
                    return False
                return super().has_changed()

        defaults["form"] = DeleteProtectedModelForm

        if defaults["fields"] is None and not forms.models.modelform_defines_fields(
            defaults["form"]
        ):
            defaults["fields"] = forms.ALL_FIELDS

        return IndirectInlineModelAdmin.formset_factory(
            self.model,
            save_new_instance=self.save_new_instance,
            **defaults
        )

class IndirectStackedInline(IndirectInlineModelAdmin):
    template = "admin/edit_inline/stacked.html"