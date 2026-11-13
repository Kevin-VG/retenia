import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# Archivo en el formato completo anterior (36 columnas, nombres originales y códigos)
LOTE_COMPLETO = Path(__file__).parent / "datos" / "lote_formato_completo.csv"


@pytest.fixture(scope="session", autouse=True)
def carpeta_datos_temporal(tmp_path_factory):
    """Preferencias y datos de la app en una carpeta temporal, no en %APPDATA%."""
    os.environ["RETENIA_DATA_DIR"] = str(tmp_path_factory.mktemp("datos_retenia"))


@pytest.fixture(scope="session")
def servicio():
    from app.services.modelo import ServicioModelo
    return ServicioModelo()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def historial(tmp_path):
    from app.services.historial import Historial
    return Historial(tmp_path / "historial.db")
