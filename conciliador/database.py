import sqlite3
from contextlib import contextmanager

from .migrations import migrate


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, paths, logger=None):
        self.paths = paths
        self.logger = logger

    def connect(self):
        self.paths.ensure_directories()
        connection = sqlite3.connect(
            self.paths.database,
            timeout=10,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def initialize(self):
        with self.connect() as connection:
            version = migrate(
                connection,
                self.paths.database,
                self.paths.migration_backups,
                self.logger,
            )
        if self.logger:
            self.logger.info(
                "Base de datos: %s; esquema: %s", self.paths.database, version
            )
        return version

    @contextmanager
    def transaction(self):
        self.initialize()
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
