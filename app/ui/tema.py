"""Tema visual de la app: siempre claro, aunque Windows esté en modo oscuro.

La hoja de estilos usa texto oscuro sobre fondos claros. Si Qt adoptara la paleta oscura del
sistema, los diálogos (QMessageBox, menús, listas desplegables…) quedarían con texto oscuro sobre
fondo oscuro. Por eso se fija el esquema de color claro y una paleta clara explícita.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette

from app import rutas

TINTA = "#0c1938"
FONDO = "#f8fafc"
BLANCO = "#ffffff"
PRIMARIO = "#2563eb"


def paleta_clara() -> QPalette:
    p = QPalette()
    colores = {
        QPalette.ColorRole.Window: FONDO,
        QPalette.ColorRole.WindowText: TINTA,
        QPalette.ColorRole.Base: BLANCO,
        QPalette.ColorRole.AlternateBase: "#f1f5f9",
        QPalette.ColorRole.Text: TINTA,
        QPalette.ColorRole.PlaceholderText: "#94a3b8",
        QPalette.ColorRole.Button: BLANCO,
        QPalette.ColorRole.ButtonText: TINTA,
        QPalette.ColorRole.BrightText: BLANCO,
        QPalette.ColorRole.Highlight: PRIMARIO,
        QPalette.ColorRole.HighlightedText: BLANCO,
        QPalette.ColorRole.ToolTipBase: TINTA,
        QPalette.ColorRole.ToolTipText: BLANCO,
        QPalette.ColorRole.Link: "#1d4ed8",
        QPalette.ColorRole.Light: BLANCO,
        QPalette.ColorRole.Midlight: "#e2e8f0",
        QPalette.ColorRole.Mid: "#cbd5e1",
        QPalette.ColorRole.Dark: "#94a3b8",
        QPalette.ColorRole.Shadow: "#64748b",
    }
    for rol, color in colores.items():
        p.setColor(rol, QColor(color))
    for rol in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, rol, QColor("#94a3b8"))
    return p


def aplicar_tema(app) -> None:
    """Estilo Fusion, esquema claro, paleta clara, fuente y hoja de estilos de la app."""
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setPalette(paleta_clara())
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(rutas.hoja_estilos())
