import sys
from dataclasses import dataclass
from pathlib import Path


def executable_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path

    @classmethod
    def portable(cls, base_dir=None):
        return cls(Path(base_dir).resolve() if base_dir else executable_directory())

    @property
    def data_dir(self):
        return self.base_dir / "data"

    @property
    def database(self):
        return self.data_dir / "conciliador.db"

    @property
    def migration_backups(self):
        return self.data_dir / "migration_backups"

    @property
    def logs_dir(self):
        return self.base_dir / "logs"

    @property
    def log_file(self):
        return self.logs_dir / "conciliador.log"

    @property
    def exports_dir(self):
        return self.base_dir / "exports"

    def ensure_directories(self):
        for directory in (
            self.data_dir,
            self.migration_backups,
            self.logs_dir,
            self.exports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
