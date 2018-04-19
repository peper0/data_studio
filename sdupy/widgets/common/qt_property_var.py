from PyQt5.QtCore import QObject

from sdupy.pyreactive.common import Wrapped
from sdupy.pyreactive.forwarder import ConstForwarders, MutatingForwarders
from sdupy.pyreactive.notifier import Notifier


class QtPropertyVar(Wrapped, ConstForwarders, MutatingForwarders):
    def __init__(self, obj: QObject, prop_name: str):
        super().__init__()
        self._notifier = Notifier()
        self.obj = obj
        self.prop_name = prop_name
        obj_meta = obj.staticMetaObject
        prop_meta = obj_meta.property(obj_meta.indexOfProperty(prop_name))
        notify_signal_meta = prop_meta.notifySignal()
        assert notify_signal_meta, "property '{}' has no notifier".format(prop_name)
        notify_signal_name = bytes(notify_signal_meta.name()).decode('utf8')
        assert notify_signal_name, "property '{}' notifier has no name?!".format(prop_name)
        notify_signal = getattr(obj, notify_signal_name)
        notify_signal.connect(self._prop_changed)

    def _prop_changed(self):
        self._notifier.notify_observers()

    def set(self, value):
        self.obj.setProperty(self.prop_name, value)

    def get(self):
        return self.obj.property(self.prop_name)

    @property
    def __notifier__(self):
        return self._notifier

    @property
    def __inner__(self):
        return self.get()
