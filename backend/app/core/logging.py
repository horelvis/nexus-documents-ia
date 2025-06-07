import logging
import sys
from pathlib import Path

from app.core.config import settings


def setup_logging():
    """Configura el sistema de logging para la aplicación."""
    
    # Crear directorio de logs si no existe
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Determinar nivel de logging basado en DEBUG setting
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # Configuración básica
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),  # Salida a consola
            # File-based logging. In containerized environments, logging to stdout (StreamHandler above) is often preferred.
            # This FileHandler can be made optional or configurable based on deployment strategy.
            logging.FileHandler(log_dir / "app.log")  # Archivo de log
        ]
    )
    
    # Configurar loggers específicos para auth debugging
    auth_loggers = [
        "app.api.dependencies",
        "app.services.auth_service", 
        "app.api.v1.auth",
        "app.main"
    ]
    
    for logger_name in auth_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    
    # Reducir verbosidad de algunos loggers (solo si no estamos en DEBUG)
    if not settings.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    else:
        # En DEBUG, mostrar más info de uvicorn
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    
    # Logger personalizado para la aplicación
    logger = logging.getLogger("app")
    logger.setLevel(log_level)
    
    return logger


def enable_auth_debug():
    """Activa logging DEBUG específicamente para componentes de autenticación."""
    auth_loggers = [
        "app.api.dependencies",
        "app.services.auth_service", 
        "app.api.v1.auth",
        "app.main"
    ]
    
    print("🔧 Activating DEBUG logging for authentication components...")
    
    for logger_name in auth_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        print(f"   ✅ {logger_name} set to DEBUG")
    
    print("🔧 Debug logging activated!")


def disable_auth_debug():
    """Desactiva logging DEBUG y vuelve a INFO para componentes de autenticación."""
    auth_loggers = [
        "app.api.dependencies",
        "app.services.auth_service", 
        "app.api.v1.auth",
        "app.main"
    ]
    
    print("🔧 Disabling DEBUG logging for authentication components...")
    
    for logger_name in auth_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        print(f"   ✅ {logger_name} set to INFO")
    
    print("🔧 Debug logging disabled!")


def get_logger_with_debug(name: str) -> logging.Logger:
    """
    Obtiene un logger y opcionalmente lo configura en DEBUG si DEBUG=true.
    Uso: logger = get_logger_with_debug(__name__)
    """
    logger = logging.getLogger(name)
    
    # Si DEBUG está activado, configurar este logger en DEBUG
    if settings.DEBUG:
        logger.setLevel(logging.DEBUG)
    
    return logger