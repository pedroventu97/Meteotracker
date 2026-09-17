"""Workers use exactly the service passed by the main window."""
from PySide6.QtCore import QThread, Signal
from ..operation import CancellationToken, OperationCancelled


class AnalysisWorker(QThread):
    result = Signal(object)
    error = Signal(str)
    event = Signal(object)

    def __init__(self, service, operation, *, generation=0, kwargs=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.operation = operation
        self.generation = generation
        self.kwargs = kwargs or {}
        self.token = CancellationToken()

    def run(self):
        try:
            method = getattr(self.service, self.operation)
            value = method(**self.kwargs, cancellation=self.token, **({"emit": self.event.emit} if self.operation in {"preview_qc", "preview_tracks"} else {}))
            self.result.emit(value)
        except OperationCancelled:
            self.result.emit({"status": "cancelled"})
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
