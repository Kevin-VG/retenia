"""Validación fila por fila de un archivo de carga por lote.

Acepta la plantilla en español (títulos legibles, opciones escritas como texto: «Sí», «Enfermería»…)
y también el formato anterior de 36 columnas con los nombres originales y códigos numéricos.

Dos niveles:
- Error: la fila no se puede evaluar (dato obligatorio vacío, valor no reconocido, imposible…).
- Advertencia: la fila se evalúa, pero el resultado puede ser menos preciso (código desconocido,
  valor poco habitual, pequeñas incoherencias).

Las columnas opcionales que faltan o están vacías toman el valor típico (mediana), igual que en la
evaluación individual.
"""
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.variables import (
    ALL_FEATURE_COLS, BINARY_COLS, COL_CARRERA, COL_ID, COLUMNAS_DECIMALES, COLUMNAS_OBLIGATORIAS,
    ETIQUETAS, NUMERIC_COLS, OPCIONES, normalizar_texto,
)

ERROR = "Error"
ADVERTENCIA = "Advertencia"
COL_REAL = "dropout"           # resultado real (opcional): 1/Sí = abandonó, 0/No = continúa
TARGET_COL = "Target"          # formato original: «Dropout», «Graduate», «Enrolled»
PREFIJO_SIN_ID = "Fila "

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
COLUMNAS_OPCIONALES = {COL_ID, COL_REAL, TARGET_COL}
COLUMNAS_PROBLEMAS = ["Fila", COL_ID, "Columna", "Valor", "Nivel", "Problema"]


def _alias_columnas() -> dict:
    """Título normalizado → nombre interno. Acepta el nombre interno, el título en español y variantes."""
    alias = {}
    for col in ALL_FEATURE_COLS:
        alias[normalizar_texto(col)] = col
        alias[normalizar_texto(ETIQUETAS[col])] = col
    for texto in ("id_estudiante", "id estudiante", "id del estudiante", "codigo", "codigo estudiante",
                  "codigo del estudiante", "id"):
        alias[texto] = COL_ID
    for texto in ("dropout", "abandono", "abandono real", "resultado real"):
        alias[texto] = COL_REAL
    alias["target"] = TARGET_COL
    return alias


ALIAS_COLUMNAS = _alias_columnas()

# Opción escrita a mano → código, por columna (sin tildes ni mayúsculas: «si», «SÍ», «Sí» valen igual)
_OPCIONES_NORMALIZADAS = {
    col: {normalizar_texto(texto): codigo for codigo, texto in opciones.items()}
    for col, opciones in OPCIONES.items()
}
_OPCIONES_NORMALIZADAS.update({c: {**_OPCIONES_NORMALIZADAS[c], "si": 1, "no": 0} for c in BINARY_COLS})
_DECIMAL_CON_COMA = re.compile(r"^-?\d+,\d+$")


class ErrorArchivo(ValueError):
    """El archivo completo no se puede usar (faltan columnas, sin filas…)."""


