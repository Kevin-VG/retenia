import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


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
