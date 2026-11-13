"""Ventana principal: barra lateral de navegación + vistas apiladas."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QStackedWidget,
    QVBoxLayout, QWidget,
)

from app import APP_NAME, __version__, rutas
from app.ui.vista_acerca import VistaAcerca
from app.ui.vista_evaluar import VistaEvaluar
from app.ui.vista_historial import VistaHistorial
from app.ui.vista_lote import VistaLote

SECCIONES = [
    ("Evaluar estudiante", "evaluar"),
    ("Carga por lote", "lote"),
    ("Historial", "historial"),
    ("Acerca de", "acerca"),
]


class VentanaPrincipal(QMainWindow):
    def __init__(self, servicio, historial):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Alerta temprana de deserción")
        if rutas.ICONO.exists():
            self.setWindowIcon(QIcon(str(rutas.ICONO)))
        self.resize(1360, 880)
        self.setMinimumSize(1100, 720)

        self.vistas = {
            "evaluar": VistaEvaluar(servicio, historial),
            "lote": VistaLote(servicio, historial),
            "historial": VistaHistorial(servicio, historial),
            "acerca": VistaAcerca(servicio, historial),
        }
        self.pila = QStackedWidget()
        for vista in self.vistas.values():
            self.pila.addWidget(vista)

        self.vistas["evaluar"].historial_cambiado.connect(self.vistas["historial"].refrescar)
        self.vistas["lote"].historial_cambiado.connect(self.vistas["historial"].refrescar)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._barra_lateral(servicio))
        lay.addWidget(self.pila, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage(
            f"Modelo {servicio.nombre_modelo} · umbral {servicio.umbral:.2f} · "
            f"historial: {historial.ruta}"
        )

    def _barra_lateral(self, servicio) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraLateral")
        barra.setFixedWidth(240)
        lay = QVBoxLayout(barra)
        lay.setContentsMargins(16, 22, 16, 16)
        lay.setSpacing(6)

        marca = QLabel(f"{APP_NAME}")
        marca.setObjectName("marca")
        lema = QLabel("Alerta temprana de deserción")
        lema.setObjectName("lema")
        lay.addWidget(marca)
        lay.addWidget(lema)
        lay.addSpacing(18)

        self.menu = QListWidget()
        self.menu.setObjectName("menu")
        self.menu.setIconSize(QSize(18, 18))
        self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for texto, clave in SECCIONES:
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, clave)
            self.menu.addItem(item)
        self.menu.currentRowChanged.connect(self.pila.setCurrentIndex)
        self.menu.setCurrentRow(0)
        lay.addWidget(self.menu, 1)

        chip = QLabel(f"{servicio.nombre_modelo}\nUmbral operativo {servicio.umbral:.2f}")
        chip.setObjectName("chipModelo")
        lay.addWidget(chip)
        version = QLabel(f"v{__version__} · sin conexión")
        version.setObjectName("lema")
        lay.addWidget(version)
        return barra

    def ir_a(self, clave: str) -> None:
        self.menu.setCurrentRow([c for _, c in SECCIONES].index(clave))
