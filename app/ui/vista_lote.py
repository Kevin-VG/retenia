"""Evaluación por lote: plantilla → CSV o Excel → revisión fila por fila → resultados por riesgo."""
import shutil
from html import escape
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from app import rutas
from app.core import scoring
from app.core.validacion import ADVERTENCIA, ERROR, ErrorArchivo
from app.core.variables import (
    ALL_FEATURE_COLS, CARRERAS, COL_CARRERA, COL_ID, ENTRADAS_FORMULARIO, ETIQUETAS, describir_valor,
)
from app.services.plantilla import crear_plantilla_excel
from app.ui.dialogo_ficha import DialogoFicha
from app.ui.widgets import (
    COLOR_ESTADO, COLOR_NIVEL, FiltroTabla, ModeloTabla, Tarjeta, TarjetaKPI, porcentaje,
    semaforo_texto, titulo_seccion,
)

EXTENSIONES = (".csv", ".xlsx")
COLUMNAS_VISTA = [COL_ID, "Prob. Deserción", "Semáforo", "Avisos", "Fila", *ENTRADAS_FORMULARIO]
DOCUMENTOS = Path.home() / "Documents"


def _tabla(modelo, proxy) -> QTableView:
    tabla = QTableView()
    tabla.setModel(proxy)
    proxy.setSourceModel(modelo)
    tabla.setSortingEnabled(True)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tabla.setAlternatingRowColors(True)
    tabla.verticalHeader().hide()
    tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    return tabla


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
        raiz.setSpacing(12)
        raiz.addWidget(titulo_seccion(
            "Carga por lote",
            f"Evalúa muchos estudiantes a la vez desde un CSV o Excel con las {len(ALL_FEATURE_COLS)} "
            "variables del dataset. Cada fila se revisa antes de evaluarla.",
        ))

        barra = QHBoxLayout()
        abrir = QPushButton("Abrir CSV o Excel…")
        abrir.setObjectName("primario")
        abrir.clicked.connect(self.abrir_dialogo)
        plantilla = QPushButton("Descargar plantilla  ▾")
        menu = QMenu(plantilla)
        menu.addAction("Plantilla Excel (recomendada: instrucciones, diccionario y listas)…",
                       self.guardar_plantilla_excel)
        menu.addAction("Plantilla CSV…", self.guardar_plantilla_csv)
        plantilla.setMenu(menu)
        self.lbl_archivo = QLabel("Ningún archivo cargado.")
        self.lbl_archivo.setObjectName("leyenda")
        barra.addWidget(abrir)
        barra.addWidget(plantilla)
        barra.addSpacing(12)
        barra.addWidget(self.lbl_archivo, 1)
        raiz.addLayout(barra)

        # ---------- estado inicial: zona para soltar ----------
        self.zona = Tarjeta()
        self.zona.setObjectName("zonaSoltar")
        aviso = QLabel(
            "<b>Suelta aquí un archivo .csv o .xlsx</b><br><br>"
            "¿Primera vez? Usa <b>Descargar plantilla → Plantilla Excel</b>: trae instrucciones, "
            "el significado de cada columna y listas desplegables para evitar errores.<br><br>"
            "Al cargar, cada fila se revisa: las filas con <span style='color:#b91c1c'><b>errores</b></span> "
            "no se evalúan y las que tienen <span style='color:#a16207'><b>advertencias</b></span> se evalúan "
            "con aviso. Todo queda listado en la pestaña «Problemas»."
        )
        aviso.setTextFormat(Qt.TextFormat.RichText)
        aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aviso.setWordWrap(True)
        aviso.setObjectName("aviso")
        self.zona.cuerpo.addWidget(aviso)
        self.zona.setMinimumHeight(220)
        raiz.addWidget(self.zona)

        # ---------- contenido tras cargar ----------
        self.contenido = QWidget()
        cont = QVBoxLayout(self.contenido)
        cont.setContentsMargins(0, 0, 0, 0)
        cont.setSpacing(10)

        kpis = QHBoxLayout()
        self.k_total = TarjetaKPI("Evaluados")
        self.k_rojo = TarjetaKPI("Riesgo alto", color=COLOR_ESTADO["Rojo"])
        self.k_amarillo = TarjetaKPI("Riesgo moderado", color=COLOR_ESTADO["Amarillo"])
        self.k_verde = TarjetaKPI("Riesgo bajo", color=COLOR_ESTADO["Verde"])
        self.k_error = TarjetaKPI("Filas con error (no evaluadas)", color=COLOR_NIVEL["Error"])
        for k in (self.k_total, self.k_rojo, self.k_amarillo, self.k_verde, self.k_error):
            kpis.addWidget(k)
        cont.addLayout(kpis)

        self.lbl_resumen = QLabel()
        self.lbl_resumen.setObjectName("resumenRevision")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setTextFormat(Qt.TextFormat.RichText)
        cont.addWidget(self.lbl_resumen)

        self.pestanas = QTabWidget()
        self.pestanas.addTab(self._crear_pestana_resultados(), "Resultados")
        self.pestanas.addTab(self._crear_pestana_problemas(), "Problemas")
        cont.addWidget(self.pestanas, 1)

        self.contenido.hide()
        raiz.addWidget(self.contenido, 1)
        raiz.addStretch()

    # ------------------------------------------------------------------ pestañas
    def _crear_pestana_resultados(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)

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
        lay.addLayout(filtros)

        formatos = {
            "Prob. Deserción": porcentaje,
            "Semáforo": semaforo_texto,
            "Avisos": lambda v: f"⚠ {v}" if v else "",
            **{c: (lambda v, c=c: describir_valor(c, v)) for c in ENTRADAS_FORMULARIO},
        }
        self.modelo = ModeloTabla(encabezados={COL_ID: "ID", "Prob. Deserción": "Probabilidad",
                                               "Fila": "Fila del archivo", **ETIQUETAS}, formatos=formatos)
        self.proxy = FiltroTabla([COL_ID])
        self.buscar.textChanged.connect(self.proxy.set_texto)
        self.filtro_semaforo.currentIndexChanged.connect(
            lambda: self.proxy.set_semaforo(self.filtro_semaforo.currentData()))
        self.tabla = _tabla(self.modelo, self.proxy)
        self.tabla.doubleClicked.connect(self.ver_ficha)
        lay.addWidget(self.tabla, 1)

        acciones = QHBoxLayout()
        ficha = QPushButton("Ver ficha del seleccionado")
        ficha.clicked.connect(self.ver_ficha)
        exp_csv = QPushButton("Exportar CSV…")
        exp_csv.clicked.connect(lambda: self.exportar("csv"))
        exp_xlsx = QPushButton("Exportar Excel…")
        exp_xlsx.setToolTip("Incluye una hoja con los problemas detectados")
        exp_xlsx.clicked.connect(lambda: self.exportar("xlsx"))
        self.btn_historial = QPushButton("Guardar lote en historial")
        self.btn_historial.setObjectName("primario")
        self.btn_historial.clicked.connect(self.guardar_historial)
        acciones.addWidget(ficha)
        acciones.addStretch()
        acciones.addWidget(exp_csv)
        acciones.addWidget(exp_xlsx)
        acciones.addWidget(self.btn_historial)
        lay.addLayout(acciones)
        return w

    def _crear_pestana_problemas(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)

        filtros = QHBoxLayout()
        self.buscar_problema = QLineEdit()
        self.buscar_problema.setPlaceholderText("Buscar por ID, columna o problema…")
        self.buscar_problema.setClearButtonEnabled(True)
        self.filtro_nivel = QComboBox()
        for texto, valor in (("Errores y advertencias", None), ("Solo errores", ERROR),
                             ("Solo advertencias", ADVERTENCIA)):
            self.filtro_nivel.addItem(texto, valor)
        filtros.addWidget(self.buscar_problema, 2)
        filtros.addWidget(self.filtro_nivel, 1)
        filtros.addStretch(2)
        lay.addLayout(filtros)

        self.modelo_problemas = ModeloTabla(encabezados={COL_ID: "ID", "Fila": "Fila del archivo"})
        self.proxy_problemas = FiltroTabla([COL_ID, "Columna", "Problema", "Valor"], columna_estado="Nivel")
        self.buscar_problema.textChanged.connect(self.proxy_problemas.set_texto)
        self.filtro_nivel.currentIndexChanged.connect(
            lambda: self.proxy_problemas.set_semaforo(self.filtro_nivel.currentData()))
        self.tabla_problemas = _tabla(self.modelo_problemas, self.proxy_problemas)
        self.tabla_problemas.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tabla_problemas, 1)

        acciones = QHBoxLayout()
        ayuda = QLabel("Corrige las filas indicadas en tu archivo y vuelve a cargarlo. "
                       "«Fila del archivo» es el número de fila en Excel (la fila 1 son los títulos).")
        ayuda.setObjectName("leyenda")
        ayuda.setWordWrap(True)
        exportar = QPushButton("Exportar problemas (CSV)…")
        exportar.clicked.connect(self.exportar_problemas)
        acciones.addWidget(ayuda, 1)
        acciones.addWidget(exportar)
        lay.addLayout(acciones)
        return w

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
            self, "Abrir archivo de estudiantes", str(DOCUMENTOS),
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
        except ErrorArchivo as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "El archivo no tiene el formato esperado", str(e))
            return
        except (ValueError, OSError) as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "No se pudo leer el archivo", str(e))
            return
        QApplication.restoreOverrideCursor()

        self.lote = lote
        self.archivo = ruta
        self.guardado = False
        self._mostrar()

    def _mostrar(self) -> None:
        res = self.lote.resultado
        problemas = self.lote.problemas
        conteo = res["Semáforo"].value_counts()
        n_err_filas = self.lote.descartadas
        n_adv = int((problemas["Nivel"] == ADVERTENCIA).sum())
        n_err = int((problemas["Nivel"] == ERROR).sum())
        filas_adv = int((res["Avisos"] != "").sum())

        self.k_total.set_valor(f"{len(res):,}")
        self.k_rojo.set_valor(str(int(conteo.get("Rojo", 0))))
        self.k_amarillo.set_valor(str(int(conteo.get("Amarillo", 0))))
        self.k_verde.set_valor(str(int(conteo.get("Verde", 0))))
        self.k_error.set_valor(str(n_err_filas))

        partes = [f"<b>Revisión del archivo:</b> {len(res) + n_err_filas:,} filas leídas"]
        if n_err_filas:
            partes.append(f"<span style='color:#b91c1c'><b>✗</b> {n_err_filas} fila(s) con {n_err} error(es) — "
                          "no se evaluaron</span>")
        if n_adv:
            partes.append(f"<span style='color:#a16207'>⚠ {filas_adv} fila(s) evaluada(s) con "
                          f"{n_adv} advertencia(s)</span>")
        if not n_err_filas and not n_adv:
            partes.append("<span style='color:#0c8a0c'>✔ sin problemas</span>")
        extra = self.lote.validacion.columnas_extra
        if extra:
            partes.append(f"columnas ignoradas: {escape(', '.join(map(str, extra)))}")
        texto = " · ".join(partes)
        m = self.lote.metricas
        if m:
            texto += (f"<br><b>Resultado real incluido:</b> Accuracy {m['accuracy'] * 100:.1f} % · "
                      f"Precision {m['precision'] * 100:.1f} % · Recall {m['recall'] * 100:.1f} % · "
                      f"F1 {m['f1']:.4f} · ROC-AUC {m['roc_auc']:.4f}")
        self.lbl_resumen.setText(texto)
        estilo = "error" if n_err_filas else ("advertencia" if n_adv else "ok")
        self.lbl_resumen.setProperty("estado", estilo)
        self.lbl_resumen.style().unpolish(self.lbl_resumen)
        self.lbl_resumen.style().polish(self.lbl_resumen)

        self.modelo.set_df(res[[c for c in COLUMNAS_VISTA if c in res.columns]])
        self.tabla.resizeColumnsToContents()
        self.tabla.setColumnWidth(3, min(self.tabla.columnWidth(3), 260))  # Avisos
        self.tabla.sortByColumn(1, Qt.SortOrder.DescendingOrder)

        self.modelo_problemas.set_df(problemas)
        self.tabla_problemas.resizeColumnsToContents()
        self.tabla_problemas.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.pestanas.setTabText(0, f"Resultados ({len(res):,})")
        self.pestanas.setTabText(1, f"Problemas ({len(problemas):,})")
        # Si nada se pudo evaluar, abrir directamente la lista de problemas
        self.pestanas.setCurrentIndex(1 if res.empty else 0)

        self.lbl_archivo.setText(f"{self.archivo.name} · umbral {self.servicio.umbral:.2f}")
        self.btn_historial.setEnabled(not res.empty)
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

    def _ruta_guardar(self, titulo, nombre, filtro):
        ruta, _ = QFileDialog.getSaveFileName(self, titulo, str(DOCUMENTOS / nombre), filtro)
        return ruta or None

    def exportar(self, formato: str) -> None:
        if self.lote is None:
            return
        base = self.archivo.stem if self.archivo else "lote"
        filtro = "CSV (*.csv)" if formato == "csv" else "Excel (*.xlsx)"
        ruta = self._ruta_guardar("Exportar resultados", f"resultados_{base}.{formato}", filtro)
        if not ruta:
            return
        df = self.lote.resultado.copy()
        df.insert(5, "Carrera (nombre)", df[COL_CARRERA].map(lambda c: CARRERAS.get(int(c), str(int(c)))))
        try:
            if formato == "csv":
                df.to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                with pd.ExcelWriter(ruta, engine="openpyxl") as libro:
                    df.to_excel(libro, index=False, sheet_name="Resultados")
                    if not self.lote.problemas.empty:
                        self.lote.problemas.to_excel(libro, index=False, sheet_name="Problemas")
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar",
                                 f"No se pudo escribir el archivo (¿está abierto en otro programa?):\n{e}")
            return
        QMessageBox.information(self, "Exportado", f"Resultados guardados en:\n{ruta}")

    def exportar_problemas(self) -> None:
        if self.lote is None or self.lote.problemas.empty:
            QMessageBox.information(self, "Sin problemas", "El archivo no tiene errores ni advertencias.")
            return
        base = self.archivo.stem if self.archivo else "lote"
        ruta = self._ruta_guardar("Exportar problemas", f"problemas_{base}.csv", "CSV (*.csv)")
        if not ruta:
            return
        try:
            self.lote.problemas.to_csv(ruta, index=False, encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar", str(e))
            return
        QMessageBox.information(self, "Exportado", f"Problemas guardados en:\n{ruta}")

    def guardar_historial(self) -> None:
        if self.lote is None or self.guardado or self.lote.resultado.empty:
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
             "perfil": perfil, "notas": f"Lote: {self.archivo.name}" + (f" · ⚠ {a}" if a else "")}
            for i, p, s, a, perfil in zip(res[COL_ID], res["Prob. Deserción"], res["Semáforo"],
                                          res["Avisos"], perfiles)
        ]
        n = self.historial.guardar_lote(filas)
        self.guardado = True
        self.btn_historial.setEnabled(False)
        self.btn_historial.setText(f"Guardado ✓ ({n:,})")
        self.historial_cambiado.emit()

    def guardar_plantilla_excel(self) -> None:
        ruta = self._ruta_guardar("Guardar plantilla Excel", "plantilla_retenia.xlsx", "Excel (*.xlsx)")
        if not ruta:
            return
        try:
            crear_plantilla_excel(Path(ruta), self.servicio)
        except OSError as e:
            QMessageBox.critical(self, "No se pudo guardar", f"¿Está abierto en Excel?\n{e}")
            return
        QMessageBox.information(
            self, "Plantilla guardada",
            f"Plantilla guardada en:\n{ruta}\n\nIncluye las hojas «Instrucciones», «Estudiantes» (con 4 "
            "ejemplos) y «Diccionario». Excel avisará si escribes un valor no permitido.",
        )

    def guardar_plantilla_csv(self) -> None:
        ruta = self._ruta_guardar("Guardar plantilla CSV", "plantilla_retenia.csv", "CSV (*.csv)")
        if not ruta:
            return
        try:
            shutil.copyfile(rutas.PLANTILLA_LOTE, ruta)
        except OSError as e:
            QMessageBox.critical(self, "No se pudo guardar", str(e))
            return
        QMessageBox.information(
            self, "Plantilla guardada",
            f"Plantilla guardada en:\n{ruta}\n\nTiene las {len(ALL_FEATURE_COLS)} columnas del modelo "
            "y 4 filas de ejemplo. Reemplázalas por tus estudiantes.",
        )
