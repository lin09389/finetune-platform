from .environment import EnvironmentOperations
from .info import SystemInfoOperations
from .process import ProcessOperations
from .service import ServiceOperations

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
