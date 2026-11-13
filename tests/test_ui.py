"""Pruebas de humo de la interfaz (plataforma Qt 'offscreen', sin pantalla)."""
import pandas as pd
import pytest

from app import rutas
from app.services import preferencias
from app.services.reporte import exportar_pdf, ficha_html
from tests.conftest import LOTE_COMPLETO


@pytest.fixture
def ventana(qapp, servicio, historial):
    from app.ui.ventana import VentanaPrincipal

    qapp.setStyleSheet(rutas.hoja_estilos())
    v = VentanaPrincipal(servicio, historial)
    v.show()
    yield v
    v.close()


@pytest.fixture
def responder_si(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))


def test_pdf_de_la_ficha(qapp, servicio, tmp_path):
    r = servicio.evaluar(servicio.perfiles["riesgo"])
    html = ficha_html(r, servicio.medianas, estudiante_id="A-001", nombre="Ana <b>",
                      notas="Llamar el lunes", institucion="Universidad Demo", responsable="Equipo de tutoría")
    assert "Ana &lt;b&gt;" in html  # el texto del usuario se escapa
    assert "Universidad Demo" in html and "Seguimiento" in html and "Equipo de tutoría" in html
    for termino in ("mediano", "entrenamiento", "Gradient", "umbral"):
        assert termino not in html
    ruta = exportar_pdf(html, tmp_path / "ficha.pdf")
    datos = ruta.read_bytes()
    assert datos.startswith(b"%PDF") and len(datos) > 5_000


def test_evaluar_formulario(ventana, servicio, historial):
    ev = ventana.vistas["evaluar"]

    # El formulario empieza vacío y no deja evaluar sin datos
    ev.evaluar()
    assert ev.resultado is None and not ev.errores.isHidden() and "Faltan 10 datos" in ev.errores.text()
    assert ev.campos["Course"].property("invalido")

    ev._aplicar(servicio.perfiles["riesgo"])
    ev.id_estudiante.setText("A-001")
    ev.evaluar()
    assert ev.resultado.semaforo == "Rojo" and "%" in ev.lbl_prob.text()
    assert "Riesgo alto" in ev.lbl_estado.text()
    ev.notas.setPlainText("nota de prueba")
    ev.guardar()
    assert historial.contar() == 1 and not ev.btn_guardar.isEnabled()

    # Cambiar un dato marca el resultado como desactualizado
    ev.campos["Debtor"].setCurrentIndex(ev.campos["Debtor"].findData(0))
    assert not ev.aviso_cambios.isHidden() and not ev.btn_pdf.isEnabled()

    # Validación cruzada visible
    ev.campos["Curricular units 1st sem (enrolled)"].setValue(2)
    ev.campos["Curricular units 1st sem (approved)"].setValue(5)
    ev.evaluar()
    assert not ev.errores.isHidden() and "aprobadas" in ev.errores.text()

    ev.limpiar()
    assert ev.resultado is None and ev.panel.isHidden() and ev.campos["Course"].currentIndex() == -1


def test_evaluar_desde_archivo(ventana, historial, tmp_path, responder_si):
    lote = ventana.vistas["lote"]
    lote.cargar(LOTE_COMPLETO)
    assert lote.modelo.rowCount() == 4
    assert "sin problemas" in lote.lbl_resumen.text()

    # Las tarjetas de resumen filtran la tabla
    lote.k_rojo.pulsada.emit()
    assert lote.filtro_semaforo.currentData() == "Rojo" and lote.k_rojo.property("activa")
    assert 1 <= lote.proxy.rowCount() < 4
    lote.k_total.pulsada.emit()
    assert lote.proxy.rowCount() == 4

    exportable = lote.tabla_exportable()
    assert {"Riesgo (%)", "Nivel de riesgo", "Carrera", "Tiene beca"} <= set(exportable.columns)
    assert set(exportable["Nivel de riesgo"]) <= {"Riesgo alto", "Riesgo moderado", "Riesgo bajo"}

    # Archivo con errores: la pestaña «Problemas» los lista y esas filas no se evalúan
    df = pd.read_csv(LOTE_COMPLETO).astype(object)
    df.loc[0, "GDP"] = "abc"
    df.loc[1, "Course"] = 1234
    con_errores = tmp_path / "con_errores.csv"
    df.to_csv(con_errores, index=False)
    lote.cargar(con_errores)
    assert lote.modelo.rowCount() == 3 and lote.modelo_problemas.rowCount() == 2
    assert lote.k_error.valor.text() == "1" and lote.pestanas.tabText(1) == "Problemas (2)"
    lote.k_error.pulsada.emit()
    assert lote.pestanas.currentIndex() == 1 and lote.proxy_problemas.rowCount() == 1

    # Guardar en historial; un segundo guardado del mismo archivo avisa antes
    lote.cargar(LOTE_COMPLETO)
    lote.guardar_historial()
    assert historial.contar() == 4
    assert historial.fecha_archivo_guardado(LOTE_COMPLETO.name)

    hist = ventana.vistas["historial"]
    ventana.ir_a("historial")
    assert hist.modelo.rowCount() == 4
    hist.buscar.setText("EJ-RIESGO")
    hist.refrescar()
    assert hist.modelo.rowCount() == 1
    assert hist.tabla_exportable()["Tipo"].tolist() == ["Archivo"]
    hist.f_periodo.setCurrentIndex(1)  # hoy
    assert hist.modelo.rowCount() == 1


def test_acerca_y_preferencias(ventana, qapp):
    ventana.ir_a("acerca")
    assert ventana.pila.currentWidget() is ventana.vistas["acerca"] and ventana.btn_acerca.isChecked()
    acerca = ventana.vistas["acerca"]
    acerca.campos["institucion"].setText("Universidad Demo")
    acerca.guardar_preferencias()
    assert preferencias.cargar()["institucion"] == "Universidad Demo"

    from PySide6.QtWidgets import QLabel
    textos = " ".join(lbl.text() for lbl in acerca.findChildren(QLabel))
    for termino in ("UPN", "Proyecto", "Python 3", "Gradient", "F1"):
        assert termino not in textos

    ventana.ir_a("evaluar")
    assert not ventana.btn_acerca.isChecked() and ventana.menu.currentRow() == 0
    qapp.processEvents()
