"""Evaluación individual: formulario, resultado, factores, plan de acción, historial y PDF."""
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app.core.scoring import CORTE_ROJO, TEXTO_ESTADO
from app.core.variables import (
    CARRERAS, COL_APROB_1, COL_APROB_2, COL_BECA, COL_CARRERA, COL_CONV_2, COL_DEUDA,
    COL_EDAD, COL_MATRIC_1, COL_MATRIC_2, COL_PAGOS, ENTRADAS_FORMULARIO, ETIQUETAS,
    describir_valor,
)
from app.services.reporte import ficha_html
from app.ui.dialogo_ficha import guardar_pdf_interactivo
from app.ui.widgets import COLOR_ESTADO, FONDO_ESTADO, Tarjeta, titulo_seccion

NOMBRES_PERFIL = {"riesgo": "Estudiante en riesgo", "vulnerable": "Estudiante vulnerable",
                  "destacado": "Estudiante destacado"}


def _si_no(valor_si_primero: bool) -> QComboBox:
    combo = QComboBox()
    opciones = [("Sí", 1), ("No", 0)] if valor_si_primero else [("No", 0), ("Sí", 1)]
    for texto, valor in opciones:
        combo.addItem(texto, valor)
    return combo


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
            "Ingresa los datos clave del estudiante. Las demás variables del modelo toman el valor "
            "mediano de los estudiantes de entrenamiento.",
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

        ejemplos = QHBoxLayout()
        ejemplos.addWidget(QLabel("Ejemplos:"))
        for clave, texto in NOMBRES_PERFIL.items():
            btn = QPushButton(texto.replace("Estudiante ", "").capitalize())
            btn.setObjectName("chip")
            btn.setToolTip(f"Cargar perfil de ejemplo: {texto}")
            btn.clicked.connect(lambda _=False, c=clave: self.cargar_perfil(c))
            ejemplos.addWidget(btn)
        ejemplos.addStretch()
        tarjeta.cuerpo.addLayout(ejemplos)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(8)

        self.id_estudiante = QLineEdit()
        self.id_estudiante.setPlaceholderText("Código o ID (opcional)")
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre (opcional, solo se guarda en este equipo)")
        form.addRow("ID estudiante", self.id_estudiante)
        form.addRow("Nombre", self.nombre)

        self.campos = {}
        carrera = QComboBox()
        for codigo, nombre in sorted(CARRERAS.items(), key=lambda kv: kv[1]):
            carrera.addItem(nombre, codigo)
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

        form.addRow(self._seccion("Situación económica"))
        self.campos[COL_PAGOS] = _si_no(True)
        self.campos[COL_DEUDA] = _si_no(False)
        self.campos[COL_BECA] = _si_no(False)
        for col in (COL_PAGOS, COL_DEUDA, COL_BECA):
            form.addRow(ETIQUETAS[col], self.campos[col])

        tarjeta.cuerpo.addLayout(form)

        self.errores = QLabel()
        self.errores.setObjectName("errores")
        self.errores.setWordWrap(True)
        self.errores.hide()
        tarjeta.cuerpo.addWidget(self.errores)

        botones = QHBoxLayout()
        limpiar = QPushButton("Limpiar")
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

    def _spin(self, col: str) -> QSpinBox:
        minimo, maximo = self.servicio.rangos[col]
        spin = QSpinBox()
        spin.setRange(minimo, maximo)
        spin.setToolTip(f"Valores permitidos: {minimo} a {maximo}")
        return spin

    def _set_combo(self, combo: QComboBox, valor) -> None:
        i = combo.findData(int(valor))
        if i >= 0:
            combo.setCurrentIndex(i)

    def _aplicar(self, valores: dict) -> None:
        for col, widget in self.campos.items():
            if isinstance(widget, QComboBox):
                self._set_combo(widget, valores[col])
            else:
                widget.setValue(int(valores[col]))

    def limpiar(self) -> None:
        """Vuelve al perfil mediano de entrenamiento."""
        self.id_estudiante.clear()
        self.nombre.clear()
        self._aplicar({c: self.servicio.medianas[c] for c in ENTRADAS_FORMULARIO})
        self.errores.hide()

    def cargar_perfil(self, clave: str) -> None:
        self._aplicar(self.servicio.perfiles[clave])
        self.id_estudiante.setText(f"EJ-{clave.upper()}")
        self.nombre.clear()
        self.evaluar()

    def entradas(self) -> dict:
        return {
            col: (w.currentData() if isinstance(w, QComboBox) else w.value())
            for col, w in self.campos.items()
        }

    # ------------------------------------------------------------------ resultado
    def _crear_panel_resultado(self) -> QWidget:
        contenedor = QWidget()
        lay = QVBoxLayout(contenedor)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.vacio = Tarjeta()
        aviso = QLabel("Elige un ejemplo o completa el formulario y pulsa <b>Evaluar riesgo</b>.")
        aviso.setObjectName("aviso")
        aviso.setWordWrap(True)
        self.vacio.cuerpo.addWidget(aviso)
        lay.addWidget(self.vacio)

        self.panel = QWidget()
        panel = QVBoxLayout(self.panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(14)

        self.tarjeta_prob = Tarjeta()
        self.tarjeta_prob.setObjectName("tarjetaResultado")
        fila = QHBoxLayout()
        col_izq = QVBoxLayout()
        lbl = QLabel("Probabilidad estimada de abandono")
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
        self.t_suben, self.lbl_suben = self._tarjeta_texto("Aumentan el riesgo")
        self.t_bajan, self.lbl_bajan = self._tarjeta_texto("Reducen el riesgo")
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
        self.notas.setPlaceholderText("Notas de seguimiento (opcional; se guardan con la evaluación)")
        self.notas.setMaximumHeight(70)
        panel.addWidget(self.notas)

        acciones = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar en historial")
        self.btn_guardar.setObjectName("primario")
        self.btn_guardar.clicked.connect(self.guardar)
        btn_pdf = QPushButton("Exportar ficha PDF…")
        btn_pdf.clicked.connect(self.exportar_pdf)
        acciones.addWidget(self.btn_guardar)
        acciones.addWidget(btn_pdf)
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
        corte = max(CORTE_ROJO, r.umbral)
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
        self.lbl_leyenda.setText(
            f"Bajo < {r.umbral * 100:.0f} %  ·  Moderado {r.umbral * 100:.0f}–{corte * 100:.0f} %  ·  "
            f"Alto ≥ {corte * 100:.0f} %   (umbral operativo {r.umbral:.2f})"
        )

        med = self.servicio.medianas

        def lista(factores, vacio):
            if not factores:
                return f"<i>{vacio}</i>"
            return "<br>".join(
                f"<b>{escape(ETIQUETAS[c])}:</b> {escape(describir_valor(c, r.perfil[c]))} "
                f"<span style='color:#64748b'>(mediano: {escape(describir_valor(c, med[c]))})</span> "
                f"· <b>{v * 100:+.0f} pts</b>"
                for c, v in factores
            )

        self.lbl_suben.setText(lista(r.suben, "Ningún dato lo aumenta de forma relevante."))
        self.lbl_bajan.setText(lista(r.bajan, "Ningún dato lo reduce de forma relevante."))
        self.lbl_explicacion.setText(
            f"El perfil mediano tiene {r.riesgo_mediano * 100:.0f} % de riesgo. Cada línea muestra cuántos "
            "puntos cambia si solo ese dato fuera distinto. Los efectos no se suman y reflejan cómo razona "
            "el modelo, no una causa comprobada."
        )
        self.lbl_plan.setText("<br>".join(
            f"• <b>{escape(t)}:</b> {escape(d)}" for t, d in r.recomendaciones
        ))
        self.btn_guardar.setEnabled(True)
        self.btn_guardar.setText("Guardar en historial")
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
            nombre=self.nombre.text(), notas=self.notas.toPlainText(),
            modelo=self.servicio.nombre_modelo,
        )
        guardar_pdf_interactivo(self, html, self.id_estudiante.text())
