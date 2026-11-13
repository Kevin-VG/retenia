"""Información del modelo, privacidad, uso ético y atribuciones."""
import platform
from html import escape

import PySide6
import sklearn
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from app import APP_NAME, __version__
from app.core.scoring import CORTE_ROJO
from app.ui.widgets import Tarjeta, titulo_seccion


class VistaAcerca(QWidget):
    def __init__(self, servicio, historial, parent=None):
        super().__init__(parent)
        meta = servicio.config
        m = meta["metricas_test_umbral_050"]
        u = servicio.umbral
        corte = max(CORTE_ROJO, u)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lay.addWidget(titulo_seccion(f"Acerca de {APP_NAME}", f"Versión {__version__}"))

        def bloque(titulo, html):
            t = Tarjeta()
            cab = QLabel(titulo)
            cab.setObjectName("tituloTarjeta")
            cuerpo = QLabel(html)
            cuerpo.setWordWrap(True)
            cuerpo.setTextFormat(Qt.TextFormat.RichText)
            cuerpo.setOpenExternalLinks(True)
            cuerpo.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            t.cuerpo.addWidget(cab)
            t.cuerpo.addWidget(cuerpo)
            lay.addWidget(t)

        bloque("Modelo", f"""
            <b>Algoritmo:</b> {escape(servicio.nombre_modelo)} (scikit-learn {sklearn.__version__})<br>
            <b>Entrenado con:</b> {meta['n_train']:,} estudiantes · evaluado en {meta['n_test']:,} estudiantes de prueba<br>
            <b>Rendimiento en prueba (umbral 0.50):</b> F1 {m['f1']:.4f} · Precision {m['precision'] * 100:.1f} % ·
            Recall {m['recall'] * 100:.1f} % · Accuracy {m['accuracy'] * 100:.1f} % · ROC-AUC {m['roc_auc']:.4f}<br>
            <b>Umbral operativo:</b> {u:.2f} → Verde &lt; {u * 100:.0f} % · Amarillo {u * 100:.0f}–{corte * 100:.0f} % ·
            Rojo ≥ {corte * 100:.0f} %
        """)

        bloque("Privacidad", f"""
            Todo se calcula en este equipo, sin conexión a internet. Las evaluaciones guardadas viven solo en<br>
            <code>{escape(str(historial.ruta))}</code><br>
            Ningún dato se envía a servidores externos.
        """)

        bloque("Uso responsable", """
            RetenIA es una herramienta de <b>apoyo</b> para Bienestar Universitario. La alerta nunca sanciona: su
            único fin es ofrecer acompañamiento oportuno. Las probabilidades son estimaciones estadísticas
            basadas en datos históricos de otra institución; la decisión final siempre corresponde a una persona.
            Los factores mostrados describen cómo razona el modelo, no causas comprobadas.
        """)

        bloque("Créditos", f"""
            Proyecto de Sistemas Inteligentes y Machine Learning — UPN.<br>
            Dataset: <a href="https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success">
            Predict Students' Dropout and Academic Success</a> (UCI #697), Realinho et al., licencia CC BY 4.0.<br>
            Interfaz: Qt for Python (PySide6 {PySide6.__version__}, LGPL v3) · scikit-learn {sklearn.__version__} (BSD-3).<br>
            Python {platform.python_version()} · {escape(platform.platform())}
        """)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(contenido)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(scroll)
