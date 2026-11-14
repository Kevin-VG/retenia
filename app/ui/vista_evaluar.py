"""Evaluación individual: formulario, resultado, factores, plan de acción, historial y PDF."""
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.core.scoring import TEXTO_ESTADO, texto_escala
from app.core.variables import (
    CARRERAS, COL_APROB_1, COL_APROB_2, COL_BECA, COL_CARRERA, COL_CONV_2, COL_DEUDA,
    COL_EDAD, COL_MATRIC_1, COL_MATRIC_2, COL_PAGOS, ETIQUETAS, describir_valor,
)
from app.services import preferencias
from app.services.reporte import ficha_html
from app.ui.dialogo_ficha import guardar_pdf_interactivo
from app.ui.widgets import (
    COLOR_ESTADO, FONDO_ESTADO, CampoNumero, OpcionSiNo, SelectorBusqueda, Tarjeta, titulo_seccion,
)

GRIS = "#64748b"


class VistaEvaluar(QWidget):
    historial_cambiado = Signal()

    def __init__(self, servicio, historial, parent=None):
        super().__init__(parent)
        self.servicio = servicio
        self.historial = historial
        self.resultado = None
        self.guardado = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 24)
        raiz.addWidget(titulo_seccion(
            "Evaluar estudiante",
            "Completa los datos académicos y económicos del estudiante y pulsa «Evaluar riesgo».",
        ))

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(20)
        cuerpo.addWidget(self._crear_formulario(), 4)
        cuerpo.addWidget(self._crear_panel_resultado(), 6)
        raiz.addLayout(cuerpo, 1)

    # ------------------------------------------------------------------ formulario
    def _crear_formulario(self) -> QWidget:
        tarjeta = Tarjeta()
        tarjeta.setMinimumWidth(380)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(8)

        self.id_estudiante = QLineEdit()
        self.id_estudiante.setPlaceholderText("Código del estudiante (opcional)")
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre (opcional)")
        self.nombre.setToolTip("Solo se guarda en este equipo.")
        form.addRow(self._seccion("Identificación"))
        form.addRow("ID estudiante", self.id_estudiante)
        form.addRow("Nombre", self.nombre)

        self.campos = {}
        carrera = SelectorBusqueda(CARRERAS, "Escribe o elige la carrera…")
        carrera.setToolTip("Escribe parte del nombre para buscar, o abre la lista con la flecha")
        self.campos[COL_CARRERA] = carrera
        form.addRow(self._seccion("Datos generales"))
        form.addRow(ETIQUETAS[COL_CARRERA], carrera)
        self.campos[COL_EDAD] = self._spin(COL_EDAD)
        form.addRow(ETIQUETAS[COL_EDAD], self.campos[COL_EDAD])

        form.addRow(self._seccion("1er semestre"))
        for col, etiqueta in ((COL_MATRIC_1, "Materias matriculadas"), (COL_APROB_1, "Materias aprobadas")):
            self.campos[col] = self._spin(col)
            form.addRow(etiqueta, self.campos[col])

        form.addRow(self._seccion("2do semestre"))
        for col, etiqueta in ((COL_MATRIC_2, "Materias matriculadas"), (COL_APROB_2, "Materias aprobadas"),
                              (COL_CONV_2, "Materias convalidadas")):
            self.campos[col] = self._spin(col)
            form.addRow(etiqueta, self.campos[col])
        self.campos[COL_CONV_2].setToolTip(
            "Materias reconocidas por estudios anteriores (sin cursarlas). Normalmente 0.")

        form.addRow(self._seccion("Situación económica"))
        for col in (COL_PAGOS, COL_DEUDA, COL_BECA):
            self.campos[col] = OpcionSiNo()
            form.addRow(ETIQUETAS[col], self.campos[col])

        for widget in self.campos.values():
            widget.valueChanged.connect(lambda w=widget: self._dato_cambiado(w))

        tarjeta.cuerpo.addLayout(form)

        self.errores = QLabel()
        self.errores.setObjectName("errores")
        self.errores.setWordWrap(True)
        self.errores.hide()
        tarjeta.cuerpo.addWidget(self.errores)

        botones = QHBoxLayout()
        limpiar = QPushButton("Nuevo estudiante")
        limpiar.setToolTip("Vacía el formulario para evaluar a otro estudiante")
        limpiar.clicked.connect(self.limpiar)
        evaluar = QPushButton("Evaluar riesgo")
        evaluar.setObjectName("primario")
        evaluar.setDefault(True)
        evaluar.clicked.connect(self.evaluar)
        botones.addWidget(limpiar)
        botones.addWidget(evaluar, 1)
        tarjeta.cuerpo.addLayout(botones)
        tarjeta.cuerpo.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(tarjeta)
        self.limpiar()
        return scroll

    @staticmethod
    def _seccion(texto: str) -> QLabel:
        lbl = QLabel(texto.upper())
        lbl.setObjectName("seccionForm")
        return lbl

    def _spin(self, col: str) -> CampoNumero:
        """Campo numérico que empieza vacío, con botones −/+ y teclas ↑/↓."""
        minimo, maximo = self.servicio.rangos[col]
        campo = CampoNumero(minimo, maximo)
        campo.setToolTip(f"Valores permitidos: de {minimo} a {maximo}")
        return campo

    @staticmethod
    def _vacio(widget) -> bool:
        return widget.value() is None

    def _aplicar(self, valores: dict) -> None:
        """Rellena el formulario con valores internos (códigos)."""
        for col, widget in self.campos.items():
            widget.setValue(valores[col])

    def limpiar(self) -> None:
        """Vacía el formulario y oculta el resultado anterior."""
        self.id_estudiante.clear()
        self.nombre.clear()
        for widget in self.campos.values():
            widget.vaciar()
            widget.set_invalido(False)
        self.errores.hide()
        self.resultado = None
        if hasattr(self, "panel"):
            self.panel.hide()
            self.vacio.show()

    def entradas(self) -> dict:
        return {col: w.value() for col, w in self.campos.items()}

    def _dato_cambiado(self, widget) -> None:
        widget.set_invalido(False)
        if self.resultado is not None and self.panel.isVisible():
            self.aviso_cambios.show()
            self.btn_guardar.setEnabled(False)
            self.btn_pdf.setEnabled(False)

    # ------------------------------------------------------------------ resultado
    def _crear_panel_resultado(self) -> QWidget:
        contenedor = QWidget()
        lay = QVBoxLayout(contenedor)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.vacio = Tarjeta()
        cab = QLabel("Resultado")
        cab.setObjectName("tituloTarjeta")
        aviso = QLabel(
            "Completa el formulario y pulsa <b>Evaluar riesgo</b>. Verás el riesgo estimado de "
            "deserción, los datos que más influyen y un plan de acción sugerido.<br><br>"
            "<b>Cómo se interpreta</b><br>"
            + "<br>".join(
                f"<span style='color:{COLOR_ESTADO[c]}'>●</span> <b>{TEXTO_ESTADO[c][0]}:</b> "
                f"{TEXTO_ESTADO[c][1]}"
                for c in ("Verde", "Amarillo", "Rojo")
            )
            + f"<br><span style='color:{GRIS}'>{escape(texto_escala(self.servicio.umbral))}</span>"
        )
        aviso.setObjectName("aviso")
        aviso.setWordWrap(True)
        aviso.setTextFormat(Qt.TextFormat.RichText)
        self.vacio.cuerpo.addWidget(cab)
        self.vacio.cuerpo.addWidget(aviso)
        lay.addWidget(self.vacio)

        self.panel = QWidget()
        panel = QVBoxLayout(self.panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(14)

        self.aviso_cambios = QLabel("Cambiaste datos del formulario. Pulsa «Evaluar riesgo» para "
                                    "actualizar el resultado.")
        self.aviso_cambios.setObjectName("avisoCambios")
        self.aviso_cambios.setWordWrap(True)
        self.aviso_cambios.hide()
        panel.addWidget(self.aviso_cambios)

        self.tarjeta_prob = Tarjeta()
        self.tarjeta_prob.setObjectName("tarjetaResultado")
        fila = QHBoxLayout()
        col_izq = QVBoxLayout()
        lbl = QLabel("Riesgo estimado de deserción")
        lbl.setObjectName("kpiTitulo")
        self.lbl_prob = QLabel()
        self.lbl_prob.setObjectName("probGrande")
        col_izq.addWidget(lbl)
        col_izq.addWidget(self.lbl_prob)
        fila.addLayout(col_izq, 1)
        col_der = QVBoxLayout()
        self.lbl_estado = QLabel()
        self.lbl_estado.setObjectName("estado")
        self.lbl_detalle = QLabel()
        self.lbl_detalle.setWordWrap(True)
        col_der.addWidget(self.lbl_estado)
        col_der.addWidget(self.lbl_detalle)
        fila.addLayout(col_der, 1)
        self.tarjeta_prob.cuerpo.addLayout(fila)
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(12)
        self.tarjeta_prob.cuerpo.addWidget(self.barra)
        self.lbl_leyenda = QLabel()
        self.lbl_leyenda.setObjectName("leyenda")
        self.lbl_leyenda.setWordWrap(True)
        self.tarjeta_prob.cuerpo.addWidget(self.lbl_leyenda)
        panel.addWidget(self.tarjeta_prob)

        factores = QGridLayout()
        factores.setHorizontalSpacing(14)
        self.t_suben, self.lbl_suben = self._tarjeta_texto("Datos que aumentan el riesgo")
        self.t_bajan, self.lbl_bajan = self._tarjeta_texto("Datos que reducen el riesgo")
        factores.addWidget(self.t_suben, 0, 0)
        factores.addWidget(self.t_bajan, 0, 1)
        panel.addLayout(factores)
        self.lbl_explicacion = QLabel()
        self.lbl_explicacion.setObjectName("leyenda")
        self.lbl_explicacion.setWordWrap(True)
        panel.addWidget(self.lbl_explicacion)

        self.t_plan, self.lbl_plan = self._tarjeta_texto("Plan de acción sugerido")
        panel.addWidget(self.t_plan)

        self.notas = QPlainTextEdit()
        self.notas.setPlaceholderText("Notas de seguimiento (opcional; se guardan con la evaluación "
                                      "y aparecen en la ficha PDF)")
        self.notas.setMaximumHeight(70)
        panel.addWidget(self.notas)

        acciones = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar en historial")
        self.btn_guardar.setObjectName("primario")
        self.btn_guardar.clicked.connect(self.guardar)
        self.btn_pdf = QPushButton("Exportar ficha PDF…")
        self.btn_pdf.clicked.connect(self.exportar_pdf)
        acciones.addWidget(self.btn_guardar)
        acciones.addWidget(self.btn_pdf)
        acciones.addStretch()
        panel.addLayout(acciones)
        panel.addStretch()

        self.panel.hide()
        lay.addWidget(self.panel)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(contenedor)
        return scroll

    @staticmethod
    def _tarjeta_texto(titulo: str):
        t = Tarjeta()
        cab = QLabel(titulo)
        cab.setObjectName("tituloTarjeta")
        cuerpo = QLabel()
        cuerpo.setWordWrap(True)
        cuerpo.setTextFormat(Qt.TextFormat.RichText)
        t.cuerpo.addWidget(cab)
        t.cuerpo.addWidget(cuerpo)
        t.cuerpo.addStretch()
        return t, cuerpo

    # ------------------------------------------------------------------ acciones
    def evaluar(self) -> None:
        faltan = [col for col, w in self.campos.items() if self._vacio(w)]
        for col, widget in self.campos.items():
            widget.set_invalido(col in faltan)
        if faltan:
            if len(faltan) > 3:
                texto = f"Faltan {len(faltan)} datos: completa los campos marcados en rojo."
            else:
                texto = "Completa los campos marcados en rojo:<br>" + "<br>".join(
                    f"• {escape(ETIQUETAS[c])}" for c in faltan)
            self.errores.setText(texto)
            self.errores.show()
            return
        entradas = self.entradas()
        errores = self.servicio.validar(entradas)
        if errores:
            self.errores.setText("<br>".join(f"• {escape(e)}" for e in errores))
            self.errores.show()
            return
        self.errores.hide()
        self.resultado = self.servicio.evaluar(entradas)
        self.guardado = False
        self.notas.clear()
        self._mostrar(self.resultado)

    def _mostrar(self, r) -> None:
        color = COLOR_ESTADO[r.semaforo]
        titulo, detalle = TEXTO_ESTADO[r.semaforo]
        self.lbl_prob.setText(f"{r.probabilidad * 100:.1f} %")
        self.lbl_prob.setStyleSheet(f"color: {color};")
        self.lbl_estado.setText(f"● {titulo}")
        self.lbl_estado.setStyleSheet(f"color: {color};")
        self.lbl_detalle.setText(detalle)
        self.tarjeta_prob.setStyleSheet(
            f"#tarjetaResultado {{ background: {FONDO_ESTADO[r.semaforo]}; border-color: {color}; }}"
        )
        self.barra.setValue(int(round(r.probabilidad * 1000)))
        self.barra.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 6px; }}")
        self.lbl_leyenda.setText(texto_escala(r.umbral))

        med = self.servicio.medianas

        def lista(factores, vacio, color_efecto):
            if not factores:
                return f"<i style='color:{GRIS}'>{vacio}</i>"
            filas = "".join(
                f"<tr><td style='padding-bottom:6px'><b>{escape(ETIQUETAS[c])}</b><br>"
                f"<span style='color:{GRIS}'>Estudiante: {escape(describir_valor(c, r.perfil[c]))} · "
                f"típico: {escape(describir_valor(c, med[c]))}</span></td>"
                f"<td align='right' style='padding-left:10px; color:{color_efecto}'>"
                f"<b>{v * 100:+.0f}</b><br><span style='font-size:8pt'>puntos</span></td></tr>"
                for c, v in factores
            )
            return f"<table width='100%' cellspacing='0'>{filas}</table>"

        self.lbl_suben.setText(lista(r.suben, "Ningún dato aumenta el riesgo de forma relevante.",
                                     COLOR_ESTADO["Rojo"]))
        self.lbl_bajan.setText(lista(r.bajan, "Ningún dato reduce el riesgo de forma relevante.",
                                     COLOR_ESTADO["Verde"]))
        self.lbl_explicacion.setText(
            f"«Típico» es el valor más habitual entre los estudiantes. Los puntos indican cuánto cambiaría "
            f"el riesgo de un estudiante típico ({r.riesgo_mediano * 100:.0f} %) si solo tuviera ese dato. "
            "Es una guía orientativa: no indica una causa y los efectos no se suman."
        )
        self.lbl_plan.setText("<br>".join(
            f"• <b>{escape(t)}:</b> {escape(d)}" for t, d in r.recomendaciones
        ))
        self.btn_guardar.setEnabled(True)
        self.btn_guardar.setText("Guardar en historial")
        self.btn_pdf.setEnabled(True)
        self.aviso_cambios.hide()
        self.vacio.hide()
        self.panel.show()

    def guardar(self) -> None:
        if self.resultado is None or self.guardado:
            return
        r = self.resultado
        self.historial.guardar(
            estudiante_id=self.id_estudiante.text(), nombre=self.nombre.text(), origen="individual",
            probabilidad=r.probabilidad, semaforo=r.semaforo, umbral=r.umbral,
            perfil=r.perfil, entradas=r.entradas, notas=self.notas.toPlainText(),
        )
        self.guardado = True
        self.btn_guardar.setEnabled(False)
        self.btn_guardar.setText("Guardado ✓")
        self.historial_cambiado.emit()

    def exportar_pdf(self) -> None:
        if self.resultado is None:
            return
        html = ficha_html(
            self.resultado, self.servicio.medianas, estudiante_id=self.id_estudiante.text(),
            nombre=self.nombre.text(), notas=self.notas.toPlainText(), **preferencias.cargar(),
        )
        guardar_pdf_interactivo(self, html, self.id_estudiante.text())
