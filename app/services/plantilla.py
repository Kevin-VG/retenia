"""Plantilla Excel para la carga por lote: datos de ejemplo, instrucciones, diccionario y listas
desplegables con validación de datos (Excel avisa al escribir un valor no permitido)."""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app import APP_NAME, rutas
from app.core.validacion import LIMITES
from app.core.variables import (
    ALL_FEATURE_COLS, BINARY_COLS, CARRERAS, COL_ID, COLUMNAS_DECIMALES, ETIQUETAS, NOMINAL_COLS,
)

FILAS_CON_VALIDACION = 2000
AZUL = PatternFill("solid", fgColor="1D4ED8")
AMARILLO = PatternFill("solid", fgColor="FFF6DD")
BLANCO_NEGRITA = Font(bold=True, color="FFFFFF")


def _tipo(col: str) -> str:
    if col in NOMINAL_COLS:
        return "Código (categoría)"
    if col in BINARY_COLS:
        return "Sí / No"
    return "Número decimal" if col in COLUMNAS_DECIMALES else "Número entero"


def _valores_permitidos(col: str, categorias: dict) -> str:
    if col in BINARY_COLS:
        return "0 = No · 1 = Sí"
    if col == "Course":
        return " · ".join(f"{c} = {n}" for c, n in sorted(CARRERAS.items()))
    if col in categorias:
        return "Códigos: " + ", ".join(str(int(c)) for c in sorted(categorias[col]))
    if col in LIMITES:
        lo, hi = LIMITES[col]
        return f"Entre {lo} y {hi}"
    return ""


