from __future__ import unicode_literals

import json
import logging

from auditlog.diff import model_instance_diff
from auditlog.models import LogEntry


def log_create(sender, instance, created, **kwargs):
    """
    Signal receiver that creates a log entry when a model instance is first saved to the database.

    Direct use is discouraged, connect your model through :py:func:`auditlog.registry.register` instead.
    """
    from auditlog.registry import auditlog

    if created and auditlog.can_create:
        changes = model_instance_diff(None, instance)

        log_entry = LogEntry.objects.log_create(
            instance,
            action=LogEntry.Action.CREATE,
            changes=json.dumps(changes),
        )


def log_update(sender, instance, **kwargs):
    """
    Signal receiver that creates a log entry when a model instance is changed and saved to the database.

    Direct use is discouraged, connect your model through :py:func:`auditlog.registry.register` instead.
    """
    from auditlog.registry import auditlog

    if instance.pk is not None and auditlog.can_update:
        try:
            old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            pass
        else:
            new = instance

            changes = model_instance_diff(old, new)

            # Log an entry only if there are changes
            if changes:
                log_entry = LogEntry.objects.log_create(
                    instance,
                    action=LogEntry.Action.UPDATE,
                    changes=json.dumps(changes),
                )


def log_delete(sender, instance, **kwargs):
    """
    Signal receiver that creates a log entry when a model instance is deleted from the database.

    Direct use is discouraged, connect your model through :py:func:`auditlog.registry.register` instead.
    """
    from auditlog.registry import auditlog

    if instance.pk is not None and auditlog.can_delete:
        changes = model_instance_diff(instance, None)

        log_entry = LogEntry.objects.log_create(
            instance,
            action=LogEntry.Action.DELETE,
            changes=json.dumps(changes),
        )


def log_m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if 'post_' in action and pk_set:
        try:
            action_suffix = action.replace('post_', '')
            action_enum = {
                'add': LogEntry.Action.UPDATE,
                'clear': LogEntry.Action.UPDATE,
                'remove': LogEntry.Action.UPDATE,
            }[action_suffix]

            parents = model.objects.filter(pk__in=pk_set).all()
            children = [instance]

            for parent in parents:
                for child in children:
                    log_entry = LogEntry.objects.log_create(
                        parent,
                        action=action_enum,
                        changes=json.dumps({
                            'id': (
                                child.pk if action_suffix == 'add' else parent.pk,
                                parent.pk if action_suffix == 'add' else child.pk,
                            ),
                            action_suffix: (
                                str(child) if action_suffix == 'add' else str(parent),
                                str(parent) if action_suffix == 'add' else str(child),
                            ),
                            'type': (
                                str(child.__class__.__name__) if action_suffix == 'add' else str(parent.__class__.__name__),
                                str(parent.__class__.__name__) if action_suffix == 'add' else str(child.__class__.__name__),
                            ),
                            'through': (
                                sender._meta.model_name,
                                None
                            )
                        }),
                    )
        except Exception:
            logging.exception("Unable to log m2m auditlog")
