"""A single operation per worker; only queued signals cross into widgets."""
from dataclasses import asdict

from PySide6.QtCore import QThread, Signal

from ..application import ApplicationService
from ..operation import CancellationToken, OperationCancelled


class ServiceWorker(QThread):
    result = Signal(object)
    error = Signal(str)
    event = Signal(object)

    def __init__(self, workspace, operation, *, paths=None, check=None, read_only=False, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.operation = operation
        self.paths = paths
        self.check = check
        self.read_only = read_only
        self.token = CancellationToken()

    def run(self):
        try:
            service = ApplicationService(self.workspace, self.event.emit,
                                         cancellation=self.token, read_only=self.read_only)
            if self.operation == "overview":
                value = {"doctor": service.doctor(), "status": service.status(), "history": service.history()}
            elif self.operation == "discover":
                value = {"results": [asdict(i) for i in service.discover(self.paths, include_registered=False)]}
            elif self.operation == "check":
                value = service.check(self.paths, new_only=True)
            elif self.operation == "prepare":
                service.validate_check(self.check)
                if service.lock_status():
                    raise ValueError("Workspace bloccata")
                value = self.check
            elif self.operation == "apply":
                value = service.apply(check=self.check)
            else:
                raise ValueError(f"Operazione sconosciuta: {self.operation}")
            self.result.emit(value)
        except OperationCancelled:
            self.result.emit({"status": "cancelled"})
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
