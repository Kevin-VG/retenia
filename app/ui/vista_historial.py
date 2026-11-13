"""Historial de evaluaciones guardadas en este equipo."""
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from app.core.variables import ALL_FEATURE_COLS, CARRERAS, COL_CARRERA
from app.ui.dialogo_ficha import DialogoFicha
from app.ui.widgets import FiltroTabla, ModeloTabla, porcentaje, semaforo_texto, titulo_seccion

COLUMNAS = ["id", "Fecha", "ID estudiante", "Nombre", "Carrera", "Origen", "Prob. Deserción",
            "Semáforo", "Notas"]


class VistaHistorial(QWidget):
    def __init__(self, servicio, historial, parent=None):
        super().__init__(parent)
        self.servicio = servicio
        self.historial = historial

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 24)
        raiz.setSpacing(12)
        raiz.addWidget(titulo_seccion(
            "Historial",
            "Evaluaciones guardadas en este equipo. Los datos no salen de tu computadora.",
        ))

        filtros = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar por ID, nombre o notas…")
        self.buscar.setClearButtonEnabled(True)
        self.f_semaforo = QComboBox()
        for texto, valor in (("Todos los niveles", None), ("Riesgo alto", "Rojo"),
                             ("Riesgo moderado", "Amarillo"), ("Riesgo bajo", "Verde")):
            self.f_semaforo.addItem(texto, valor)
        self.f_origen = QComboBox()
        for texto, valor in (("Todos los orígenes", None), ("Individual", "individual"), ("Lote", "lote")):
            self.f_origen.addItem(texto, valor)
        filtros.addWidget(self.buscar, 3)
        filtros.addWidget(self.f_semaforo, 1)
        filtros.addWidget(self.f_origen, 1)
        raiz.addLayout(filtros)

        # Búsqueda en la base con un pequeño retardo para no consultar en cada tecla
        self._temporizador = QTimer(self, singleShot=True, interval=250)
        self._temporizador.timeout.connect(self.refrescar)
        self.buscar.textChanged.connect(self._temporizador.start)
        self.f_semaforo.currentIndexChanged.connect(self.refrescar)
        self.f_origen.currentIndexChanged.connect(self.refrescar)

        self.modelo = ModeloTabla(
            encabezados={"Prob. Deserción": "Probabilidad"},
            formatos={"Prob. Deserción": porcentaje, "Semáforo": semaforo_texto,
                      "Fecha": lambda v: str(v).replace("T", " ")},
        )
        self.proxy = FiltroTabla([])
        self.proxy.setSourceModel(self.modelo)
        self.tabla = QTableView()
        self.tabla.setModel(self.proxy)
        self.tabla.setSortingEnabled(True)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().hide()
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabla.doubleClicked.connect(self.ver_ficha)
        raiz.addWidget(self.tabla, 1)

        acciones = QHBoxLayout()
        ver = QPushButton("Ver ficha / PDF")
        ver.setObjectName("primario")
        ver.clicked.connect(self.ver_ficha)
        eliminar = QPushButton("Eliminar seleccionados")
        eliminar.setObjectName("peligro")
        eliminar.clicked.connect(self.eliminar)
        exportar = QPushButton("Exportar CSV…")
        exportar.clicked.connect(self.exportar)
        carpeta = QPushButton("Abrir carpeta de datos")
        carpeta.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.historial.ruta.parent))))
        self.lbl_total = QLabel()
        self.lbl_total.setObjectName("leyenda")
        acciones.addWidget(ver)
        acciones.addWidget(eliminar)
        acciones.addSpacing(12)
        acciones.addWidget(self.lbl_total, 1)
        acciones.addWidget(exportar)
        acciones.addWidget(carpeta)
        raiz.addLayout(acciones)

        self.registros = []
        self.refrescar()

    def refrescar(self) -> None:
        self.registros = self.historial.buscar(
            self.buscar.text(), self.f_semaforo.currentData(), self.f_origen.currentData()
        )
        filas = [
            {
                "id": r.id,
                "Fecha": r.fecha,
                "ID estudiante": r.estudiante_id,
                "Nombre": r.nombre,
                "Carrera": CARRERAS.get(int(r.perfil.get(COL_CARRERA, 0)), ""),
                "Origen": r.origen.capitalize(),
                "Prob. Deserción": r.probabilidad,
                "Semáforo": r.semaforo,
                "Notas": r.notas,
            }
            for r in self.registros
        ]
        self.modelo.set_df(pd.DataFrame(filas, columns=COLUMNAS))
        self.tabla.hideColumn(0)
        self.tabla.resizeColumnsToContents()
        total = self.historial.contar()
        self.lbl_total.setText(f"Mostrando {len(filas):,} de {total:,} evaluaciones")

    def _ids_seleccionados(self) -> list[int]:
        return [
            int(self.modelo.df["id"].iat[self.proxy.mapToSource(i).row()])
            for i in self.tabla.selectionModel().selectedRows()
        ]

    def ver_ficha(self, *_):
        ids = self._ids_seleccionados()
        if not ids:
            QMessageBox.information(self, "Selecciona una evaluación", "Selecciona una fila del historial.")
            return
        r = self.historial.obtener(ids[0])
        if r is None:
            return
        if r.origen == "individual":
            resultado = self.servicio.evaluar(r.entradas, umbral=r.umbral)
        else:
            resultado = self.servicio.explicar(r.perfil, umbral=r.umbral)
        DialogoFicha(
            self, self.servicio, resultado, estudiante_id=r.estudiante_id, nombre=r.nombre,
            fecha=r.fecha, notas=r.notas, historial=self.historial, registro_id=r.id,
        ).exec()
        self.refrescar()

    def eliminar(self) -> None:
        ids = self._ids_seleccionados()
        if not ids:
            return
        r = QMessageBox.warning(
            self, "Eliminar evaluaciones",
            f"Se eliminarán {len(ids)} evaluación(es) del historial. Esta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if r == QMessageBox.StandardButton.Yes:
            self.historial.eliminar(ids)
            self.refrescar()

    def exportar(self) -> None:
        if not self.registros:
            QMessageBox.information(self, "Sin datos", "No hay evaluaciones para exportar.")
            return
        sugerido = str(Path.home() / "Documents" / "historial_retenia.csv")
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar historial", sugerido, "CSV (*.csv)")
        if not ruta:
            return
        filas = [
            {"id_registro": r.id, "fecha": r.fecha, "id_estudiante": r.estudiante_id, "nombre": r.nombre,
             "origen": r.origen, "probabilidad": round(r.probabilidad, 4), "semaforo": r.semaforo,
             "umbral": r.umbral, "notas": r.notas,
             **{c: r.perfil.get(c) for c in ALL_FEATURE_COLS}}
            for r in self.registros
        ]
        try:
            pd.DataFrame(filas).to_csv(ruta, index=False, encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar", str(e))
            return
        QMessageBox.information(self, "Exportado", f"Historial guardado en:\n{ruta}")

    def showEvent(self, evento):
        super().showEvent(evento)
        self.refrescar()

    def keyPressEvent(self, evento):
        if evento.key() == Qt.Key.Key_Delete:
            self.eliminar()
        else:
            super().keyPressEvent(evento)
