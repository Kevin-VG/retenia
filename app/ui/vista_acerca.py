"""Acerca de: cómo leer los resultados, fiabilidad, limitaciones, privacidad, ajustes y licencias."""
from html import escape

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app import APP_NAME, __version__
from app.core.scoring import TEXTO_ESTADO, texto_escala
from app.services import preferencias
from app.ui.widgets import COLOR_ESTADO, Tarjeta, titulo_seccion


class VistaAcerca(QWidget):
    def __init__(self, servicio, historial, parent=None):
        super().__init__(parent)
        meta = servicio.config
        m = meta["metricas_test_umbral_050"]
        self.historial = historial

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lay.addWidget(titulo_seccion(f"Acerca de {APP_NAME}", f"Versión {__version__}"))

        def bloque(titulo, html=""):
            t = Tarjeta()
            cab = QLabel(titulo)
            cab.setObjectName("tituloTarjeta")
            t.cuerpo.addWidget(cab)
            if html:
                cuerpo = QLabel(html)
                cuerpo.setWordWrap(True)
                cuerpo.setTextFormat(Qt.TextFormat.RichText)
                cuerpo.setOpenExternalLinks(True)
                cuerpo.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                t.cuerpo.addWidget(cuerpo)
            lay.addWidget(t)
            return t

        bloque("Qué hace", f"""
            {APP_NAME} estima el riesgo de deserción de cada estudiante a partir de su avance académico
            y su situación económica, para que el equipo de bienestar o tutoría pueda priorizar el
            acompañamiento. Puedes evaluar a un estudiante con el formulario o a un grupo con la
            plantilla de Excel, y guardar los resultados con notas de seguimiento.
        """)

        niveles = "<br>".join(
            f"<span style='color:{COLOR_ESTADO[c]}'>●</span> <b>{TEXTO_ESTADO[c][0]}:</b> {TEXTO_ESTADO[c][1]}"
            for c in ("Verde", "Amarillo", "Rojo")
        )
        bloque("Cómo leer el resultado", f"""
            {niveles}<br><span style='color:#52514e'>{escape(texto_escala(servicio.umbral))}</span><br><br>
            Los «datos que influyen» indican cuánto cambiaría el riesgo de un estudiante típico si solo
            tuviera ese dato. Son una guía para orientar la conversación, no una causa comprobada.
        """)

        if "metricas_test_umbral_operativo" in meta:
            op = meta["metricas_test_umbral_operativo"]
            detalle = (
                f"detectó a <b>{op['detectados']} de {op['abandonaron']}</b> estudiantes que abandonaron "
                f"({op['recall'] * 100:.0f} %) y el <b>{op['precision'] * 100:.0f} %</b> de sus alertas fue "
                f"acertado"
            )
        else:
            detalle = (f"con un corte de referencia del 50 %, detectó al {m['recall'] * 100:.0f} % de los "
                       f"estudiantes que abandonaron y el {m['precision'] * 100:.0f} % de sus alertas fue acertado")
        bloque("Fiabilidad", f"""
            En pruebas con {meta['n_test']:,} estudiantes cuyo resultado ya se conocía, {APP_NAME} {detalle}.
            Al comparar a un estudiante que abandonó con otro que no, asignó más riesgo al primero en el
            {m['roc_auc'] * 100:.0f} % de los casos.<br><br>
            Si cargas un archivo con la columna «Abandonó», {APP_NAME} compara sus alertas con el
            resultado real de tus estudiantes.
        """)

        bloque("Alcance y limitaciones", f"""
            El modelo se construyó con datos históricos de {meta['n_train'] + meta['n_test']:,} estudiantes
            de educación superior de otra institución; por eso la lista de carreras corresponde a esa
            institución. Conviene validar los resultados con datos propios antes de usarlos de forma
            generalizada.<br><br>
            {APP_NAME} es una herramienta de <b>apoyo</b>: la alerta nunca debe usarse para sancionar ni
            para negar beneficios. Su único fin es ofrecer acompañamiento oportuno, y la decisión final
            siempre corresponde a una persona.
        """)

        privacidad = bloque("Privacidad", """
            Todo se calcula en este equipo, sin conexión a internet. Las evaluaciones guardadas se
            almacenan solo en esta computadora; ningún dato se envía a servidores externos.
        """)
        carpeta = QPushButton("Abrir carpeta de datos")
        carpeta.setToolTip(str(historial.ruta.parent))
        carpeta.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.historial.ruta.parent))))
        privacidad.cuerpo.addWidget(carpeta, 0, Qt.AlignmentFlag.AlignLeft)

        ajustes = bloque("Datos de la ficha PDF")
        ayuda = QLabel("Aparecen en el encabezado y al pie de cada ficha exportada. Se guardan al escribir.")
        ayuda.setObjectName("leyenda")
        ajustes.cuerpo.addWidget(ayuda)
        form = QFormLayout()
        valores = preferencias.cargar()
        self.campos = {}
        for clave, etiqueta, ejemplo in (
            ("institucion", "Institución", "Nombre de la universidad o instituto"),
            ("area", "Área", "Por ejemplo: Bienestar Universitario"),
            ("responsable", "Elaborado por", "Nombre de quien firma las fichas"),
        ):
            campo = QLineEdit(valores[clave])
            campo.setPlaceholderText(ejemplo)
            campo.textChanged.connect(lambda *_: self._guardado.start())
            form.addRow(etiqueta, campo)
            self.campos[clave] = campo
        ajustes.cuerpo.addLayout(form)
        self._guardado = QTimer(self, singleShot=True, interval=500)
        self._guardado.timeout.connect(self.guardar_preferencias)

        bloque("Licencias de terceros", """
            Modelo construido con el conjunto de datos «Predict Students' Dropout and Academic Success»
            (Realinho et al., <a href="https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success">UCI
            Machine Learning Repository</a>), licencia CC BY 4.0.<br>
            Interfaz: Qt for Python (PySide6), licencia LGPL v3 · Cálculo: scikit-learn (BSD-3), pandas y
            NumPy (BSD-3).
        """)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(contenido)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(scroll)

    def guardar_preferencias(self) -> None:
        try:
            preferencias.guardar({c: w.text() for c, w in self.campos.items()})
        except OSError:
            pass  # no bloquear la interfaz si la carpeta no es escribible
