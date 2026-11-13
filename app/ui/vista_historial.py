"""Historial de evaluaciones guardadas en este equipo."""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from app.core.variables import ALL_FEATURE_COLS, CARRERAS, COL_CARRERA, ETIQUETAS
from app.services.plantilla import valor_plantilla
from app.services.reporte import fecha_legible
from app.ui.dialogo_ficha import DialogoFicha
from app.ui.widgets import NOMBRE_ESTADO, FiltroTabla, ModeloTabla, porcentaje, semaforo_texto, titulo_seccion

COLUMNAS = ["id", "Fecha", "ID estudiante", "Nombre", "Carrera", "Origen", "Prob. Deserción",
            "Semáforo", "Notas"]
ORIGEN = {"individual": "Individual", "lote": "Archivo"}
PERIODOS = (("Cualquier fecha", None), ("Hoy", 0), ("Últimos 7 días", 7), ("Últimos 30 días", 30),
            ("Últimos 12 meses", 365))


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
            "Evaluaciones guardadas en este equipo. Doble clic en una fila para ver la ficha, editar las "
            "notas o exportar el PDF.",
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
        for texto, valor in (("Individual y archivo", None), ("Solo individual", "individual"),
                             ("Solo desde archivo", "lote")):
            self.f_origen.addItem(texto, valor)
        self.f_periodo = QComboBox()
        for texto, dias in PERIODOS:
            self.f_periodo.addItem(texto, dias)
        filtros.addWidget(self.buscar, 3)
        filtros.addWidget(self.f_periodo, 1)
        filtros.addWidget(self.f_semaforo, 1)
        filtros.addWidget(self.f_origen, 1)
        raiz.addLayout(filtros)

        # Búsqueda en la base con un pequeño retardo para no consultar en cada tecla
        self._temporizador = QTimer(self, singleShot=True, interval=250)
        self._temporizador.timeout.connect(self.refrescar)
        self.buscar.textChanged.connect(self._temporizador.start)
        for combo in (self.f_semaforo, self.f_origen, self.f_periodo):
            combo.currentIndexChanged.connect(self.refrescar)

        self.modelo = ModeloTabla(
            encabezados={"Prob. Deserción": "Riesgo", "Semáforo": "Nivel de riesgo", "Origen": "Tipo"},
            formatos={"Prob. Deserción": porcentaje, "Semáforo": semaforo_texto, "Fecha": fecha_legible},
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
        eliminar = QPushButton("Eliminar seleccionadas")
        eliminar.setObjectName("peligro")
        eliminar.setToolTip("También con la tecla Supr")
        eliminar.clicked.connect(self.eliminar)
        exportar = QPushButton("Exportar a Excel…")
        exportar.setToolTip("Exporta las evaluaciones que se muestran con los filtros actuales")
        exportar.clicked.connect(self.exportar)
        self.lbl_total = QLabel()
        self.lbl_total.setObjectName("leyenda")
        acciones.addWidget(ver)
        acciones.addWidget(eliminar)
        acciones.addSpacing(12)
        acciones.addWidget(self.lbl_total, 1)
        acciones.addWidget(exportar)
        raiz.addLayout(acciones)

        self.registros = []
        self.refrescar()

    def _desde(self) -> str | None:
        dias = self.f_periodo.currentData()
        if dias is None:
            return None
        return (date.today() - timedelta(days=dias)).isoformat()

    def refrescar(self) -> None:
        self.registros = self.historial.buscar(
            self.buscar.text(), self.f_semaforo.currentData(), self.f_origen.currentData(), self._desde()
        )
        filas = [
            {
                "id": r.id,
                "Fecha": r.fecha,
                "ID estudiante": r.estudiante_id,
                "Nombre": r.nombre,
                "Carrera": CARRERAS.get(int(r.perfil.get(COL_CARRERA, 0)), ""),
                "Origen": ORIGEN.get(r.origen, r.origen),
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
        if total == 0:
            self.lbl_total.setText("Aún no hay evaluaciones guardadas. Usa «Guardar en historial» al "
                                   "evaluar un estudiante o un archivo.")
        else:
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

    def tabla_exportable(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"Fecha": fecha_legible(r.fecha), "ID estudiante": r.estudiante_id, "Nombre": r.nombre,
             "Tipo": ORIGEN.get(r.origen, r.origen), "Riesgo (%)": round(r.probabilidad * 100, 1),
             "Nivel de riesgo": NOMBRE_ESTADO.get(r.semaforo, r.semaforo), "Notas": r.notas,
             **{ETIQUETAS[c]: valor_plantilla(c, r.perfil.get(c)) for c in ALL_FEATURE_COLS}}
            for r in self.registros
        ])

    def exportar(self) -> None:
        if not self.registros:
            QMessageBox.information(self, "Sin datos", "No hay evaluaciones para exportar.")
            return
        sugerido = str(Path.home() / "Documents" / "historial_retenia.xlsx")
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar historial", sugerido,
                                              "Excel (*.xlsx);;CSV (*.csv)")
        if not ruta:
            return
        df = self.tabla_exportable()
        try:
            if ruta.lower().endswith(".csv"):
                df.to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(ruta, index=False, sheet_name="Historial")
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar", f"¿Está abierto en otro programa?\n{e}")
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
