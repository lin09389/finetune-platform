from .process import ProcessOperations
from .service import ServiceOperations
from .environment import EnvironmentOperations
from .info import SystemInfoOperations

ProcessManager = ProcessOperations
ServiceManager = ServiceOperations

__all__ = [
    "ProcessOperations",
    "ServiceOperations",
    "EnvironmentOperations",
    "SystemInfoOperations",
    "ProcessManager",
    "ServiceManager",
]
