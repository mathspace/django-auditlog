from __future__ import unicode_literals

import threading

from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
from django.db.models import Model


user_settings = getattr(settings, 'AUDITLOG', {
    'disable_auditlog': False
})


class FlagLocals(threading.local):
    enable_all = user_settings.get('enable_all', True)
    enable_create = user_settings.get('enable_create', True)
    enable_update = user_settings.get('enable_update', True)
    enable_delete = user_settings.get('enable_delete', True)


class AuditlogModelRegistry(object):
    """
    A registry that keeps track of the models that use Auditlog to track changes.
    """
    def __init__(self, create=True, update=True, delete=True, custom=None):
        from auditlog.receivers import log_create, log_update, log_delete

        self._registry = {}
        self._signals = {}

        if user_settings.get('disable_auditlog', False):
            return

        self.flag = FlagLocals()
        self.flag.enable_all = bool(create) and bool(update) and bool(delete)
        self.flag.enable_create = bool(create)
        self.flag.enable_update = bool(update)
        self.flag.enable_delete = bool(delete)

        if create:
            self._signals[post_save] = log_create
        if update:
            self._signals[pre_save] = log_update
        if delete:
            self._signals[post_delete] = log_delete

        if custom is not None:
            self._signals.update(custom)

    def register(self, model=None, include_fields=[], exclude_fields=[], mapping_fields={}):
        """
        Register a model with auditlog. Auditlog will then track mutations on this model's instances.

        :param model: The model to register.
        :type model: Model
        :param include_fields: The fields to include. Implicitly excludes all other fields.
        :type include_fields: list
        :param exclude_fields: The fields to exclude. Overrides the fields to include.
        :type exclude_fields: list
        """
        def registrar(cls):
            """Register models for a given class."""
            if not issubclass(cls, Model):
                raise TypeError("Supplied model is not a valid model.")

            self._registry[cls] = {
                'include_fields': include_fields,
                'exclude_fields': exclude_fields,
                'mapping_fields': mapping_fields,
            }
            self._connect_signals(cls)

            # We need to return the class, as the decorator is basically
            # syntactic sugar for:
            # MyClass = auditlog.register(MyClass)
            return cls

        if model is None:
            # If we're being used as a decorator, return a callable with the
            # wrapper.
            return lambda cls: registrar(cls)
        else:
            # Otherwise, just register the model.
            registrar(model)

    def contains(self, model):
        """
        Check if a model is registered with auditlog.

        :param model: The model to check.
        :type model: Model
        :return: Whether the model has been registered.
        :rtype: bool
        """
        return model in self._registry

    def unregister(self, model):
        """
        Unregister a model with auditlog. This will not affect the database.

        :param model: The model to unregister.
        :type model: Model
        """
        try:
            del self._registry[model]
        except KeyError:
            pass
        else:
            self._disconnect_signals(model)

    def disable_signals(self, disconnect=False):
        self.flag.enable_all = False

        if disconnect:
            for cls in self._registry:
                self._disconnect_signals(cls)

    def enable_signals(self, reconnect=False):
        self.flag.enable_all = True

        if reconnect:
            for cls in self._registry:
                self._connect_signals(cls)

    @property
    def can_create(self):
        return self.flag.enable_create and self.flag.enable_all

    @can_create.setter
    def can_create(self, value: bool):
        self.flag.enable_create = bool(value)

    @property
    def can_update(self):
        return self.flag.enable_update and self.flag.enable_all

    @can_update.setter
    def can_update(self, value: bool):
        self.flag.enable_update = bool(value)

    @property
    def can_delete(self):
        return self.flag.enable_delete and self.flag.enable_all

    @can_delete.setter
    def can_delete(self, value: bool):
        self.flag.enable_delete = bool(value)

    def _connect_signals(self, model):
        """
        Connect signals for the model.
        """
        if user_settings.get('disable_auditlog', False):
            return

        for signal in self._signals:
            receiver = self._signals[signal]
            signal.connect(receiver, sender=model, dispatch_uid=self._dispatch_uid(signal, model))

    def _disconnect_signals(self, model):
        """
        Disconnect signals for the model.
        """
        if user_settings.get('disable_auditlog', False):
            return

        for signal, receiver in self._signals.items():
            signal.disconnect(sender=model, dispatch_uid=self._dispatch_uid(signal, model))

    def _dispatch_uid(self, signal, model):
        """
        Generate a dispatch_uid.
        """
        return (self.__class__, model, signal)

    def get_model_fields(self, model):
        return {
            'include_fields': self._registry[model]['include_fields'],
            'exclude_fields': self._registry[model]['exclude_fields'],
            'mapping_fields': self._registry[model]['mapping_fields'],
        }


class AuditLogModelRegistry(AuditlogModelRegistry):
    def __init__(self, *args, **kwargs):
        super(AuditLogModelRegistry, self).__init__(*args, **kwargs)
        raise DeprecationWarning("Use AuditlogModelRegistry instead of AuditLogModelRegistry, AuditLogModelRegistry will be removed in django-auditlog 0.4.0 or later.")


auditlog = AuditlogModelRegistry()
