"""Client-independent cooperative cancellation and safe local result paths."""
from pathlib import Path
from threading import Event


class OperationCancelled(RuntimeError):
    """Raised only at a transaction's explicitly safe boundaries."""


class CancellationToken:
    def __init__(self):
        self._requested = Event()

    def request(self) -> None:
        self._requested.set()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()

    def checkpoint(self) -> None:
        if self.requested:
            raise OperationCancelled("Operazione annullata al punto sicuro")


def safe_result_path(workspace: Path, value: str | Path, *, authorized_roots=()) -> Path:
    text = str(value)
    if not text or "://" in text or "\x00" in text:
        raise ValueError("È richiesto un percorso locale, non un URL o un comando")
    path = Path(text).expanduser()
    if ":" in str(path).removeprefix(path.drive):
        raise ValueError("Percorso non consentito")
    path = (path if path.is_absolute() else workspace / path).resolve(strict=True)
    roots = (workspace, *authorized_roots)
    if not any(path.is_relative_to(Path(root).resolve()) for root in roots):
        raise ValueError("Risultato esterno alla workspace e non autorizzato")
    if path.is_file() and path.suffix.lower() not in {
        ".md", ".txt", ".log", ".json", ".csv", ".pdf", ".png", ".jpg", ".svg",
        ".gpkg", ".parquet", ".yaml", ".yml",
    }:
        raise ValueError("Tipo di risultato non consentito")
    if not path.is_file() and not path.is_dir():
        raise ValueError("Risultato non apribile")
    return path
