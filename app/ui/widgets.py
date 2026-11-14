"""Componentes reutilizables de la interfaz."""
import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIntValidator
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

COLOR_ESTADO = {"Rojo": "#c62828", "Amarillo": "#b77900", "Verde": "#0c7a0c"}
FONDO_ESTADO = {"Rojo": "#fdecec", "Amarillo": "#fff6dd", "Verde": "#e8f6e8"}
ICONO_ESTADO = {"Rojo": "●", "Amarillo": "●", "Verde": "●"}
NOMBRE_ESTADO = {"Rojo": "Riesgo alto", "Amarillo": "Riesgo moderado", "Verde": "Riesgo bajo"}
COLOR_NIVEL = {"Error": "#b91c1c", "Advertencia": "#a16207"}
FONDO_NIVEL = {"Error": "#fdecec", "Advertencia": "#fff6dd"}

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
    """Tarjeta de resumen (título + cifra). Si es `pulsable`, emite `pulsada` al hacer clic."""

    pulsada = Signal()

    def __init__(self, titulo: str, valor: str = "—", color: str | None = None,
                 parent: QWidget | None = None, pulsable: bool = False, ayuda: str = ""):
        super().__init__(parent)
        self.setObjectName("kpi")
        self.pulsable = pulsable
        if pulsable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(ayuda)
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

    def set_activa(self, activa: bool) -> None:
        self.setProperty("activa", activa)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, evento):
        if self.pulsable and evento.button() == Qt.MouseButton.LeftButton:
            self.pulsada.emit()
        super().mouseReleaseEvent(evento)


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
        self._idx_nivel = self._columnas.index("Nivel") if "Nivel" in self._columnas else None
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
            if col == "Semáforo":  # ordenar por gravedad, no alfabéticamente
                return {"Verde": 0, "Amarillo": 1, "Rojo": 2}.get(valor, -1)
            return valor.item() if isinstance(valor, np.generic) else valor
        if self._idx_semaforo is not None and col in ("Semáforo", "Prob. Deserción"):
            estado = self._valores[index.row(), self._idx_semaforo]
            if role == Qt.ItemDataRole.ForegroundRole:
                return QBrush(QColor(COLOR_ESTADO.get(estado, "#0c1938")))
            if role == Qt.ItemDataRole.BackgroundRole and col == "Semáforo":
                return QBrush(QColor(FONDO_ESTADO.get(estado, "#ffffff")))
        if self._idx_nivel is not None:
            nivel = self._valores[index.row(), self._idx_nivel]
            if role == Qt.ItemDataRole.ForegroundRole and col in ("Nivel", "Problema"):
                return QBrush(QColor(COLOR_NIVEL.get(nivel, "#0c1938")))
            if role == Qt.ItemDataRole.BackgroundRole and col == "Nivel":
                return QBrush(QColor(FONDO_NIVEL.get(nivel, "#ffffff")))
        if role == Qt.ItemDataRole.ToolTipRole and col in ("Avisos", "Problema") and valor:
            return str(valor)
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
    """Filtra por una columna de estado (Semáforo o Nivel) y por texto; ordena por el valor real."""

    def __init__(self, columnas_texto: list[str], columna_estado: str = "Semáforo", parent=None):
        super().__init__(parent)
        self.columnas_texto = columnas_texto
        self.columna_estado = columna_estado
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
        col = self.columna_estado
        if self.semaforo and col in df.columns and df[col].iat[fila] != self.semaforo:
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
    return f"{ICONO_ESTADO.get(valor, '')} {NOMBRE_ESTADO.get(valor, valor)}"


def mensaje_vacio(texto: str) -> QLabel:
    lbl = QLabel(texto)
    lbl.setObjectName("aviso")
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    return lbl


# ---------------------------------------------------------------------------- campos del formulario
# Todos comparten la misma interfaz: value() (None si está vacío), setValue(), vaciar(),
# set_invalido() y la señal valueChanged.

