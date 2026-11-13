"""Punto de entrada de RetenIA.

    python -m app.main
"""
import sys
import traceback

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from app import APP_NAME, __version__, rutas


def _error_fatal(titulo: str, mensaje: str) -> None:
    QMessageBox.critical(None, f"{APP_NAME} — {titulo}", mensaje)
    sys.exit(1)


def main() -> int:
    if "--autoprueba" in sys.argv:
        from pathlib import Path

        from app.autoprueba import ejecutar
        i = sys.argv.index("--autoprueba")
        salida = sys.argv[i + 1] if len(sys.argv) > i + 1 else "autoprueba.json"
        return ejecutar(Path(salida))

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    if rutas.ICONO.exists():
        app.setWindowIcon(QIcon(str(rutas.ICONO)))
    app.setStyleSheet(rutas.hoja_estilos())

    # Botones estándar de Qt (Cerrar, Sí, No, Cancelar…) en español
    traductor = QTranslator(app)
    if traductor.load(QLocale(QLocale.Language.Spanish), "qtbase", "_",
                      QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(traductor)

    splash = None
    if rutas.ICONO_PNG.exists():
        imagen = QPixmap(str(rutas.ICONO_PNG)).scaled(
            256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        splash = QSplashScreen(imagen)
        splash.show()
        splash.showMessage("Cargando modelo…", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        app.processEvents()

    # Importes pesados (pandas / scikit-learn) después de mostrar el splash
    from app.services.historial import Historial
    from app.services.modelo import ErrorModelo, ServicioModelo
    from app.ui.ventana import VentanaPrincipal

    try:
        servicio = ServicioModelo()
    except ErrorModelo as e:
        _error_fatal("Modelo no válido", str(e))
    except Exception:  # noqa: BLE001 - mostrar cualquier fallo de carga en vez de cerrar en silencio
        _error_fatal("Error al cargar el modelo", traceback.format_exc())

    try:
        historial = Historial()
    except Exception:  # noqa: BLE001
        _error_fatal("Error en el historial", traceback.format_exc())

    ventana = VentanaPrincipal(servicio, historial)
    ventana.show()
    if splash:
        splash.finish(ventana)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
