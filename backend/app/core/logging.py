import logging
import sys
from pathlib import Path

from app.core.config import settings


def setup_logging():
    """Configura el sistema de logging para la aplicación."""
    
    # Crear directorio de logs si no existe
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configuración básica
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),  # Salida a consola
            # File-based logging. In containerized environments, logging to stdout (StreamHandler above) is often preferred.
            # This FileHandler can be made optional or configurable based on deployment strategy.
            logging.FileHandler(log_dir / "app.log")  # Archivo de log
        ]
    )
    
    # Reducir verbosidad de algunos loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Logger personalizado para la aplicación
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    
    return logger