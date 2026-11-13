"""Vista previa de la ficha del estudiante y exportación a PDF."""
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout,
)

from app.services.reporte import exportar_pdf, ficha_html


def nombre_archivo_ficha(estudiante_id: str, fecha: str | None = None) -> str:
    fecha = (fecha or datetime.now().isoformat(timespec="seconds"))[:10]
    seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", estudiante_id.strip()) or "estudiante"
    return f"ficha_{seguro}_{fecha}.pdf"


def guardar_pdf_interactivo(parent, html: str, estudiante_id: str, fecha: str | None = None) -> Path | None:
    """Pide la ruta, exporta y ofrece abrir el PDF. Devuelve la ruta o None si se cancela."""
    sugerido = str(Path.home() / "Documents" / nombre_archivo_ficha(estudiante_id, fecha))
    ruta, _ = QFileDialog.getSaveFileName(parent, "Exportar ficha PDF", sugerido, "PDF (*.pdf)")
    if not ruta:
        return None
    if not ruta.lower().endswith(".pdf"):
        ruta += ".pdf"
    try:
        exportar_pdf(html, Path(ruta))
    except OSError as e:
        QMessageBox.critical(parent, "No se pudo exportar", f"No se pudo escribir el PDF:\n{e}")
        return None
    respuesta = QMessageBox.information(
        parent, "Ficha exportada", f"Ficha guardada en:\n{ruta}\n\n¿Abrir el PDF ahora?",
        QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close,
    )
    if respuesta == QMessageBox.StandardButton.Open:
        QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))
    return Path(ruta)


class DialogoFicha(QDialog):
    """Muestra la ficha; permite editar notas (si viene del historial) y exportar a PDF."""

    def __init__(self, parent, servicio, resultado, *, estudiante_id="", nombre="", fecha=None,
                 notas="", historial=None, registro_id=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ficha del estudiante {estudiante_id or ''}".strip())
        self.resize(820, 900)
        self.servicio = servicio
        self.resultado = resultado
        self.meta = {"estudiante_id": estudiante_id, "nombre": nombre, "fecha": fecha}
        self.historial = historial
        self.registro_id = registro_id

        self.vista = QTextBrowser()
        self.vista.setOpenExternalLinks(False)

        self.notas = QPlainTextEdit(notas)
        self.notas.setPlaceholderText("Notas de seguimiento (se incluyen en la ficha)")
        self.notas.setMaximumHeight(80)
        self.notas.textChanged.connect(self._refrescar)

        btn_pdf = QPushButton("Exportar PDF…")
        btn_pdf.setObjectName("primario")
        btn_pdf.clicked.connect(self._exportar)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.reject)
        if historial is not None and registro_id is not None:
            btn_notas = QPushButton("Guardar notas")
            btn_notas.clicked.connect(self._guardar_notas)
            botones.addButton(btn_notas, QDialogButtonBox.ButtonRole.ActionRole)

        pie = QHBoxLayout()
        pie.addWidget(btn_pdf)
        pie.addStretch()
        pie.addWidget(botones)

        lay = QVBoxLayout(self)
        lay.addWidget(self.vista, 1)
        lay.addWidget(QLabel("Notas:"))
        lay.addWidget(self.notas)
        lay.addLayout(pie)
        self._refrescar()

    def _html(self) -> str:
        return ficha_html(
            self.resultado, self.servicio.medianas, notas=self.notas.toPlainText(),
            modelo=self.servicio.nombre_modelo, **self.meta,
        )

    def _refrescar(self) -> None:
        barra = self.vista.verticalScrollBar().value()
        self.vista.setHtml(self._html())
        self.vista.verticalScrollBar().setValue(barra)

    def _exportar(self) -> None:
        guardar_pdf_interactivo(self, self._html(), self.meta["estudiante_id"], self.meta["fecha"])

    def _guardar_notas(self) -> None:
        self.historial.actualizar_notas(self.registro_id, self.notas.toPlainText())
        QMessageBox.information(self, "Notas guardadas", "Las notas se guardaron en el historial.")