def _refrescar_estilo(widget, propiedad: str, valor) -> None:
    if widget.property(propiedad) != valor:
        widget.setProperty(propiedad, valor)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class CampoNumero(QWidget):
    """Número entero que puede quedar vacío: [−] [ valor ] [+]. Flechas ↑/↓ también cambian el valor."""

    valueChanged = Signal()

    def __init__(self, minimo: int, maximo: int, parent=None):
        super().__init__(parent)
        self.minimo, self.maximo = minimo, maximo
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.menos = self._boton("−", "Restar 1", -1)
        self.edit = QLineEdit()
        self.edit.setValidator(QIntValidator(minimo, maximo, self))
        self.edit.setPlaceholderText(f"{minimo}–{maximo}")
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.textChanged.connect(lambda *_: self.valueChanged.emit())
        self.edit.installEventFilter(self)
        self.mas = self._boton("+", "Sumar 1", +1)
        lay.addWidget(self.menos)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.mas)
        self.setFocusProxy(self.edit)

    def _boton(self, texto, ayuda, paso) -> QToolButton:
        b = QToolButton()
        b.setText(texto)
        b.setObjectName("paso")
        b.setToolTip(ayuda)
        b.setAutoRepeat(True)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.paso(paso))
        return b

    def eventFilter(self, obj, evento):
        if obj is self.edit and evento.type() == QEvent.Type.KeyPress:
            if evento.key() == Qt.Key.Key_Up:
                self.paso(+1)
                return True
            if evento.key() == Qt.Key.Key_Down:
                self.paso(-1)
                return True
        return super().eventFilter(obj, evento)

    def paso(self, delta: int) -> None:
        actual = self.value()
        nuevo = self.minimo if actual is None else actual + delta
        self.setValue(max(self.minimo, min(self.maximo, nuevo)))

    def value(self) -> int | None:
        texto = self.edit.text().strip()
        return int(texto) if texto.lstrip("-").isdigit() else None

    def setValue(self, valor) -> None:
        self.edit.setText("" if valor is None else str(int(valor)))

    def vaciar(self) -> None:
        self.setValue(None)

    def set_invalido(self, invalido: bool) -> None:
        _refrescar_estilo(self.edit, "invalido", invalido)


class OpcionSiNo(QWidget):
    """Botones excluyentes (por defecto «Sí» / «No»): un clic en vez de abrir una lista."""

    valueChanged = Signal()

    def __init__(self, opciones=(("Sí", 1), ("No", 0)), parent=None):
        super().__init__(parent)
        self.setObjectName("opciones")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.grupo = QButtonGroup(self)
        self.botones = {}
        for texto, valor in opciones:
            b = QPushButton(texto)
            b.setObjectName("opcion")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.grupo.addButton(b)
            self.botones[valor] = b
            lay.addWidget(b, 1)
        self.grupo.buttonToggled.connect(lambda _b, marcado: marcado and self.valueChanged.emit())

    def value(self):
        for valor, b in self.botones.items():
            if b.isChecked():
                return valor
        return None

    def setValue(self, valor) -> None:
        if valor is None or int(valor) not in self.botones:
            self.vaciar()
        else:
            self.botones[int(valor)].setChecked(True)

    def vaciar(self) -> None:
        self.grupo.setExclusive(False)
        for b in self.botones.values():
            b.setChecked(False)
        self.grupo.setExclusive(True)
        self.valueChanged.emit()

    def set_invalido(self, invalido: bool) -> None:
        for b in self.botones.values():
            _refrescar_estilo(b, "invalido", invalido)


class SelectorBusqueda(QComboBox):
    """Lista desplegable en la que también se puede escribir para buscar (coincidencia parcial).

    La rueda del ratón solo cambia la opción si el selector tiene el foco, para no modificarlo sin
    querer al desplazar el formulario.
    """

    valueChanged = Signal()

    def __init__(self, opciones: dict, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setView(QListView())  # permite dar altura a los elementos desde la hoja de estilos
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMaxVisibleItems(20)
        for valor, texto in sorted(opciones.items(), key=lambda kv: kv[1]):
            self.addItem(texto, valor)
        completer = QCompleter(self.model(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.popup().setObjectName("sugerencias")
        self.setCompleter(completer)
        self.lineEdit().setPlaceholderText(placeholder)
        self.setCurrentIndex(-1)
        self.currentIndexChanged.connect(lambda *_: self.valueChanged.emit())
        self.editTextChanged.connect(lambda *_: self.valueChanged.emit())

    def wheelEvent(self, evento):
        if self.hasFocus():
            super().wheelEvent(evento)
        else:
            evento.ignore()

    def value(self):
        i = self.findText(self.currentText().strip(), Qt.MatchFlag.MatchFixedString)
        return self.itemData(i) if i >= 0 else None

    def setValue(self, valor) -> None:
        if valor is None:
            self.vaciar()
        else:
            self.setCurrentIndex(self.findData(int(valor)))

    def vaciar(self) -> None:
        self.setCurrentIndex(-1)
        self.setEditText("")

    def set_invalido(self, invalido: bool) -> None:
        _refrescar_estilo(self, "invalido", invalido)
