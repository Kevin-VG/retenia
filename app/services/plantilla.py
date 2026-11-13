"""Plantilla Excel para evaluar estudiantes desde archivo.

- Hoja «Instrucciones»: pasos, ejemplo de una fila completa y qué pasa al cargar el archivo.
- Hoja «Estudiantes»: títulos en español; obligatorias en azul (con *), opcionales en gris.
  Cada celda muestra qué escribir al seleccionarla y valida el valor (listas desplegables con
  texto: «Sí», «No», nombre de la carrera…).
- Hoja «Valores válidos»: significado, obligatoriedad, valores permitidos y ejemplo de cada columna.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app import APP_NAME
from app.core.validacion import LIMITES
from app.core.variables import (
    COL_CARRERA, COL_ID, COLUMNAS_DECIMALES, COLUMNAS_OBLIGATORIAS, COLUMNAS_PLANTILLA, DESCRIPCIONES,
    ETIQUETAS, OPCIONES, describir_valor,
)

FILAS_CON_VALIDACION = 2000
TITULO_ID = "ID estudiante"
AZUL = PatternFill("solid", fgColor="1D4ED8")
GRIS = PatternFill("solid", fgColor="E2E8F0")
GRIS_CLARO = PatternFill("solid", fgColor="F1F5F9")
BLANCO_NEGRITA = Font(bold=True, color="FFFFFF")
OSCURO_NEGRITA = Font(bold=True, color="0C1938")
TINTA = "0C1938"
BORDE = Border(*(Side(style="thin", color="CBD5E1"),) * 4)

# Valores de muestra (para la hoja de instrucciones y la columna «Ejemplo»)
EJEMPLO = {
    COL_ID: "U2024001",
    COL_CARRERA: 9500, "Age at enrollment": 19,
    "Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 5,
    "Curricular units 2nd sem (enrolled)": 6, "Curricular units 2nd sem (approved)": 4,
    "Curricular units 2nd sem (credited)": 0,
    "Tuition fees up to date": 1, "Debtor": 0, "Scholarship holder": 0,
    "Curricular units 1st sem (grade)": 13.5, "Curricular units 2nd sem (grade)": 12.8,
    "Curricular units 1st sem (credited)": 0,
    "Curricular units 1st sem (evaluations)": 8, "Curricular units 2nd sem (evaluations)": 7,
    "Curricular units 1st sem (without evaluations)": 0, "Curricular units 2nd sem (without evaluations)": 0,
    "Admission grade": 135, "Previous qualification (grade)": 140, "Application order": 1,
    "Daytime/evening attendance": 1, "Gender": 0, "Marital Status": 1, "Displaced": 0,
    "Educational special needs": 0, "International": 0,
}


def encabezado(col: str) -> str:
    """Título de la columna en la plantilla («*» = obligatoria)."""
    if col == COL_ID:
        return TITULO_ID
    return f"{ETIQUETAS[col]} *" if col in COLUMNAS_OBLIGATORIAS else ETIQUETAS[col]


def valor_plantilla(col: str, valor):
    """Valor tal como se escribe en la plantilla: texto para las opciones, número para el resto."""
    if col == COL_ID or valor is None:
        return valor
    if col in OPCIONES:
        return describir_valor(col, valor)
    return float(valor) if col in COLUMNAS_DECIMALES else int(round(float(valor)))


def fila_plantilla(valores: dict, estudiante_id: str = "") -> list:
    """Fila lista para la hoja «Estudiantes» a partir de valores internos (códigos)."""
    return [estudiante_id] + [valor_plantilla(c, valores[c]) if c in valores else None
                              for c in COLUMNAS_PLANTILLA]


def _tipo(col: str) -> str:
    if col in OPCIONES:
        return "Lista"
    return "Número decimal" if col in COLUMNAS_DECIMALES else "Número entero"


def _valores_validos(col: str, separador: str = " · ") -> str:
    if col in OPCIONES:
        nombres = OPCIONES[col].values()
        return separador.join(sorted(nombres) if col == COL_CARRERA else nombres)
    if col in LIMITES:
        lo, hi = LIMITES[col]
        decimal = " (puede tener decimales)" if col in COLUMNAS_DECIMALES else ""
        return f"De {lo} a {hi}{decimal}"
    return ""


def _ayuda_celda(col: str) -> str:
    """Mensaje que Excel muestra al seleccionar una celda (máximo 255 caracteres)."""
    obligatoria = "Obligatorio." if col in COLUMNAS_OBLIGATORIAS else "Opcional: si lo dejas vacío se usa un valor típico."
    if col == COL_CARRERA:
        valores = "Elige la carrera en la lista desplegable."
    elif col in OPCIONES:
        valores = "Elige: " + " / ".join(OPCIONES[col].values()) + "."
    else:
        valores = _valores_validos(col) + "."
    return f"{DESCRIPCIONES[col]} {valores} {obligatoria}"[:255]


def crear_plantilla_excel(ruta: Path, servicio=None) -> Path:
    columnas = [COL_ID, *COLUMNAS_PLANTILLA]
    wb = Workbook()

    # ---------------------------------------------------------------- Estudiantes
    ws = wb.active
    ws.title = "Estudiantes"
    ws.append([encabezado(c) for c in columnas])
    for i, col in enumerate(columnas, start=1):
        celda = ws.cell(row=1, column=i)
        obligatoria = col in COLUMNAS_OBLIGATORIAS
        celda.fill = AZUL if obligatoria else (GRIS_CLARO if col == COL_ID else GRIS)
        celda.font = BLANCO_NEGRITA if obligatoria else OSCURO_NEGRITA
        celda.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        celda.border = BORDE
        if col == COL_ID:
            texto = "ID estudiante (opcional)\nCódigo para reconocer al estudiante en los resultados."
        else:
            texto = (f"{ETIQUETAS[col]} ({'obligatorio' if obligatoria else 'opcional'})\n"
                     f"{DESCRIPCIONES[col]}\nValores válidos: {_valores_validos(col, ', ')}")
        celda.comment = Comment(texto[:900], APP_NAME, width=340, height=170)
        ws.column_dimensions[get_column_letter(i)].width = 30 if col == COL_CARRERA else 17
    ws.row_dimensions[1].height = 62
    ws.freeze_panes = "B2"

    # ---------------------------------------------------------------- Listas (oculta)
    listas = wb.create_sheet("Listas")
    rango_lista = {}
    for j, col in enumerate([c for c in COLUMNAS_PLANTILLA if c in OPCIONES], start=1):
        listas.cell(row=1, column=j, value=ETIQUETAS[col])
        valores = sorted(OPCIONES[col].values()) if col == COL_CARRERA else list(OPCIONES[col].values())
        for k, valor in enumerate(valores, start=2):
            listas.cell(row=k, column=j, value=valor)
        letra = get_column_letter(j)
        rango_lista[col] = f"Listas!${letra}$2:${letra}${len(valores) + 1}"
    listas.sheet_state = "hidden"

    # ---------------------------------------------------------------- Validación y ayuda por celda
    ultima = FILAS_CON_VALIDACION + 1
    for i, col in enumerate(columnas, start=1):
        rango = f"{get_column_letter(i)}2:{get_column_letter(i)}{ultima}"
        if col == COL_ID:
            dv = DataValidation(type="textLength", operator="lessThanOrEqual", formula1="60", allow_blank=True)
            dv.error = "El ID puede tener como máximo 60 caracteres."
            dv.prompt = "Código del estudiante (opcional). Ayuda a reconocerlo en los resultados."
        elif col in rango_lista:
            dv = DataValidation(type="list", formula1=rango_lista[col], allow_blank=True)
            dv.error = "Elige un valor de la lista desplegable."
        elif col in LIMITES:
            lo, hi = LIMITES[col]
            tipo = "decimal" if col in COLUMNAS_DECIMALES else "whole"
            dv = DataValidation(type=tipo, operator="between", formula1=str(lo), formula2=str(hi),
                                allow_blank=True)
            dv.error = f"Escribe un número {'' if tipo == 'decimal' else 'entero '}de {lo} a {hi}."
        else:
            continue
        titulo = TITULO_ID if col == COL_ID else ETIQUETAS[col]
        dv.errorTitle = titulo[:32]
        dv.promptTitle = titulo[:32]
        if col != COL_ID:
            dv.prompt = _ayuda_celda(col)
        dv.showErrorMessage = True
        dv.showInputMessage = True
        ws.add_data_validation(dv)
        dv.add(rango)

    # ---------------------------------------------------------------- Valores válidos
    guia = wb.create_sheet("Valores válidos")
    guia.append(["Columna", "¿Obligatoria?", "Qué significa", "Valores válidos", "Ejemplo"])
    guia.append([TITULO_ID, "No", "Código para reconocer al estudiante en los resultados y en las fichas.",
                 "Texto libre (máximo 60 caracteres)", EJEMPLO[COL_ID]])
    habituales = servicio.rangos_entrenamiento if servicio is not None else {}
    for col in COLUMNAS_PLANTILLA:
        validos = _valores_validos(col, "\n")
        if col in habituales and col not in OPCIONES:
            lo, hi = habituales[col]
            validos += f"\nLo habitual: de {lo:g} a {hi:g}"
        guia.append([ETIQUETAS[col], "Sí" if col in COLUMNAS_OBLIGATORIAS else "No", DESCRIPCIONES[col],
                     validos, valor_plantilla(col, EJEMPLO[col])])
    for celda in guia[1]:
        celda.fill = AZUL
        celda.font = BLANCO_NEGRITA
        celda.alignment = Alignment(vertical="center")
    for fila in guia.iter_rows(min_row=2):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")
            celda.border = BORDE
        if fila[1].value == "Sí":
            fila[0].font = Font(bold=True, color=TINTA)
            fila[1].font = Font(bold=True, color="1D4ED8")
    for letra, ancho in zip("ABCDE", (36, 14, 60, 46, 22)):
        guia.column_dimensions[letra].width = ancho
    guia.freeze_panes = "A2"

    # ---------------------------------------------------------------- Instrucciones
    ins = wb.create_sheet("Instrucciones", 0)
    ins.sheet_view.showGridLines = False
    ins.column_dimensions["A"].width = 3
    fila = 1

    def linea(texto, *, negrita=False, tamano=11, color=TINTA):
        nonlocal fila
        celda = ins.cell(row=fila, column=2, value=texto)
        celda.font = Font(bold=negrita, size=tamano, color=color)
        fila += 1

    linea(f"{APP_NAME} · Plantilla para evaluar estudiantes", negrita=True, tamano=16)
    linea("Completa una fila por estudiante y abre el archivo en RetenIA → «Evaluar desde archivo».",
          color="52514E")
    fila += 1
    linea("Cómo completarla", negrita=True, tamano=12)
    for paso in (
        "1. Ve a la hoja «Estudiantes» y escribe un estudiante por fila, empezando en la fila 2.",
        "2. Las columnas azules (con *) son obligatorias. Las grises son opcionales: si las dejas vacías, "
        "RetenIA usa un valor típico.",
        "3. Al seleccionar una celda, Excel muestra qué escribir. Las columnas de lista (Carrera, Sí/No, "
        "Turno…) tienen un desplegable.",
        "4. No cambies los títulos de la fila 1 ni el nombre de la hoja «Estudiantes».",
        "5. Guarda el archivo (.xlsx) y ábrelo en RetenIA. Si tienes dudas sobre una columna, revisa la "
        "hoja «Valores válidos».",
    ):
        linea(paso)
    fila += 1
    linea("Ejemplo de una fila completa (solo columnas obligatorias)", negrita=True, tamano=12)
    ejemplo_cols = [COL_ID, *COLUMNAS_OBLIGATORIAS]
    for j, col in enumerate(ejemplo_cols, start=2):
        cab = ins.cell(row=fila, column=j, value=encabezado(col))
        cab.fill = AZUL if col in COLUMNAS_OBLIGATORIAS else GRIS_CLARO
        cab.font = BLANCO_NEGRITA if col in COLUMNAS_OBLIGATORIAS else OSCURO_NEGRITA
        cab.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cab.border = BORDE
        val = ins.cell(row=fila + 1, column=j, value=valor_plantilla(col, EJEMPLO[col]))
        val.alignment = Alignment(horizontal="center")
        val.border = BORDE
        if j > 2:
            ins.column_dimensions[get_column_letter(j)].width = 16
    ins.column_dimensions["B"].width = 16
    ins.column_dimensions["C"].width = 18
    ins.row_dimensions[fila].height = 48
    fila += 3
    linea("Qué pasa al abrir el archivo en RetenIA", negrita=True, tamano=12)
    for texto in (
        "• Cada fila se revisa antes de evaluarla.",
        "• Error: la fila NO se evalúa (dato obligatorio vacío, valor no válido, aprobadas mayor que "
        "matriculadas…). Corrígela y vuelve a abrir el archivo.",
        "• Advertencia: la fila se evalúa, pero conviene revisarla (valor poco habitual, ID repetido…).",
        "• La pestaña «Problemas» indica la fila del archivo, la columna y qué corregir.",
    ):
        linea(texto)
    fila += 1
    linea("Opcional: comparar con el resultado real", negrita=True, tamano=12)
    linea("Si ya sabes qué estudiantes abandonaron (por ejemplo, de un ciclo anterior), agrega una columna "
          "con el título «Abandonó» y escribe Sí o No.")
    linea("RetenIA mostrará cuántos de esos casos habría detectado y qué tan acertadas fueron sus alertas.")
    ins.column_dimensions["B"].width = 16

    for hoja in (ins, guia):
        hoja.sheet_properties.tabColor = "1D4ED8"
    ws.sheet_properties.tabColor = "0C8A0C"
    wb.active = wb.index(ws)

    ruta = Path(ruta)
    wb.save(ruta)
    return ruta
