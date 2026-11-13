"""Componentes reutilizables de la interfaz."""
import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

COLOR_ESTADO = {"Rojo": "#d03b3b", "Amarillo": "#e0a106", "Verde": "#0c8a0c"}
FONDO_ESTADO = {"Rojo": "#fdecec", "Amarillo": "#fff6dd", "Verde": "#e8f6e8"}
ICONO_ESTADO = {"Rojo": "●", "Amarillo": "●", "Verde": "●"}
NOMBRE_ESTADO = {"Rojo": "Riesgo alto", "Amarillo": "Riesgo moderado", "Verde": "Riesgo bajo"}

ROL_ORDEN = Qt.ItemDataRole.UserRole + 1


class Tarjeta(QFrame):
    """Contenedor blanco con borde redondeado (estilo en estilos.qss)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self.cuerpo = QVBoxLayout(self)
        self.cuerpo.setContentsMargins(18, 16, 18, 16)
        self.cuerpo.setSpacing(8)


class TarjetaKPI(Tarjeta):
    def __init__(self, titulo: str, valor: str = "—", color: str | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.titulo = QLabel(titulo)
        self.titulo.setObjectName("kpiTitulo")
        self.valor = QLabel(valor)
        self.valor.setObjectName("kpiValor")
        if color:
            self.valor.setStyleSheet(f"color: {color};")
        self.cuerpo.addWidget(self.titulo)
        self.cuerpo.addWidget(self.valor)

    def set_valor(self, valor: str) -> None:
        self.valor.setText(valor)


def titulo_seccion(texto: str, subtitulo: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 4)
    lay.setSpacing(2)
    t = QLabel(texto)
    t.setObjectName("tituloVista")
    lay.addWidget(t)
    if subtitulo:
        s = QLabel(subtitulo)
        s.setObjectName("subtituloVista")
        s.setWordWrap(True)
        lay.addWidget(s)
    return w


class ModeloTabla(QAbstractTableModel):
    """Modelo de solo lectura sobre un DataFrame.

    `formatos` mapea columna -> función(valor) -> str para mostrar.
    Las columnas 'Semáforo' y 'Prob. Deserción' se colorean según el estado.
    """

    def __init__(self, df: pd.DataFrame | None = None, encabezados: dict | None = None,
                 formatos: dict | None = None, parent=None):
        super().__init__(parent)
        self.encabezados = encabezados or {}
        self.formatos = formatos or {}
        self.set_df(df if df is not None else pd.DataFrame())

    def set_df(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self.df = df.reset_index(drop=True)
        self._columnas = list(self.df.columns)
        self._valores = self.df.to_numpy(dtype=object)
        self._idx_semaforo = self._columnas.index("Semáforo") if "Semáforo" in self._columnas else None
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._valores)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._columnas)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        valor = self._valores[index.row(), index.column()]
        col = self._columnas[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if col in self.formatos:
                return self.formatos[col](valor)
            if isinstance(valor, (float, np.floating)):
                return f"{valor:g}"
            return "" if valor is None else str(valor)
        if role == ROL_ORDEN:
            return valor.item() if isinstance(valor, np.generic) else valor
        if self._idx_semaforo is not None and col in ("Semáforo", "Prob. Deserción"):
            estado = self._valores[index.row(), self._idx_semaforo]
            if role == Qt.ItemDataRole.ForegroundRole:
                return QBrush(QColor(COLOR_ESTADO.get(estado, "#0c1938")))
            if role == Qt.ItemDataRole.BackgroundRole and col == "Semáforo":
                return QBrush(QColor(FONDO_ESTADO.get(estado, "#ffffff")))
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(valor, (int, float, np.number)):
            # Números puros a la derecha; valores traducidos a texto (carrera, Sí/No) a la izquierda
            if col in self.formatos and col != "Prob. Deserción":
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, seccion, orientacion, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientacion == Qt.Orientation.Horizontal:
            col = self._columnas[seccion]
            return self.encabezados.get(col, col)
        return str(seccion + 1)

    def fila(self, fila: int) -> pd.Series:
        return self.df.iloc[fila]


class FiltroTabla(QSortFilterProxyModel):
    """Filtra por semáforo y por texto en columnas dadas; ordena por el valor real."""

    def __init__(self, columnas_texto: list[str], parent=None):
        super().__init__(parent)
        self.columnas_texto = columnas_texto
        self.semaforo: str | None = None
        self.texto = ""
        self.setSortRole(ROL_ORDEN)

    def set_semaforo(self, semaforo: str | None) -> None:
        self.beginFilterChange()
        self.semaforo = semaforo
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_texto(self, texto: str) -> None:
        self.beginFilterChange()
        self.texto = texto.strip().lower()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, fila, padre):
        modelo: ModeloTabla = self.sourceModel()
        df = modelo.df
        if self.semaforo and "Semáforo" in df.columns and df["Semáforo"].iat[fila] != self.semaforo:
            return False
        if self.texto:
            return any(
                self.texto in str(df[c].iat[fila]).lower()
                for c in self.columnas_texto if c in df.columns
            )
        return True

    def lessThan(self, izq, der):
        a, b = izq.data(ROL_ORDEN), der.data(ROL_ORDEN)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


def porcentaje(valor) -> str:
    return f"{float(valor) * 100:.1f} %"


def semaforo_texto(valor) -> str:
    return f"{ICONO_ESTADO.get(valor, '')} {valor}"
