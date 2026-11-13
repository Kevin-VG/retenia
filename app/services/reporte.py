"""Ficha del estudiante: HTML (vista previa) y PDF (QTextDocument + QPdfWriter)."""
from datetime import datetime
from html import escape
from pathlib import Path

from app import APP_NAME, __version__
from app.core.scoring import TEXTO_ESTADO, texto_escala
from app.core.variables import ENTRADAS_FORMULARIO, ETIQUETAS, describir_valor

COLOR_ESTADO = {"Rojo": "#c62828", "Amarillo": "#b77900", "Verde": "#0c7a0c"}
FONDO_ESTADO = {"Rojo": "#fdecec", "Amarillo": "#fff6dd", "Verde": "#e8f6e8"}
GRIS = "#52514e"
BORDE = "#cbd5e1"
LINEAS_SEGUIMIENTO = 4


def _h(texto: str) -> str:
    return (f"<p style='font-size:11.5pt; font-weight:bold; margin-top:12px; margin-bottom:4px'>"
            f"{texto}</p>")


def fecha_legible(fecha_iso: str) -> str:
    """2026-11-12T22:24:05 → 12/11/2026 22:24."""
    try:
        return datetime.fromisoformat(fecha_iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(fecha_iso or "")


def _factores_html(titulo, factores, perfil, medianas, color):
    if not factores:
        return ""
    filas = "".join(
        f"<tr><td>{escape(ETIQUETAS[c])}</td>"
        f"<td align='center'>{escape(describir_valor(c, perfil[c]))}</td>"
        f"<td align='center' style='color:{GRIS}'>{escape(describir_valor(c, medianas[c]))}</td>"
        f"<td align='right' style='color:{color}'><b>{v * 100:+.0f} puntos</b></td></tr>"
        for c, v in factores
    )
    return (
        f"<p style='margin-top:6px; margin-bottom:2px'><b>{titulo}</b></p>"
        f"<table width='100%' cellspacing='0' cellpadding='3' border='1' style='border-color:{BORDE}'>"
        "<tr style='background:#f1f5f9'><th align='left'>Dato</th><th>Valor del estudiante</th>"
        "<th>Valor típico</th><th align='right'>Efecto en el riesgo</th></tr>"
        f"{filas}</table>"
    )


def ficha_html(resultado, medianas: dict, *, estudiante_id="", nombre="", fecha=None, notas="",
               institucion="", area="", responsable="") -> str:
    """HTML de la ficha. `resultado` es un ResultadoIndividual."""
    fecha = fecha_legible(fecha or datetime.now().isoformat(timespec="seconds"))
    color = resultado.semaforo
    titulo, detalle = TEXTO_ESTADO[color]
    perfil = resultado.perfil

    # Datos del estudiante en dos columnas (etiqueta | valor | etiqueta | valor)
    pares = [(ETIQUETAS[c], describir_valor(c, perfil[c])) for c in ENTRADAS_FORMULARIO]
    mitad = (len(pares) + 1) // 2
    filas_datos = []
    for izq, der in zip(pares[:mitad], pares[mitad:] + [("", "")]):
        filas_datos.append(
            f"<tr><td style='color:{GRIS}'>{escape(izq[0])}</td><td><b>{escape(izq[1])}</b></td>"
            f"<td style='color:{GRIS}'>{escape(der[0])}</td><td><b>{escape(der[1])}</b></td></tr>"
        )

    factores = (
        _factores_html("Datos que aumentan el riesgo", resultado.suben, perfil, medianas, COLOR_ESTADO["Rojo"])
        + _factores_html("Datos que reducen el riesgo", resultado.bajan, perfil, medianas,
                         COLOR_ESTADO["Verde"])
    )
    if factores:
        factores = f"""{_h('Qué datos influyen más')}{factores}
<p style="color:{GRIS}; font-size:8pt">«Valor típico» es el valor más habitual entre los estudiantes.
El efecto indica cuántos puntos cambiaría el riesgo de un estudiante típico ({resultado.riesgo_mediano * 100:.0f} %)
si solo tuviera ese dato. Es una guía orientativa: no indica una causa y los efectos no se suman.</p>"""
    else:
        factores = (f"{_h('Qué datos influyen más')}<p>Ningún dato se aleja de forma relevante de los "
                    "valores típicos.</p>")

    recs = "".join(f"<li><b>{escape(t)}:</b> {escape(d)}</li>" for t, d in resultado.recomendaciones)
    notas_html = (f"{_h('Notas')}<p>{escape(notas).replace(chr(10), '<br>')}</p>"
                  if notas.strip() else "")
    identidad = escape(estudiante_id.strip()) or "—"
    nombre_html = f"<br>Nombre: <b>{escape(nombre.strip())}</b>" if nombre.strip() else ""
    cabecera = escape(institucion) if institucion.strip() else APP_NAME
    subcabecera = (f"{escape(area)} · " if area.strip() else "") + "Ficha de alerta temprana de deserción"
    seguimiento = "".join(
        "<tr><td height='26'>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>"
        for _ in range(LINEAS_SEGUIMIENTO)
    )
    responsable_html = escape(responsable) if responsable.strip() else "_" * 34

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:#0c1938; font-size:9.5pt">
<table width="100%" cellpadding="0" cellspacing="0"><tr>
  <td><span style="font-size:16pt; font-weight:bold; color:#1d4ed8">{cabecera}</span><br>
      <span style="color:{GRIS}">{subcabecera}</span></td>
  <td align="right" style="color:{GRIS}">Fecha: {escape(fecha)}<br>
      Estudiante: <b>{identidad}</b>{nombre_html}</td>
</tr></table>
<hr>
<table width="100%" cellpadding="8" cellspacing="0" style="background:{FONDO_ESTADO[color]}">
<tr>
  <td width="38%"><span style="color:{GRIS}">Riesgo estimado de deserción</span><br>
      <span style="font-size:24pt; font-weight:bold; color:{COLOR_ESTADO[color]}">{resultado.probabilidad * 100:.1f} %</span></td>
  <td><span style="font-size:14pt; font-weight:bold; color:{COLOR_ESTADO[color]}">{titulo}</span><br>
      {escape(detalle)}<br>
      <span style="color:{GRIS}; font-size:8.5pt">{escape(texto_escala(resultado.umbral))}</span></td>
</tr></table>

{_h('Datos del estudiante')}
<table width="100%" cellspacing="0" cellpadding="3" border="1" style="border-color:{BORDE}">{''.join(filas_datos)}</table>

{factores}

{_h('Plan de acción sugerido')}
<ul style="margin-top:0px">{recs}</ul>
{notas_html}

{_h('Seguimiento')}
<p style="color:{GRIS}; font-size:8pt; margin-top:0px">Registre aquí las acciones realizadas con el estudiante.</p>
<table width="100%" cellspacing="0" cellpadding="4" border="1" style="border-color:{BORDE}">
<tr style="background:#f1f5f9"><th width="16%" align="left">Fecha</th><th width="36%" align="left">Acción realizada</th>
<th width="20%" align="left">Responsable</th><th align="left">Resultado / próximo paso</th></tr>
{seguimiento}
</table>
<table width="100%" cellpadding="4" cellspacing="0" style="margin-top:14px"><tr>
  <td width="50%">Elaborado por: {responsable_html}</td>
  <td>Firma: ______________________________</td>
</tr></table>
<p style="color:{GRIS}; font-size:7.5pt; margin-top:10px">Documento confidencial, de uso exclusivo para el acompañamiento del
estudiante. La estimación es orientativa: no es un diagnóstico ni motivo de sanción, y la decisión final
corresponde al equipo responsable. Generado con {APP_NAME} {__version__}.</p>
</body></html>
"""


def exportar_pdf(html: str, ruta: Path) -> Path:
    """Escribe el HTML como PDF A4. Requiere una QGuiApplication activa.

    Sin tamaño de página fijo, QTextDocument.print_ maqueta el documento con la resolución del
    PDF (las fuentes en pt salen a su tamaño real), añade márgenes de 2 cm y numera las páginas.
    """
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    ruta = Path(ruta)
    writer = QPdfWriter(str(ruta))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setResolution(300)
    writer.setTitle("Ficha de alerta temprana de deserción")
    writer.setCreator(f"{APP_NAME} {__version__}")

    doc = QTextDocument()
    doc.setHtml(html)
    doc.print_(writer)
    return ruta