def crear_plantilla_excel(ruta: Path, servicio) -> Path:
    categorias = servicio.categorias_conocidas
    rangos_ent = servicio.rangos_entrenamiento
    columnas = [COL_ID, *ALL_FEATURE_COLS]

    wb = Workbook()

    # ---------------------------------------------------------------- Estudiantes
    ws = wb.active
    ws.title = "Estudiantes"
    ws.append(columnas)
    ejemplos = pd.read_csv(rutas.PLANTILLA_LOTE)[columnas]
    for fila in ejemplos.itertuples(index=False):
        ws.append([v.item() if hasattr(v, "item") else v for v in fila])
    for i, col in enumerate(columnas, start=1):
        celda = ws.cell(row=1, column=i)
        celda.fill = AZUL
        celda.font = BLANCO_NEGRITA
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        if col == COL_ID:
            texto = "ID estudiante (opcional)\nCódigo para identificar al estudiante."
        else:
            texto = f"{ETIQUETAS[col]}\nTipo: {_tipo(col)}\n{_valores_permitidos(col, categorias)}"
        celda.comment = Comment(texto[:900], APP_NAME, width=320, height=160)
        ws.column_dimensions[get_column_letter(i)].width = max(14, min(32, len(col) * 0.9))
    ws.row_dimensions[1].height = 48
    ws.freeze_panes = "B2"
    for fila in ws.iter_rows(min_row=2, max_row=1 + len(ejemplos)):
        for celda in fila:
            celda.fill = AMARILLO

    # ---------------------------------------------------------------- Listas (oculta)
    listas = wb.create_sheet("Listas")
    columnas_lista = {}
    for j, col in enumerate([c for c in NOMINAL_COLS if c in categorias], start=1):
        listas.cell(row=1, column=j, value=col)
        valores = sorted(int(c) for c in categorias[col])
        for k, valor in enumerate(valores, start=2):
            listas.cell(row=k, column=j, value=valor)
        letra = get_column_letter(j)
        columnas_lista[col] = f"Listas!${letra}$2:${letra}${len(valores) + 1}"
    listas.sheet_state = "hidden"

    # ---------------------------------------------------------------- Validación de datos
    ultima = FILAS_CON_VALIDACION + 1
    for i, col in enumerate(columnas, start=1):
        if col == COL_ID:
            continue
        rango = f"{get_column_letter(i)}2:{get_column_letter(i)}{ultima}"
        if col in BINARY_COLS:
            dv = DataValidation(type="list", formula1='"0,1"', allow_blank=False)
            dv.error = "Escribe 0 (No) o 1 (Sí)."
        elif col in columnas_lista:
            dv = DataValidation(type="list", formula1=columnas_lista[col], allow_blank=False)
            dv.error = "Código no reconocido. Revisa la hoja «Diccionario»."
            dv.errorStyle = "warning"  # se permite, pero RetenIA lo marcará como advertencia
        elif col in LIMITES:
            lo, hi = LIMITES[col]
            tipo = "decimal" if col in COLUMNAS_DECIMALES else "whole"
            dv = DataValidation(type=tipo, operator="between", formula1=str(lo), formula2=str(hi))
            dv.error = f"Debe ser un número {'decimal' if tipo == 'decimal' else 'entero'} entre {lo} y {hi}."
        else:
            continue
        dv.errorTitle = ETIQUETAS[col]
        dv.showErrorMessage = True
        ws.add_data_validation(dv)
        dv.add(rango)

    # ---------------------------------------------------------------- Diccionario
    dic = wb.create_sheet("Diccionario")
    dic.append(["Columna (no cambiar el nombre)", "Significado", "Tipo", "Valores permitidos",
                "Rango visto en entrenamiento"])
    dic.append([COL_ID, "Identificador del estudiante (opcional)", "Texto", "Cualquiera", ""])
    for col in ALL_FEATURE_COLS:
        ent = rangos_ent.get(col)
        dic.append([col, ETIQUETAS[col], _tipo(col), _valores_permitidos(col, categorias),
                    f"{ent[0]:g} a {ent[1]:g}" if ent else ""])
    for celda in dic[1]:
        celda.fill = AZUL
        celda.font = BLANCO_NEGRITA
    for letra, ancho in zip("ABCDE", (44, 36, 20, 70, 26)):
        dic.column_dimensions[letra].width = ancho
    for fila in dic.iter_rows(min_row=2):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")
    dic.freeze_panes = "A2"

    # ---------------------------------------------------------------- Instrucciones
    ins = wb.create_sheet("Instrucciones", 0)
    lineas = [
        (f"Plantilla de carga por lote — {APP_NAME}", True),
        ("", False),
        ("1. Completa la hoja «Estudiantes»: una fila por estudiante.", False),
        ("2. Las 4 filas amarillas son ejemplos: bórralas o reemplázalas por tus datos.", False),
        ("3. No cambies los nombres de las columnas (fila 1). Pasa el cursor sobre cada título para ver qué significa.", False),
        ("4. La columna id_estudiante es opcional, pero ayuda a identificar a cada estudiante en resultados y fichas.", False),
        ("5. Sí/No se escribe 1/0. Las categorías (carrera, nacionalidad, ocupación…) se escriben como código: ver «Diccionario».", False),
        ("6. Guarda el archivo como .xlsx y ábrelo en RetenIA → Carga por lote.", False),
        ("", False),
        ("Al cargar el archivo, RetenIA revisa cada fila:", True),
        ("• Error: la fila NO se evalúa (vacío, texto en un campo numérico, valor imposible, aprobadas > matriculadas…).", False),
        ("• Advertencia: la fila se evalúa, pero el resultado es menos fiable (código desconocido, valor poco habitual…).", False),
        ("La pestaña «Problemas» indica la fila del archivo, la columna y qué corregir.", False),
        ("", False),
        ("Opcional: agrega una columna «dropout» (1 = abandonó, 0 = no) para comparar el modelo con el resultado real.", False),
    ]
    for texto, negrita in lineas:
        ins.append([texto])
        ins.cell(row=ins.max_row, column=1).font = Font(bold=negrita, size=14 if ins.max_row == 1 else 11,
                                                         color="0C1938")
    ins.column_dimensions["A"].width = 120
    ins.sheet_view.showGridLines = False
    for hoja in (ins, dic):
        hoja.sheet_properties.tabColor = "1D4ED8"
    wb.active = wb.index(ws)

    ruta = Path(ruta)
    wb.save(ruta)
    return ruta
