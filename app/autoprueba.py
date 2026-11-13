"""Autoprueba del ejecutable empaquetado (sin interacción).

    RetenIA.exe --autoprueba resultado.json

Carga y verifica el modelo, evalúa los perfiles de ejemplo, construye la ventana,
genera una ficha PDF y escribe un JSON con el resultado. Código de salida 0 = OK.
Se usa en CI para comprobar que el .exe congelado funciona igual que el código fuente.
"""
import json
import tempfile
import traceback
from pathlib import Path

ESPERADO = {"riesgo": "Rojo", "vulnerable": "Amarillo", "destacado": "Verde"}


def ejecutar(ruta_salida: Path) -> int:
    informe = {"ok": False}
    try:
        from PySide6.QtWidgets import QApplication

        from app import __version__, rutas
        from app.services.historial import Historial
        from app.services.modelo import ServicioModelo
        from app.services.reporte import exportar_pdf, ficha_html
        from app.ui.ventana import VentanaPrincipal

        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(rutas.hoja_estilos())
        servicio = ServicioModelo()
        resultados = {c: servicio.evaluar(p) for c, p in servicio.perfiles.items()}
        informe["version"] = __version__
        informe["probabilidades"] = {c: round(r.probabilidad, 4) for c, r in resultados.items()}
        informe["semaforos"] = {c: r.semaforo for c, r in resultados.items()}

        with tempfile.TemporaryDirectory() as tmp:
            historial = Historial(Path(tmp) / "historial.db")
            ventana = VentanaPrincipal(servicio, historial)
            ventana.vistas["lote"].cargar(rutas.PLANTILLA_LOTE)
            informe["filas_lote"] = ventana.vistas["lote"].modelo.rowCount()
            pdf = exportar_pdf(
                ficha_html(resultados["riesgo"], servicio.medianas, estudiante_id="AUTOPRUEBA",
                           modelo=servicio.nombre_modelo),
                Path(tmp) / "ficha.pdf",
            )
            informe["pdf_bytes"] = pdf.stat().st_size

            from app.core.scoring import leer_excel
            from app.services.plantilla import crear_plantilla_excel
            xlsx = crear_plantilla_excel(Path(tmp) / "plantilla.xlsx", servicio)
            lote_xlsx = servicio.evaluar_lote(leer_excel(xlsx))
            informe["plantilla_excel"] = {"filas": len(lote_xlsx.resultado),
                                          "problemas": len(lote_xlsx.problemas)}
            ventana.close()

        informe["ok"] = (
            informe["semaforos"] == ESPERADO and informe["filas_lote"] == 4 and informe["pdf_bytes"] > 5000
            and informe["plantilla_excel"] == {"filas": 4, "problemas": 0}
        )
    except Exception:  # noqa: BLE001 - el informe debe recoger cualquier fallo
        informe["error"] = traceback.format_exc()
    Path(ruta_salida).write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if informe["ok"] else 1
