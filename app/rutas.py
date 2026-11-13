"""Rutas de recursos (empaquetados) y de datos del usuario (escribibles)."""
import os
import sys
from pathlib import Path

from app import APP_NAME

# En el ejecutable de PyInstaller los recursos viven en sys._MEIPASS
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
RECURSOS = _BASE / "app" / "resources"
MODELO = RECURSOS / "model" / "pipeline_ganador.joblib"
CONFIG = RECURSOS / "model" / "config.json"
PLANTILLA_LOTE = RECURSOS / "plantilla_lote.csv"
ICONO = RECURSOS / "icon.ico"
ICONO_PNG = RECURSOS / "icon.png"
ESTILOS = RECURSOS / "estilos.qss"


def carpeta_datos() -> Path:
    """Carpeta escribible del usuario: %APPDATA%/RetenIA (o la variable RETENIA_DATA_DIR)."""
    ruta = os.environ.get("RETENIA_DATA_DIR")
    if ruta:
        base = Path(ruta)
    else:
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def hoja_estilos() -> str:
    """QSS con las rutas de imágenes resueltas (funciona igual en desarrollo y en el .exe)."""
    if not ESTILOS.exists():
        return ""
    return ESTILOS.read_text(encoding="utf-8").replace("@RECURSOS@", RECURSOS.as_posix())
