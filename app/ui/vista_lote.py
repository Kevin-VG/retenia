"""Evaluación por lote: CSV o Excel → tabla ordenada por riesgo → exportar / historial / ficha."""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from app import rutas
from app.core import scoring
from app.core.variables import (
    ALL_FEATURE_COLS, CARRERAS, COL_CARRERA, COL_ID, ENTRADAS_FORMULARIO, ETIQUETAS,
    describir_valor,
)
from app.ui.dialogo_ficha import DialogoFicha
from app.ui.widgets import (
    COLOR_ESTADO, FiltroTabla, ModeloTabla, Tarjeta, TarjetaKPI, porcentaje, semaforo_texto,
    titulo_seccion,
)

EXTENSIONES = (".csv", ".xlsx")
COLUMNAS_VISTA = [COL_ID, "Prob. Deserción", "Semáforo", *ENTRADAS_FORMULARIO]


class VistaLote(QWidget):
    historial_cambiado = Signal()

    def __init__(self, servicio, historial, parent=None):
        super().__init__(parent)
        self.servicio = servicio
        self.historial = historial
        self.lote = None          # ResultadoLote
        self.archivo: Path | None = None
        self.guardado = False
        self.setAcceptDrops(True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 24)
        raiz.setSpacing(14)
        raiz.addWidget(titulo_seccion(
            "Carga por lote",
            f"Evalúa muchos estudiantes a la vez desde un CSV o Excel con las {len(ALL_FEATURE_COLS)} "
            "variables del dataset. Puedes arrastrar el archivo a esta ventana.",
        ))

        barra = QHBoxLayout()
        abrir = QPushButton("Abrir CSV o Excel…")
        abrir.setObjectName("primario")
        abrir.clicked.connect(self.abrir_dialogo)
        plantilla = QPushButton("Guardar plantilla de ejemplo…")
        plantilla.clicked.connect(self.guardar_plantilla)
        self.lbl_archivo = QLabel("Ningún archivo cargado.")
        self.lbl_archivo.setObjectName("leyenda")
        barra.addWidget(abrir)
        barra.addWidget(plantilla)
        barra.addSpacing(12)
        barra.addWidget(self.lbl_archivo, 1)
        raiz.addLayout(barra)

        self.zona = Tarjeta()
        self.zona.setObjectName("zonaSoltar")
        aviso = QLabel("Suelta aquí un archivo .csv o .xlsx\n\n"
                       "Si incluye la columna «id_estudiante» se usa como identificador. "
                       "Si incluye «dropout» o «Target», también se compara con el resultado real.")
        aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aviso.setWordWrap(True)
        aviso.setObjectName("aviso")
        self.zona.cuerpo.addWidget(aviso)
        self.zona.setMinimumHeight(180)
        raiz.addWidget(self.zona)

        self.contenido = QWidget()
        cont = QVBoxLayout(self.contenido)
        cont.setContentsMargins(0, 0, 0, 0)
        cont.setSpacing(12)

        kpis = QHBoxLayout()
        self.k_total = TarjetaKPI("Estudiantes evaluados")
        self.k_rojo = TarjetaKPI("Riesgo alto", color=COLOR_ESTADO["Rojo"])
        self.k_amarillo = TarjetaKPI("Riesgo moderado", color=COLOR_ESTADO["Amarillo"])
        self.k_verde = TarjetaKPI("Riesgo bajo", color=COLOR_ESTADO["Verde"])
        for k in (self.k_total, self.k_rojo, self.k_amarillo, self.k_verde):
            kpis.addWidget(k)
        cont.addLayout(kpis)

        self.lbl_avisos = QLabel()
        self.lbl_avisos.setObjectName("leyenda")
        self.lbl_avisos.setWordWrap(True)
        cont.addWidget(self.lbl_avisos)

        filtros = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar por ID…")
        self.buscar.setClearButtonEnabled(True)
        self.filtro_semaforo = QComboBox()
        for texto, valor in (("Todos los niveles", None), ("Riesgo alto", "Rojo"),
                             ("Riesgo moderado", "Amarillo"), ("Riesgo bajo", "Verde")):
            self.filtro_semaforo.addItem(texto, valor)
        filtros.addWidget(self.buscar, 2)
        filtros.addWidget(self.filtro_semaforo, 1)
        filtros.addStretch(2)
        cont.addLayout(filtros)

        formatos = {
            "Prob. Deserción": porcentaje,
            "Semáforo": semaforo_texto,
            **{c: (lambda v, c=c: describir_valor(c, v)) for c in ENTRADAS_FORMULARIO},
        }
        self.modelo = ModeloTabla(encabezados={COL_ID: "ID", "Prob. Deserción": "Probabilidad",
                                               **ETIQUETAS}, formatos=formatos)
        self.proxy = FiltroTabla([COL_ID])
        self.proxy.setSourceModel(self.modelo)
        self.buscar.textChanged.connect(self.proxy.set_texto)
        self.filtro_semaforo.currentIndexChanged.connect(
            lambda: self.proxy.set_semaforo(self.filtro_semaforo.currentData()))

        self.tabla = QTableView()
        self.tabla.setModel(self.proxy)
        self.tabla.setSortingEnabled(True)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().hide()
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabla.doubleClicked.connect(self.ver_ficha)
        cont.addWidget(self.tabla, 1)

        acciones = QHBoxLayout()
        self.btn_ficha = QPushButton("Ver ficha del seleccionado")
        self.btn_ficha.clicked.connect(self.ver_ficha)
        exp_csv = QPushButton("Exportar CSV…")
        exp_csv.clicked.connect(lambda: self.exportar("csv"))
        exp_xlsx = QPushButton("Exportar Excel…")
        exp_xlsx.clicked.connect(lambda: self.exportar("xlsx"))
        self.btn_historial = QPushButton("Guardar lote en historial")
        self.btn_historial.setObjectName("primario")
        self.btn_historial.clicked.connect(self.guardar_historial)
        acciones.addWidget(self.btn_ficha)
        acciones.addStretch()
        acciones.addWidget(exp_csv)
        acciones.addWidget(exp_xlsx)
        acciones.addWidget(self.btn_historial)
        cont.addLayout(acciones)

        self.contenido.hide()
        raiz.addWidget(self.contenido, 1)
        raiz.addStretch()

    # ------------------------------------------------------------------ arrastrar y soltar
    def dragEnterEvent(self, evento):
        urls = evento.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(EXTENSIONES):
            evento.acceptProposedAction()

    def dropEvent(self, evento):
        self.cargar(Path(evento.mimeData().urls()[0].toLocalFile()))

    # ------------------------------------------------------------------ carga
    def abrir_dialogo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir archivo de estudiantes", str(Path.home()),
            "Datos de estudiantes (*.csv *.xlsx);;CSV (*.csv);;Excel (*.xlsx)",
        )
        if ruta:
            self.cargar(Path(ruta))

    def cargar(self, ruta: Path) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if ruta.suffix.lower() == ".xlsx":
                df = scoring.leer_excel(ruta)
            else:
                df = scoring.leer_lote(ruta.read_bytes())
            lote = self.servicio.evaluar_lote(df)
        except (ValueError, OSError) as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "No se pudo evaluar el archivo", str(e))
            return
        QApplication.restoreOverrideCursor()

        self.lote = lote
        self.archivo = ruta
        self.guardado = False
        self._mostrar()

    def _mostrar(self) -> None:
        res = self.lote.resultado
        conteo = res["Semáforo"].value_counts()
        self.k_total.set_valor(f"{len(res):,}")
        self.k_rojo.set_valor(str(int(conteo.get("Rojo", 0))))
        self.k_amarillo.set_valor(str(int(conteo.get("Amarillo", 0))))
        self.k_verde.set_valor(str(int(conteo.get("Verde", 0))))

        avisos = []
        if self.lote.descartadas:
            avisos.append(f"⚠ {self.lote.descartadas} fila(s) descartadas por valores vacíos o no numéricos.")
        if self.lote.desconocidas:
            detalle = ", ".join(f"{ETIQUETAS[c]}: {n}" for c, n in self.lote.desconocidas.items())
            avisos.append(f"ℹ Códigos que el modelo no conoce (se puntúan con menor fiabilidad): {detalle}.")
        m = self.lote.metricas
        if m:
            avisos.append(
                f"✔ El archivo trae el resultado real → Accuracy {m['accuracy'] * 100:.1f} % · "
                f"Precision {m['precision'] * 100:.1f} % · Recall {m['recall'] * 100:.1f} % · "
                f"F1 {m['f1']:.4f} · ROC-AUC {m['roc_auc']:.4f}"
            )
        self.lbl_avisos.setText("\n".join(avisos))
        self.lbl_avisos.setVisible(bool(avisos))

        self.modelo.set_df(res[[c for c in COLUMNAS_VISTA if c in res.columns]])
        self.tabla.resizeColumnsToContents()
        self.tabla.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        self.lbl_archivo.setText(f"{self.archivo.name} · umbral {self.servicio.umbral:.2f}")
        self.btn_historial.setEnabled(True)
        self.btn_historial.setText("Guardar lote en historial")
        self.zona.hide()
        self.contenido.show()

    # ------------------------------------------------------------------ acciones
    def _fila_seleccionada(self):
        indices = self.tabla.selectionModel().selectedRows() if self.tabla.selectionModel() else []
        if not indices:
            return None
        return self.proxy.mapToSource(indices[0]).row()

    def ver_ficha(self, *_):
        fila = self._fila_seleccionada()
        if fila is None:
            QMessageBox.information(self, "Selecciona un estudiante", "Selecciona una fila de la tabla.")
            return
        datos = self.lote.resultado.iloc[fila]
        resultado = self.servicio.explicar(datos[ALL_FEATURE_COLS].to_dict())
        DialogoFicha(self, self.servicio, resultado, estudiante_id=str(datos[COL_ID])).exec()

    def exportar(self, formato: str) -> None:
        if self.lote is None:
            return
        base = self.archivo.stem if self.archivo else "lote"
        sugerido = str(Path.home() / "Documents" / f"resultados_{base}.{formato}")
        filtro = "CSV (*.csv)" if formato == "csv" else "Excel (*.xlsx)"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar resultados", sugerido, filtro)
        if not ruta:
            return
        df = self.lote.resultado.copy()
        df.insert(3, "Carrera (nombre)", df[COL_CARRERA].map(lambda c: CARRERAS.get(int(c), str(int(c)))))
        try:
            if formato == "csv":
                df.to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(ruta, index=False, sheet_name="Resultados", engine="openpyxl")
        except (OSError, PermissionError) as e:
            QMessageBox.critical(self, "No se pudo exportar",
                                 f"No se pudo escribir el archivo (¿está abierto en otro programa?):\n{e}")
            return
        QMessageBox.information(self, "Exportado", f"Resultados guardados en:\n{ruta}")

    def guardar_historial(self) -> None:
        if self.lote is None or self.guardado:
            return
        res = self.lote.resultado
        r = QMessageBox.question(
            self, "Guardar en historial",
            f"¿Guardar las {len(res):,} evaluaciones de «{self.archivo.name}» en el historial?",
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        umbral = self.servicio.umbral
        perfiles = res[ALL_FEATURE_COLS].to_dict("records")
        filas = [
            {"estudiante_id": str(i), "probabilidad": p, "semaforo": s, "umbral": umbral,
             "perfil": perfil, "notas": f"Lote: {self.archivo.name}"}
            for i, p, s, perfil in zip(res[COL_ID], res["Prob. Deserción"], res["Semáforo"], perfiles)
        ]
        n = self.historial.guardar_lote(filas)
        self.guardado = True
        self.btn_historial.setEnabled(False)
        self.btn_historial.setText(f"Guardado ✓ ({n:,})")
        self.historial_cambiado.emit()

    def guardar_plantilla(self) -> None:
        sugerido = str(Path.home() / "Documents" / "plantilla_retenia.csv")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla", sugerido, "CSV (*.csv)")
        if ruta:
            shutil.copyfile(rutas.PLANTILLA_LOTE, ruta)
            QMessageBox.information(
                self, "Plantilla guardada",
                f"Plantilla guardada en:\n{ruta}\n\nTiene las {len(ALL_FEATURE_COLS)} columnas del modelo "
                "y 4 filas de ejemplo. Reemplázalas por tus estudiantes.",
            )
