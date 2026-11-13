"""Pruebas de humo de la interfaz (plataforma Qt 'offscreen', sin pantalla)."""
import pandas as pd

from app import rutas
from app.services.reporte import exportar_pdf, ficha_html


def test_pdf_de_la_ficha(qapp, servicio, tmp_path):
    r = servicio.evaluar(servicio.perfiles["riesgo"])
    html = ficha_html(r, servicio.medianas, estudiante_id="A-001", nombre="Ana <b>",
                      notas="Llamar el lunes", modelo=servicio.nombre_modelo)
    assert "Ana &lt;b&gt;" in html  # el texto del usuario se escapa
    ruta = exportar_pdf(html, tmp_path / "ficha.pdf")
    datos = ruta.read_bytes()
    assert datos.startswith(b"%PDF") and len(datos) > 5_000


def test_ventana_flujo_completo(qapp, servicio, historial, tmp_path):
    from app.ui.ventana import VentanaPrincipal

    qapp.setStyleSheet(rutas.hoja_estilos())
    v = VentanaPrincipal(servicio, historial)
    v.show()

    # Evaluar y guardar
    ev = v.vistas["evaluar"]
    ev.cargar_perfil("riesgo")
    assert ev.resultado.semaforo == "Rojo" and "%" in ev.lbl_prob.text()
    ev.notas.setPlainText("nota de prueba")
    ev.guardar()
    assert historial.contar() == 1 and not ev.btn_guardar.isEnabled()

    # Validación visible
    ev.campos["Curricular units 1st sem (enrolled)"].setValue(2)
    ev.campos["Curricular units 1st sem (approved)"].setValue(5)
    ev.evaluar()
    assert not ev.errores.isHidden()

    # Lote desde CSV y guardar en historial (sin diálogo de confirmación)
    lote = v.vistas["lote"]
    lote.cargar(rutas.PLANTILLA_LOTE)
    assert lote.modelo.rowCount() == 4
    lote.proxy.set_semaforo("Rojo")
    assert lote.proxy.rowCount() >= 1
    lote.proxy.set_semaforo(None)
    assert "sin problemas" in lote.lbl_resumen.text()

    # Archivo con errores: la pestaña «Problemas» los lista y esas filas no se evalúan
    df = pd.read_csv(rutas.PLANTILLA_LOTE).astype(object)
    df.loc[0, "GDP"] = "abc"
    df.loc[1, "Course"] = 1234
    con_errores = tmp_path / "con_errores.csv"
    df.to_csv(con_errores, index=False)
    lote.cargar(con_errores)
    assert lote.modelo.rowCount() == 3 and lote.modelo_problemas.rowCount() == 2
    assert lote.k_error.valor.text() == "1" and lote.pestanas.tabText(1) == "Problemas (2)"
    lote.proxy_problemas.set_semaforo("Error")
    assert lote.proxy_problemas.rowCount() == 1
    lote.cargar(rutas.PLANTILLA_LOTE)

    from PySide6.QtWidgets import QMessageBox
    original = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        lote.guardar_historial()
    finally:
        QMessageBox.question = original
    assert historial.contar() == 5

    # Historial refrescado y filtrable
    hist = v.vistas["historial"]
    v.ir_a("historial")
    assert hist.modelo.rowCount() == 5
    hist.buscar.setText("EJ-RIESGO")
    hist.refrescar()
    assert hist.modelo.rowCount() == 2  # individual + fila del lote

    # Captura para el README
    v.ir_a("evaluar")
    qapp.processEvents()
    v.grab().save(str(tmp_path / "captura.png"))
    v.close()


def test_plantilla_tiene_todas_las_columnas():
    from app.core.variables import ALL_FEATURE_COLS, COL_ID
    df = pd.read_csv(rutas.PLANTILLA_LOTE)
    assert list(df.columns) == [COL_ID, *ALL_FEATURE_COLS]
