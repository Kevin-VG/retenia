"""Validación fila por fila de un archivo de carga por lote.

Dos niveles:
- Error: la fila no se puede evaluar (vacío, no numérico, valor imposible, incoherencia grave).
- Advertencia: la fila se evalúa, pero el resultado es menos fiable (código desconocido,
  valor fuera de lo visto en entrenamiento, pequeñas incoherencias).
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.variables import (
    ALL_FEATURE_COLS, BINARY_COLS, COL_ID, COLUMNAS_DECIMALES, ETIQUETAS, NUMERIC_COLS,
)

ERROR = "Error"
ADVERTENCIA = "Advertencia"

# Límites de valores posibles (fuera de ellos el dato es imposible, no solo inusual)
LIMITES = {
    "Application order": (0, 9),
    "Age at enrollment": (15, 100),
    "Previous qualification (grade)": (0, 200),
    "Admission grade": (0, 200),
    "Curricular units 1st sem (grade)": (0, 20),
    "Curricular units 2nd sem (grade)": (0, 20),
    "Unemployment rate": (0, 100),
    "Inflation rate": (-50, 100),
    "GDP": (-50, 50),
}
for _c in NUMERIC_COLS:
    if _c.startswith("Curricular units") and "(grade)" not in _c:
        LIMITES[_c] = (0, 60)

COLUMNAS_ENTERAS = [c for c in ALL_FEATURE_COLS if c not in COLUMNAS_DECIMALES]
COLUMNAS_OPCIONALES = {COL_ID, "dropout", "Target"}
COLUMNAS_PROBLEMAS = ["Fila", COL_ID, "Columna", "Valor", "Nivel", "Problema"]


class ErrorArchivo(ValueError):
    """El archivo completo no se puede usar (faltan columnas, sin filas…)."""


@dataclass
class Validacion:
    X: pd.DataFrame                 # 36 columnas numéricas (NaN donde no se pudo convertir)
    filas: pd.Series                # número de fila en el archivo (encabezado = fila 1)
    ids: pd.Series                  # id_estudiante o «FILA-n»
    con_error: pd.Series            # bool por fila: no se evalúa
    problemas: pd.DataFrame         # una fila por problema detectado
    columnas_extra: list = field(default_factory=list)

    @property
    def n_errores(self) -> int:
        return int(self.con_error.sum())

    def avisos_por_fila(self) -> pd.Series:
        adv = self.problemas[self.problemas["Nivel"] == ADVERTENCIA]
        return adv.groupby("Fila")["Problema"].apply(lambda s: " · ".join(dict.fromkeys(s)))


def _texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "(vacío)"
    if isinstance(valor, (float, np.floating)) and float(valor).is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    return texto if texto else "(vacío)"


def validar_lote(df: pd.DataFrame, categorias_conocidas: dict, rangos_entrenamiento: dict) -> Validacion:
    """Valida un DataFrame leído de CSV/Excel. Lanza ErrorArchivo si no se puede usar en absoluto."""
    if df.empty:
        raise ErrorArchivo("El archivo no tiene filas de datos.")
    faltan = [c for c in ALL_FEATURE_COLS if c not in df.columns]
    if faltan:
        raise ErrorArchivo(
            f"Faltan {len(faltan)} de {len(ALL_FEATURE_COLS)} columnas obligatorias:\n• "
            + "\n• ".join(faltan)
            + "\n\nDescarga la plantilla para ver el formato correcto."
        )

    df = df.reset_index(drop=True)
    filas = pd.Series(df.index + 2, name="Fila")
    if COL_ID in df.columns:
        ids = df[COL_ID].map(lambda v: "" if _texto(v) == "(vacío)" else _texto(v))
        ids = ids.where(ids != "", "FILA-" + filas.astype(str))
    else:
        ids = "FILA-" + filas.astype(str)

    crudo = df[ALL_FEATURE_COLS]
    X = crudo.apply(pd.to_numeric, errors="coerce")
    vacio = crudo.isna() | crudo.astype(str).apply(lambda s: s.str.strip() == "")
    no_numerico = X.isna() & ~vacio

    partes = []

    def registrar(mascara, col, nivel, problema, valores=None):
        mascara = pd.Series(mascara, index=df.index).fillna(False).astype(bool)
        if not mascara.any():
            return
        vals = (valores if valores is not None else crudo[col])[mascara]
        partes.append(pd.DataFrame({
            "Fila": filas[mascara], COL_ID: ids[mascara],
            "Columna": "ID estudiante" if col == COL_ID else ETIQUETAS.get(col, col),
            "Valor": vals.map(_texto),
            "Nivel": nivel, "Problema": problema,
        }))

    for col in ALL_FEATURE_COLS:
        x = X[col]
        registrar(vacio[col], col, ERROR, "Valor vacío")
        registrar(no_numerico[col], col, ERROR, "No es un número")
        if col in COLUMNAS_ENTERAS:
            registrar(x.notna() & (x % 1 != 0), col, ERROR, "Debe ser un número entero")
        if col in BINARY_COLS:
            registrar(x.notna() & ~x.isin([0, 1]), col, ERROR, "Debe ser 0 (No) o 1 (Sí)")
        if col in LIMITES:
            lo, hi = LIMITES[col]
            registrar(x.notna() & ((x < lo) | (x > hi)), col, ERROR,
                      f"Valor imposible: debe estar entre {lo} y {hi}")
        if col in categorias_conocidas:  # vacío si el modelo no expone sus categorías
            registrar(x.notna() & (x % 1 == 0) & ~x.isin(categorias_conocidas[col]), col, ADVERTENCIA,
                      "Código que el modelo no conoce (resultado menos fiable)")
        if col in rangos_entrenamiento:
            lo, hi = rangos_entrenamiento[col]
            dentro_limites = True
            if col in LIMITES:
                dentro_limites = (x >= LIMITES[col][0]) & (x <= LIMITES[col][1])
            registrar(x.notna() & dentro_limites & ((x < lo) | (x > hi)), col, ADVERTENCIA,
                      f"Fuera de lo visto en entrenamiento ({lo:g} a {hi:g}); el modelo extrapola")

    for sem, nombre in (("1st", "1er"), ("2nd", "2do")):
        c = lambda medida: f"Curricular units {sem} sem ({medida})"  # noqa: E731
        matric = X[c("enrolled")]
        registrar(X[c("approved")] > matric, c("approved"), ERROR,
                  f"Aprobadas mayor que matriculadas ({nombre} semestre)")
        registrar(X[c("credited")] > matric, c("credited"), ERROR,
                  f"Convalidadas mayor que matriculadas ({nombre} semestre)")
        registrar(X[c("without evaluations")] > matric, c("without evaluations"), ADVERTENCIA,
                  f"Sin evaluar mayor que matriculadas ({nombre} semestre)")
        registrar((X[c("approved")] == 0) & (X[c("grade")] > 0), c("grade"), ADVERTENCIA,
                  f"Promedio mayor que 0 sin materias aprobadas ({nombre} semestre)")

    if COL_ID in df.columns:
        duplicado = ids.duplicated(keep=False) & ~ids.str.startswith("FILA-")
        registrar(duplicado, COL_ID, ADVERTENCIA, "ID repetido en el archivo", valores=ids)

    def _orden(col):  # errores antes que advertencias dentro de cada fila
        return col.map({ERROR: 0, ADVERTENCIA: 1}) if col.name == "Nivel" else col

    problemas = (
        pd.concat(partes, ignore_index=True).sort_values(["Fila", "Nivel"], key=_orden, kind="stable")
        if partes else pd.DataFrame(columns=COLUMNAS_PROBLEMAS)
    ).reset_index(drop=True)

    filas_error = set(problemas.loc[problemas["Nivel"] == ERROR, "Fila"])
    con_error = filas.isin(filas_error)
    extra = [c for c in df.columns if c not in ALL_FEATURE_COLS and c not in COLUMNAS_OPCIONALES]
    return Validacion(X=X, filas=filas, ids=ids, con_error=con_error, problemas=problemas,
                      columnas_extra=extra)