@dataclass
class Validacion:
    datos: pd.DataFrame             # archivo con columnas normalizadas (nombres internos)
    X: pd.DataFrame                 # 36 columnas numéricas (NaN donde hay error)
    filas: pd.Series                # número de fila en el archivo (encabezado = fila 1)
    ids: pd.Series                  # ID del estudiante o «Fila n»
    con_error: pd.Series            # bool por fila: no se evalúa
    problemas: pd.DataFrame         # una fila por problema detectado
    columnas_extra: list = field(default_factory=list)

    @property
    def n_errores(self) -> int:
        return int(self.con_error.sum())

    def avisos_por_fila(self) -> pd.Series:
        adv = self.problemas[self.problemas["Nivel"] == ADVERTENCIA]
        return adv.groupby("Fila")["Problema"].apply(lambda s: " · ".join(dict.fromkeys(s)))


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra los títulos reconocidos a los nombres internos (ignora mayúsculas, tildes y «*»)."""
    nuevos = {}
    for col in df.columns:
        clave = normalizar_texto(str(col).replace("*", ""))
        nuevos[col] = ALIAS_COLUMNAS.get(clave, str(col).strip())
    return df.rename(columns=nuevos)


def _texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "(vacío)"
    if isinstance(valor, (float, np.floating)) and float(valor).is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    return texto if texto else "(vacío)"


def _a_codigo(col: str, valor):
    """Convierte «Sí», «Enfermería», «12,5»… a número; deja igual lo que no reconoce."""
    if not isinstance(valor, str):
        return valor
    texto = valor.strip()
    if col in _OPCIONES_NORMALIZADAS:
        codigo = _OPCIONES_NORMALIZADAS[col].get(normalizar_texto(texto))
        if codigo is not None:
            return codigo
    if _DECIMAL_CON_COMA.match(texto):
        return texto.replace(",", ".")
    return texto


def _opciones_validas(col: str) -> str:
    if col == COL_CARRERA:
        return "elige una carrera de la lista (hoja «Valores válidos»)"
    return "usa " + " o ".join(f"«{t}»" for t in OPCIONES[col].values())


def validar_lote(df: pd.DataFrame, categorias_conocidas: dict, rangos_entrenamiento: dict,
                 medianas: dict) -> Validacion:
    """Valida un DataFrame leído de CSV/Excel. Lanza ErrorArchivo si no se puede usar en absoluto."""
    if df.empty:
        raise ErrorArchivo("El archivo no tiene filas con estudiantes.")
    filas = pd.Series(np.asarray(df.index) + 2, name="Fila")
    df = normalizar_columnas(df.copy()).reset_index(drop=True)
    df = df.loc[:, ~df.columns.duplicated()]

    faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in df.columns]
    if faltan:
        raise ErrorArchivo(
            f"Faltan {len(faltan)} columna(s) obligatoria(s):\n• "
            + "\n• ".join(ETIQUETAS[c] for c in faltan)
            + "\n\nDescarga la plantilla Excel para ver el formato correcto."
        )
    provistas = {c for c in ALL_FEATURE_COLS if c in df.columns}
    for col in ALL_FEATURE_COLS:
        if col not in provistas:
            df[col] = np.nan

    if COL_ID in df.columns:
        ids = df[COL_ID].map(lambda v: "" if _texto(v) == "(vacío)" else _texto(v))
        ids = ids.where(ids != "", PREFIJO_SIN_ID + filas.astype(str))
    else:
        ids = PREFIJO_SIN_ID + filas.astype(str)

    crudo = df[ALL_FEATURE_COLS].astype(object)
    convertido = crudo.apply(lambda s: s.map(lambda v: _a_codigo(s.name, v)))
    X = convertido.apply(pd.to_numeric, errors="coerce")
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

    # Columnas opcionales vacías → valor típico (sin aviso: es lo esperado)
    for col in ALL_FEATURE_COLS:
        if col not in COLUMNAS_OBLIGATORIAS:
            X.loc[vacio[col], col] = medianas[col]
    for sem in ("1st", "2nd"):  # sin materias aprobadas el promedio es 0, como en el formulario
        nota = f"Curricular units {sem} sem (grade)"
        sin_aprobadas = X[f"Curricular units {sem} sem (approved)"] == 0
        X.loc[vacio[nota] & sin_aprobadas, nota] = 0.0

    for col in ALL_FEATURE_COLS:
        x = X[col]
        escrito = ~vacio[col]
        if col in COLUMNAS_OBLIGATORIAS:
            registrar(vacio[col], col, ERROR, "Falta este dato (es obligatorio)")
        if col in OPCIONES:
            registrar(no_numerico[col], col, ERROR, f"Valor no reconocido: {_opciones_validas(col)}")
        else:
            registrar(no_numerico[col], col, ERROR, "Debe ser un número")
        if col in COLUMNAS_ENTERAS:
            registrar(escrito & x.notna() & (x % 1 != 0), col, ERROR, "Debe ser un número entero")
        if col in BINARY_COLS:
            registrar(escrito & x.notna() & ~x.isin([0, 1]), col, ERROR,
                      f"Valor no reconocido: {_opciones_validas(col)}")
        if col in LIMITES:
            lo, hi = LIMITES[col]
            registrar(escrito & x.notna() & ((x < lo) | (x > hi)), col, ERROR,
                      f"Fuera del rango permitido ({lo} a {hi})")
        if col in categorias_conocidas and col not in BINARY_COLS:
            registrar(escrito & x.notna() & (x % 1 == 0) & ~x.isin(categorias_conocidas[col]), col,
                      ADVERTENCIA, "Código no reconocido; el resultado puede ser menos preciso")
        if col in rangos_entrenamiento:
            lo, hi = rangos_entrenamiento[col]
            dentro_limites = True
            if col in LIMITES:
                dentro_limites = (x >= LIMITES[col][0]) & (x <= LIMITES[col][1])
            registrar(escrito & x.notna() & dentro_limites & ((x < lo) | (x > hi)), col, ADVERTENCIA,
                      f"Valor poco habitual (lo usual es de {lo:g} a {hi:g}); "
                      "el resultado puede ser menos preciso")

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
        duplicado = ids.duplicated(keep=False) & ~ids.str.startswith(PREFIJO_SIN_ID)
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
    return Validacion(datos=df, X=X, filas=filas, ids=ids, con_error=con_error, problemas=problemas,
                      columnas_extra=extra)
