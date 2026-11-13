"""Ficha del estudiante: HTML (vista previa) y PDF (QTextDocument + QPdfWriter)."""
from datetime import datetime
from html import escape
from pathlib import Path

from app import APP_NAME, __version__
from app.core.scoring import CORTE_ROJO, TEXTO_ESTADO
from app.core.variables import ENTRADAS_FORMULARIO, ETIQUETAS, describir_valor

COLOR_ESTADO = {"Rojo": "#d03b3b", "Amarillo": "#d99a06", "Verde": "#0c8a0c"}
FONDO_ESTADO = {"Rojo": "#fdecec", "Amarillo": "#fff6dd", "Verde": "#e8f6e8"}


def _factores_html(titulo, factores, perfil, medianas, vacio):
    filas = "".join(
        f"<tr><td>{escape(ETIQUETAS[c])}</td>"
        f"<td align='center'>{escape(describir_valor(c, perfil[c]))}</td>"
        f"<td align='center'>{escape(describir_valor(c, medianas[c]))}</td>"
        f"<td align='right'><b>{v * 100:+.0f} pts</b></td></tr>"
        for c, v in factores
    ) or f"<tr><td colspan='4'><i>{vacio}</i></td></tr>"
    return (
        f"<h3>{titulo}</h3>"
        "<table width='100%' cellspacing='0' cellpadding='5' border='1' style='border-color:#e2e8f0'>"
        "<tr style='background:#f1f5f9'><th align='left'>Dato</th><th>Valor</th>"
        "<th>Perfil mediano</th><th align='right'>Efecto</th></tr>"
        f"{filas}</table>"
    )


def ficha_html(resultado, medianas: dict, *, estudiante_id="", nombre="", fecha=None,
               notas="", modelo="") -> str:
    """HTML de la ficha. `resultado` es un ResultadoIndividual."""
    fecha = fecha or datetime.now().isoformat(timespec="seconds")
    color = resultado.semaforo
    titulo, detalle = TEXTO_ESTADO[color]
    corte = max(CORTE_ROJO, resultado.umbral)
    perfil = resultado.perfil

    datos = "".join(
        f"<tr><td>{escape(ETIQUETAS[c])}</td><td><b>{escape(describir_valor(c, perfil[c]))}</b></td></tr>"
        for c in ENTRADAS_FORMULARIO
    )
    recs = "".join(f"<li><b>{escape(t)}:</b> {escape(d)}</li>" for t, d in resultado.recomendaciones)
    notas_html = f"<h3>Notas</h3><p>{escape(notas)}</p>" if notas.strip() else ""
    identidad = escape(estudiante_id) or "—"
    nombre_html = f" · {escape(nombre)}" if nombre.strip() else ""

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:#0c1938; font-size:10pt">
<table width="100%" cellpadding="0" cellspacing="0"><tr>
  <td><span style="font-size:18pt; font-weight:bold; color:#1d4ed8">{APP_NAME}</span><br>
      <span style="color:#52514e">Ficha de alerta temprana de deserción</span></td>
  <td align="right" style="color:#52514e">Fecha: {escape(fecha.replace('T', ' '))}<br>
      Estudiante: <b>{identidad}</b>{nombre_html}</td>
</tr></table>
<hr>
<table width="100%" cellpadding="10" cellspacing="0" style="background:{FONDO_ESTADO[color]}">
<tr>
  <td width="40%"><span style="color:#52514e">Probabilidad estimada de abandono</span><br>
      <span style="font-size:26pt; font-weight:bold; color:{COLOR_ESTADO[color]}">{resultado.probabilidad * 100:.1f} %</span></td>
  <td><span style="font-size:14pt; font-weight:bold; color:{COLOR_ESTADO[color]}">● {titulo}</span><br>
      {escape(detalle)}<br>
      <span style="color:#52514e; font-size:9pt">Bajo &lt; {resultado.umbral * 100:.0f} % ·
      Moderado {resultado.umbral * 100:.0f}–{corte * 100:.0f} % · Alto ≥ {corte * 100:.0f} %</span></td>
</tr></table>

<h3>Datos del estudiante</h3>
<table width="100%" cellspacing="0" cellpadding="4" border="1" style="border-color:#e2e8f0">{datos}</table>
<p style="color:#52514e; font-size:9pt">Las variables no listadas se completan con el valor mediano
de los estudiantes de entrenamiento.</p>

{_factores_html("Datos que aumentan el riesgo", resultado.suben, perfil, medianas,
                "Ningún dato lo aumenta de forma relevante.")}
{_factores_html("Datos que reducen el riesgo", resultado.bajan, perfil, medianas,
                "Ningún dato lo reduce de forma relevante.")}
<p style="color:#52514e; font-size:9pt">El perfil mediano tiene {resultado.riesgo_mediano * 100:.0f} % de
riesgo. Cada fila indica cuántos puntos cambia la probabilidad si solo ese dato fuera distinto.
Los efectos no se suman y reflejan cómo razona el modelo, no una causa comprobada.</p>

<h3>Plan de acción sugerido</h3>
<ul>{recs}</ul>
{notas_html}
<hr>
<p style="color:#52514e; font-size:8pt">Generado por {APP_NAME} {__version__} · Modelo: {escape(modelo)} ·
Umbral operativo {resultado.umbral:.2f}. Herramienta de apoyo: la alerta nunca sanciona; su único fin
es ofrecer acompañamiento oportuno. La decisión final corresponde a Bienestar Universitario.</p>
</body></html>
"""


def exportar_pdf(html: str, ruta: Path) -> Path:
    """Escribe el HTML como PDF A4. Requiere una QGuiApplication activa."""
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    ruta = Path(ruta)
    writer = QPdfWriter(str(ruta))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    writer.setResolution(300)
    writer.setTitle(f"{APP_NAME} - Ficha del estudiante")
    writer.setCreator(f"{APP_NAME} {__version__}")

    doc = QTextDocument()
    doc.setHtml(html)
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print_(writer)
    return ruta
