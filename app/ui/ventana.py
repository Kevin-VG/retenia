"""Ventana principal: barra lateral de navegación + vistas apiladas."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app import APP_NAME, __version__, rutas
from app.ui.vista_acerca import VistaAcerca
from app.ui.vista_evaluar import VistaEvaluar
from app.ui.vista_historial import VistaHistorial
from app.ui.vista_lote import VistaLote

# (texto, clave, icono); «Acerca de» va aparte, al pie de la barra lateral
SECCIONES = [
    ("Evaluar estudiante", "evaluar", "evaluar.svg"),
    ("Evaluar desde archivo", "lote", "archivo.svg"),
    ("Historial", "historial", "historial.svg"),
]
CLAVES = [c for _, c, _ in SECCIONES] + ["acerca"]


def _icono(nombre: str) -> QIcon:
    ruta = rutas.ICONOS / nombre
    return QIcon(str(ruta)) if ruta.exists() else QIcon()


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
        for clave in CLAVES:
            self.pila.addWidget(self.vistas[clave])

        self.vistas["evaluar"].historial_cambiado.connect(self.vistas["historial"].refrescar)
        self.vistas["lote"].historial_cambiado.connect(self.vistas["historial"].refrescar)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._barra_lateral())
        lay.addWidget(self.pila, 1)
        self.setCentralWidget(central)
        self.statusBar().hide()

    def _barra_lateral(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraLateral")
        barra.setFixedWidth(240)
        lay = QVBoxLayout(barra)
        lay.setContentsMargins(16, 22, 16, 16)
        lay.setSpacing(6)

        marca = QLabel(APP_NAME)
        marca.setObjectName("marca")
        lema = QLabel("Alerta temprana de deserción")
        lema.setObjectName("lema")
        lay.addWidget(marca)
        lay.addWidget(lema)
        lay.addSpacing(18)

        self.menu = QListWidget()
        self.menu.setObjectName("menu")
        self.menu.setIconSize(QSize(18, 18))
        self.menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for texto, clave, icono in SECCIONES:
            item = QListWidgetItem(_icono(icono), texto)
            item.setData(Qt.ItemDataRole.UserRole, clave)
            self.menu.addItem(item)
        self.menu.currentRowChanged.connect(self._fila_menu)
        lay.addWidget(self.menu, 1)

        self.btn_acerca = QPushButton(_icono("acerca.svg"), "  Acerca de y ajustes")
        self.btn_acerca.setObjectName("enlaceLateral")
        self.btn_acerca.setCheckable(True)
        self.btn_acerca.setIconSize(QSize(16, 16))
        self.btn_acerca.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_acerca.clicked.connect(lambda: self.ir_a("acerca"))
        lay.addWidget(self.btn_acerca)

        privacidad = QLabel("Los datos se procesan y guardan solo en este equipo.")
        privacidad.setObjectName("chipPrivacidad")
        privacidad.setWordWrap(True)
        lay.addWidget(privacidad)
        version = QLabel(f"Versión {__version__}")
        version.setObjectName("lema")
        lay.addWidget(version)

        self.menu.setCurrentRow(0)
        return barra

    def _fila_menu(self, fila: int) -> None:
        if fila >= 0:
            self.pila.setCurrentIndex(fila)
            self.btn_acerca.setChecked(False)

    def ir_a(self, clave: str) -> None:
        if clave == "acerca":
            self.menu.setCurrentRow(-1)
            self.menu.clearSelection()
            self.pila.setCurrentIndex(CLAVES.index("acerca"))
            self.btn_acerca.setChecked(True)
        else:
            self.menu.setCurrentRow(CLAVES.index(clave))
