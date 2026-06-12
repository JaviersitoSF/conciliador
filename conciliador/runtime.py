import logging
from logging.handlers import RotatingFileHandler

from .database import Database
from .paths import AppPaths


def configure_logging(paths):
    paths.ensure_directories()
    logger = logging.getLogger("conciliador")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        paths.log_file,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger


def prepare_application(base_dir=None):
    from . import printing, storage

    paths = AppPaths.portable(base_dir)
    logger = configure_logging(paths)
    logger.info("Iniciando Conciliador")
    printing.configure_paths(paths)
    storage.configure_paths(paths)
    database = Database(paths, logger)
    version = database.initialize()
    storage.inicializar_db()
    return paths, logger, version
