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


def prepare_application(core, base_dir=None):
    paths = AppPaths.portable(base_dir)
    logger = configure_logging(paths)
    logger.info("Iniciando Conciliador")
    core.ARCHIVO_DATOS = str(paths.database)
    core.DIRECTORIO_RESPALDOS = str(paths.data_dir / "operation_backups")
    database = Database(paths, logger)
    version = database.initialize()
    # La fachada existente garantiza que la cuenta inicial y su formato existan.
    core.inicializar_db()
    return paths, logger, version
