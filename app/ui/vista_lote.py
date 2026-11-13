"""Evaluación desde archivo: plantilla Excel → revisión fila por fila → resultados por nivel de riesgo."""
from html import escape
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from app.core import scoring
from app.core.validacion import ADVERTENCIA, ERROR, ErrorArchivo
from app.core.variables import ALL_FEATURE_COLS, COL_CARRERA, COL_ID, COLUMNAS_PLANTILLA, describir_valor
from app.services.plantilla import crear_plantilla_excel, encabezado, valor_plantilla
from app.services.reporte import fecha_legible
from app.ui.dialogo_ficha import DialogoFicha
from app.ui.widgets import (
    COLOR_ESTADO, COLOR_NIVEL, NOMBRE_ESTADO, FiltroTabla, ModeloTabla, Tarjeta, TarjetaKPI, porcentaje,
    semaforo_texto, titulo_seccion,
)

EXTENSIONES = (".xlsx", ".csv")
COLUMNAS_VISTA = [COL_ID, "Prob. Deserción", "Semáforo", COL_CARRERA, "Fila", "Avisos"]
DOCUMENTOS = Path.home() / "Documents"
FILTROS_NIVEL = (("Todos los niveles", None), ("Riesgo alto", "Rojo"), ("Riesgo moderado", "Amarillo"),
                 ("Riesgo bajo", "Verde"))


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
    tabla.horizontalHeader().setStretchLastSection(True)
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
            "Evaluar desde archivo",
            "Evalúa a varios estudiantes a la vez con la plantilla de Excel. Cada fila se revisa antes "
            "de evaluarla.",
        ))

        barra = QHBoxLayout()
        plantilla = QPushButton("Descargar plantilla Excel…")
        plantilla.setToolTip("Plantilla con instrucciones, listas desplegables y la explicación de "
                             "cada columna")
        plantilla.clicked.connect(self.guardar_plantilla_excel)
        abrir = QPushButton("Abrir archivo…")
        abrir.setObjectName("primario")
        abrir.setToolTip("Excel (.xlsx) o CSV con los mismos títulos de columna que la plantilla")
        abrir.clicked.connect(self.abrir_dialogo)
        self.lbl_archivo = QLabel()
        self.lbl_archivo.setObjectName("leyenda")
        barra.addWidget(plantilla)
        barra.addWidget(abrir)
        barra.addSpacing(12)
        barra.addWidget(self.lbl_archivo, 1)
        raiz.addLayout(barra)

        # ---------- estado inicial: pasos + zona para soltar ----------
        self.zona = Tarjeta()
        self.zona.setObjectName("zonaSoltar")
        aviso = QLabel(
            "<p style='font-size:12pt'><b>Arrastra aquí tu archivo Excel (.xlsx) o CSV</b></p>"
            "<table cellspacing='8' align='center'>"
            "<tr><td><b>1.</b></td><td align='left'>Pulsa <b>Descargar plantilla Excel</b> y completa "
            "una fila por estudiante. Al seleccionar una celda, Excel te indica qué valores son válidos.</td></tr>"
            "<tr><td><b>2.</b></td><td align='left'>Arrastra el archivo a esta zona o pulsa "
            "<b>Abrir archivo…</b></td></tr>"
            "<tr><td><b>3.</b></td><td align='left'>Revisa los resultados, abre la ficha de cada "
            "estudiante y guarda el grupo en el historial.</td></tr></table>"
            f"<p>Las filas con <span style='color:{COLOR_NIVEL[ERROR]}'><b>errores</b></span> no se "
            f"evalúan; las que tienen <span style='color:{COLOR_NIVEL[ADVERTENCIA]}'><b>advertencias</b>"
            "</span> se evalúan con aviso. Todo se detalla en la pestaña «Problemas».</p>"
        )
        aviso.setTextFormat(Qt.TextFormat.RichText)
        aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aviso.setWordWrap(True)
        aviso.setObjectName("aviso")
        self.zona.cuerpo.addWidget(aviso)
        self.zona.setMinimumHeight(260)
        raiz.addWidget(self.zona)

        # ---------- contenido tras cargar ----------
        self.contenido = QWidget()
        cont = QVBoxLayout(self.contenido)
        cont.setContentsMargins(0, 0, 0, 0)
        cont.setSpacing(10)

        kpis = QHBoxLayout()
        self.k_total = TarjetaKPI("Evaluados", pulsable=True, ayuda="Mostrar todos los evaluados")
        self.k_rojo = TarjetaKPI("Riesgo alto", color=COLOR_ESTADO["Rojo"], pulsable=True,
                                 ayuda="Mostrar solo riesgo alto")
        self.k_amarillo = TarjetaKPI("Riesgo moderado", color=COLOR_ESTADO["Amarillo"], pulsable=True,
                                     ayuda="Mostrar solo riesgo moderado")
        self.k_verde = TarjetaKPI("Riesgo bajo", color=COLOR_ESTADO["Verde"], pulsable=True,
                                  ayuda="Mostrar solo riesgo bajo")
        self.k_error = TarjetaKPI("Filas no evaluadas (con error)", color=COLOR_NIVEL[ERROR], pulsable=True,
                                  ayuda="Ver las filas con errores")
        self._kpi_nivel = {None: self.k_total, "Rojo": self.k_rojo, "Amarillo": self.k_amarillo,
                           "Verde": self.k_verde}
        for nivel, k in self._kpi_nivel.items():
            k.pulsada.connect(lambda n=nivel: self._filtrar_nivel(n))
            kpis.addWidget(k)
        self.k_error.pulsada.connect(self._ver_errores)
        kpis.addWidget(self.k_error)
        cont.addLayout(kpis)

        self.lbl_resumen = QLabel()
        self.lbl_resumen.setObjectName("resumenRevision")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setTextFormat(Qt.TextFormat.RichText)
        cont.addWidget(self.lbl_resumen)

        self.pestanas = QTabWidget()
        self.pestanas.addTab(self._crear_pestana_resultados(), "Resultados")
        self.pestanas.addTab(self._crear_pestana_problemas(), "Problemas")
        self.pestanas.currentChanged.connect(lambda i: self._filtro_cambiado() if i == 0 else None)
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
        for texto, valor in FILTROS_NIVEL:
            self.filtro_semaforo.addItem(texto, valor)
        ayuda = QLabel("Doble clic en una fila para ver la ficha completa.")
        ayuda.setObjectName("leyenda")
        filtros.addWidget(self.buscar, 2)
        filtros.addWidget(self.filtro_semaforo, 1)
        filtros.addSpacing(8)
        filtros.addWidget(ayuda, 2)
        lay.addLayout(filtros)

        formatos = {
            "Prob. Deserción": porcentaje,
            "Semáforo": semaforo_texto,
            "Avisos": lambda v: f"⚠ {v}" if v else "",
            COL_CARRERA: lambda v: describir_valor(COL_CARRERA, v),
        }
        self.modelo = ModeloTabla(
            encabezados={COL_ID: "ID estudiante", "Prob. Deserción": "Riesgo", "Semáforo": "Nivel de riesgo",
                         COL_CARRERA: "Carrera", "Fila": "Fila del archivo", "Avisos": "Avisos"},
            formatos=formatos,
        )
        self.proxy = FiltroTabla([COL_ID])
        self.buscar.textChanged.connect(self.proxy.set_texto)
        self.filtro_semaforo.currentIndexChanged.connect(self._filtro_cambiado)
        self.tabla = _tabla(self.modelo, self.proxy)
        self.tabla.doubleClicked.connect(self.ver_ficha)
        lay.addWidget(self.tabla, 1)

        acciones = QHBoxLayout()
        ficha = QPushButton("Ver ficha")
        ficha.clicked.connect(self.ver_ficha)
        exp_xlsx = QPushButton("Exportar Excel…")
        exp_xlsx.setToolTip("Resultados y, si los hay, los problemas detectados")
        exp_xlsx.clicked.connect(lambda: self.exportar("xlsx"))
        exp_csv = QPushButton("Exportar CSV…")
        exp_csv.clicked.connect(lambda: self.exportar("csv"))
        self.btn_historial = QPushButton("Guardar en historial")
        self.btn_historial.setObjectName("primario")
        self.btn_historial.clicked.connect(self.guardar_historial)
        acciones.addWidget(ficha)
        acciones.addStretch()
        acciones.addWidget(exp_xlsx)
        acciones.addWidget(exp_csv)
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

        self.modelo_problemas = ModeloTabla(encabezados={COL_ID: "ID estudiante", "Fila": "Fila del archivo"})
        self.proxy_problemas = FiltroTabla([COL_ID, "Columna", "Problema", "Valor"], columna_estado="Nivel")
        self.buscar_problema.textChanged.connect(self.proxy_problemas.set_texto)
        self.filtro_nivel.currentIndexChanged.connect(
            lambda: self.proxy_problemas.set_semaforo(self.filtro_nivel.currentData()))
        self.tabla_problemas = _tabla(self.modelo_problemas, self.proxy_problemas)
        lay.addWidget(self.tabla_problemas, 1)

        acciones = QHBoxLayout()
        ayuda = QLabel("Corrige las filas indicadas en tu archivo y vuelve a abrirlo. "
                       "«Fila del archivo» es el número de fila en Excel (la fila 1 son los títulos).")
        ayuda.setObjectName("leyenda")
        ayuda.setWordWrap(True)
        exportar = QPushButton("Exportar problemas…")
        exportar.clicked.connect(self.exportar_problemas)
        acciones.addWidget(ayuda, 1)
        acciones.addWidget(exportar)
        lay.addLayout(acciones)
        return w

    # ------------------------------------------------------------------ filtros
    def _filtro_cambiado(self) -> None:
        nivel = self.filtro_semaforo.currentData()
        self.proxy.set_semaforo(nivel)
        for clave, k in self._kpi_nivel.items():
            k.set_activa(clave == nivel)
        self.k_error.set_activa(False)

    def _filtrar_nivel(self, nivel) -> None:
        self.pestanas.setCurrentIndex(0)
        self.filtro_semaforo.setCurrentIndex([v for _, v in FILTROS_NIVEL].index(nivel))

    def _ver_errores(self) -> None:
        self.pestanas.setCurrentIndex(1)
        self.filtro_nivel.setCurrentIndex(1)
        for k in self._kpi_nivel.values():
            k.set_activa(False)
        self.k_error.set_activa(True)

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
            "Archivos de estudiantes (*.xlsx *.csv);;Excel (*.xlsx);;CSV (*.csv)",
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
            QMessageBox.warning(self, "No se pudo leer el archivo",
                                f"{e}\n\nSi el archivo está abierto en Excel, ciérralo e inténtalo de nuevo.")
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
        filas_adv = int((res["Avisos"] != "").sum())

        self.k_total.set_valor(f"{len(res):,}")
        self.k_rojo.set_valor(str(int(conteo.get("Rojo", 0))))
        self.k_amarillo.set_valor(str(int(conteo.get("Amarillo", 0))))
        self.k_verde.set_valor(str(int(conteo.get("Verde", 0))))
        self.k_error.set_valor(str(n_err_filas))

        partes = [f"<b>Revisión del archivo:</b> {len(res) + n_err_filas:,} filas leídas"]
        if n_err_filas:
            partes.append(f"<span style='color:{COLOR_NIVEL[ERROR]}'><b>✗</b> {n_err_filas} fila(s) con "
                          "errores no se evaluaron</span>")
        if filas_adv:
            partes.append(f"<span style='color:{COLOR_NIVEL[ADVERTENCIA]}'>⚠ {filas_adv} fila(s) evaluada(s) "
                          "con advertencias</span>")
        if not n_err_filas and problemas.empty:
            partes.append(f"<span style='color:{COLOR_ESTADO['Verde']}'>✔ sin problemas</span>")
        extra = self.lote.validacion.columnas_extra
        if extra:
            partes.append(f"columnas no reconocidas (se ignoraron): {escape(', '.join(map(str, extra)))}")
        texto = " · ".join(partes)
        m = self.lote.metricas
        if m:
            texto += (
                f"<br><b>Comparación con el resultado real</b> ({m['n']:,} estudiantes, "
                f"{m['abandonaron']:,} abandonaron): RetenIA alertó a <b>{m['detectados']:,} de "
                f"{m['abandonaron']:,}</b> que abandonaron (sensibilidad {m['recall'] * 100:.0f} %) y "
                f"<b>{m['precision'] * 100:.0f} %</b> de sus {m['alertas']:,} alertas fueron acertadas "
                f"(precisión). Exactitud global {m['accuracy'] * 100:.0f} % · F1 {m['f1']:.2f} · "
                f"AUC {m['roc_auc']:.2f}."
            )
        self.lbl_resumen.setText(texto)
        self.lbl_resumen.setToolTip(
            "Sensibilidad: de los estudiantes que abandonaron, cuántos recibieron alerta.\n"
            "Precisión: de las alertas emitidas, cuántas correspondían a estudiantes que abandonaron.\n"
            "AUC: capacidad de ordenar a los estudiantes por riesgo (1 = perfecta, 0.5 = al azar)."
            if m else ""
        )
        estilo = "error" if n_err_filas else ("advertencia" if not problemas.empty else "ok")
        self.lbl_resumen.setProperty("estado", estilo)
        self.lbl_resumen.style().unpolish(self.lbl_resumen)
        self.lbl_resumen.style().polish(self.lbl_resumen)

        self.modelo.set_df(res[[c for c in COLUMNAS_VISTA if c in res.columns]])
        self.tabla.resizeColumnsToContents()
        self.tabla.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        self.filtro_semaforo.setCurrentIndex(0)
        self.buscar.clear()

        self.modelo_problemas.set_df(problemas)
        self.tabla_problemas.resizeColumnsToContents()
        self.tabla_problemas.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.filtro_nivel.setCurrentIndex(0)
        self.pestanas.setTabText(0, f"Resultados ({len(res):,})")
        self.pestanas.setTabText(1, f"Problemas ({len(problemas):,})")
        # Si nada se pudo evaluar, abrir directamente la lista de problemas
        self.pestanas.setCurrentIndex(1 if res.empty else 0)

        self.lbl_archivo.setText(f"Archivo: <b>{escape(self.archivo.name)}</b>")
        self.btn_historial.setEnabled(not res.empty)
        self.btn_historial.setText("Guardar en historial")
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
        datos = self.lote.resultado.iloc[fila]  # la tabla muestra las filas de `resultado` en su orden
        resultado = self.servicio.explicar(datos[ALL_FEATURE_COLS].to_dict())
        DialogoFicha(self, self.servicio, resultado, estudiante_id=str(datos[COL_ID])).exec()

    def _ruta_guardar(self, titulo, nombre, filtro):
        ruta, _ = QFileDialog.getSaveFileName(self, titulo, str(DOCUMENTOS / nombre), filtro)
        return ruta or None

    def tabla_exportable(self) -> pd.DataFrame:
        """Resultados con títulos y valores legibles (se pueden volver a abrir en RetenIA)."""
        res = self.lote.resultado
        df = pd.DataFrame({
            "ID estudiante": res[COL_ID],
            "Riesgo (%)": (res["Prob. Deserción"] * 100).round(1),
            "Nivel de riesgo": res["Semáforo"].map(NOMBRE_ESTADO),
            "Avisos": res["Avisos"],
            "Fila del archivo": res["Fila"],
        })
        for col in COLUMNAS_PLANTILLA:
            df[encabezado(col).rstrip(" *")] = res[col].map(lambda v, c=col: valor_plantilla(c, v))
        return df

    def exportar(self, formato: str) -> None:
        if self.lote is None:
            return
        base = self.archivo.stem if self.archivo else "estudiantes"
        filtro = "CSV (*.csv)" if formato == "csv" else "Excel (*.xlsx)"
        ruta = self._ruta_guardar("Exportar resultados", f"resultados_{base}.{formato}", filtro)
        if not ruta:
            return
        df = self.tabla_exportable()
        try:
            if formato == "csv":
                df.to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                with pd.ExcelWriter(ruta, engine="openpyxl") as libro:
                    df.to_excel(libro, index=False, sheet_name="Resultados")
                    if not self.lote.problemas.empty:
                        self._problemas_exportables().to_excel(libro, index=False, sheet_name="Problemas")
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar",
                                 f"No se pudo escribir el archivo (¿está abierto en otro programa?):\n{e}")
            return
        QMessageBox.information(self, "Exportado", f"Resultados guardados en:\n{ruta}")

    def _problemas_exportables(self) -> pd.DataFrame:
        return self.lote.problemas.rename(columns={COL_ID: "ID estudiante", "Fila": "Fila del archivo"})

    def exportar_problemas(self) -> None:
        if self.lote is None or self.lote.problemas.empty:
            QMessageBox.information(self, "Sin problemas", "El archivo no tiene errores ni advertencias.")
            return
        base = self.archivo.stem if self.archivo else "estudiantes"
        ruta = self._ruta_guardar("Exportar problemas", f"problemas_{base}.xlsx",
                                  "Excel (*.xlsx);;CSV (*.csv)")
        if not ruta:
            return
        try:
            if ruta.lower().endswith(".csv"):
                self._problemas_exportables().to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                self._problemas_exportables().to_excel(ruta, index=False, sheet_name="Problemas")
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar", str(e))
            return
        QMessageBox.information(self, "Exportado", f"Problemas guardados en:\n{ruta}")

    def guardar_historial(self) -> None:
        if self.lote is None or self.guardado or self.lote.resultado.empty:
            return
        res = self.lote.resultado
        previo = self.historial.fecha_archivo_guardado(self.archivo.name)
        pregunta = f"¿Guardar las {len(res):,} evaluaciones de «{self.archivo.name}» en el historial?"
        if previo:
            pregunta = (f"Ya guardaste evaluaciones de «{self.archivo.name}» el {fecha_legible(previo)}.\n\n"
                        f"¿Guardar de nuevo las {len(res):,} evaluaciones? Quedarán duplicadas en el historial.")
        r = QMessageBox.question(self, "Guardar en historial", pregunta)
        if r != QMessageBox.StandardButton.Yes:
            return
        umbral = self.servicio.umbral
        perfiles = res[ALL_FEATURE_COLS].to_dict("records")
        filas = [
            {"estudiante_id": str(i), "probabilidad": p, "semaforo": s, "umbral": umbral,
             "perfil": perfil, "notas": f"Archivo: {self.archivo.name}" + (f" · Aviso: {a}" if a else "")}
            for i, p, s, a, perfil in zip(res[COL_ID], res["Prob. Deserción"], res["Semáforo"],
                                          res["Avisos"], perfiles)
        ]
        n = self.historial.guardar_lote(filas)
        self.guardado = True
        self.btn_historial.setEnabled(False)
        self.btn_historial.setText(f"Guardado ✓ ({n:,})")
        self.historial_cambiado.emit()

    def guardar_plantilla_excel(self) -> None:
        ruta = self._ruta_guardar("Guardar plantilla Excel", "plantilla_estudiantes_retenia.xlsx",
                                  "Excel (*.xlsx)")
        if not ruta:
            return
        try:
            crear_plantilla_excel(Path(ruta), self.servicio)
        except OSError as e:
            QMessageBox.critical(self, "No se pudo guardar", f"¿Está abierto en Excel?\n{e}")
            return
        QMessageBox.information(
            self, "Plantilla guardada",
            f"Plantilla guardada en:\n{ruta}\n\nÁbrela en Excel y completa la hoja «Estudiantes». "
            "Las columnas azules (con *) son obligatorias; al seleccionar una celda, Excel te muestra qué "
            "escribir. La hoja «Valores válidos» explica cada columna.",
        )
