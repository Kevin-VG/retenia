"""Puntuación: semáforo, validación, perfil, factores de riesgo, lotes y métricas.

Sin dependencias de Qt, para poder probarse por separado.
"""
import io

import numpy as np
import pandas as pd

from app.core.validacion import COL_REAL, TARGET_COL
from app.core.variables import (
    ALL_FEATURE_COLS, COL_APROB_1, COL_APROB_2, COL_BECA, COL_DEUDA, COL_EDAD,
    COL_MATRIC_1, COL_MATRIC_2, COL_PAGOS, normalizar_texto,
)

CORTE_ROJO = 0.60  # desde aquí la alerta pasa de amarilla a roja

SEMESTRES = ("1st", "2nd")

TEXTO_ESTADO = {
    "Rojo": ("Riesgo alto", "Priorizar contacto e intervención."),
    "Amarillo": ("Riesgo moderado", "Activar alerta y seguimiento cercano."),
    "Verde": ("Riesgo bajo", "Mantener seguimiento regular."),
}


def texto_escala(umbral: float) -> str:
    """Escala de niveles en palabras, p. ej. «Bajo: menos de 40 % · Moderado: 40 % a 60 % · Alto: 60 % o más»."""
    u, corte = umbral * 100, max(CORTE_ROJO, umbral) * 100
    if corte <= u:
        return f"Bajo: menos de {u:.0f} % · Alto: {u:.0f} % o más"
    return f"Bajo: menos de {u:.0f} % · Moderado: {u:.0f} % a {corte:.0f} % · Alto: {corte:.0f} % o más"


def semaforo(probabilidades, umbral: float) -> np.ndarray:
    """Verde bajo el umbral del modelo; sobre él, Amarillo y luego Rojo."""
    prob = np.asarray(probabilidades)
    return np.select(
        [prob >= max(CORTE_ROJO, umbral), prob >= umbral],
        ["Rojo", "Amarillo"],
        default="Verde",
    )


def validar_perfil(entradas: dict, rangos: dict, etiquetas: dict) -> list:
    """Devuelve los errores de un perfil del formulario (vacío si es válido)."""
    errores = [
        f"{etiquetas[col]}: debe estar entre {minimo} y {maximo}."
        for col, (minimo, maximo) in rangos.items()
        if col in entradas and not minimo <= entradas[col] <= maximo
    ]
    for sem, nombre in zip(SEMESTRES, ("1er", "2do")):
        matriculadas = entradas[f"Curricular units {sem} sem (enrolled)"]
        if entradas[f"Curricular units {sem} sem (approved)"] > matriculadas:
            errores.append(f"{nombre} semestre: aprobadas no puede superar a matriculadas.")
        if entradas[f"Curricular units {sem} sem (credited)"] > matriculadas:
            errores.append(f"{nombre} semestre: convalidadas no puede superar a matriculadas.")
    return errores


def construir_perfil(medianas: dict, entradas: dict) -> pd.DataFrame:
    """Completa con las medianas de train las variables que no se ingresan.

    En el dataset, 0 materias aprobadas siempre implica promedio 0.
    """
    perfil = {**medianas, **entradas}
    for sem in SEMESTRES:
        if perfil[f"Curricular units {sem} sem (approved)"] == 0:
            perfil[f"Curricular units {sem} sem (grade)"] = 0.0
    return pd.DataFrame([perfil])[ALL_FEATURE_COLS]


def factores_riesgo(pipeline, medianas: dict, entradas: dict):
    """Mide cada dato por separado frente al perfil mediano.

    Parte del perfil con las medianas de train y cambia un solo dato cada vez:
    positivo sube el riesgo, negativo lo baja. Devuelve (riesgo_mediano, aportes
    de mayor a menor). Los aportes no se suman y no son una relación causal.
    """
    def probabilidad(cambios):
        return float(pipeline.predict_proba(construir_perfil(medianas, cambios))[0, 1])

    tipico = probabilidad({})
    aportes = {
        col: probabilidad({col: valor}) - tipico
        for col, valor in entradas.items()
        if valor != medianas[col]
    }
    return tipico, sorted(aportes.items(), key=lambda item: item[1], reverse=True)


def recomendaciones(perfil: dict, probabilidad: float, umbral: float) -> list:
    """Plan de acción sugerido según los datos del estudiante."""
    recs = []
    if perfil[COL_DEUDA] == 1 or perfil[COL_PAGOS] == 0:
        recs.append(("Apoyo financiero",
                     "Contactar con Bienestar Universitario para fraccionamiento o beca de emergencia."))
    if perfil[COL_APROB_2] < perfil[COL_MATRIC_2] / 2 or perfil[COL_APROB_1] < perfil[COL_MATRIC_1] / 2:
        recs.append(("Tutoría académica",
                     "Aprobó menos de la mitad de sus materias en algún semestre."))
    if perfil[COL_BECA] == 0 and probabilidad >= umbral:
        recs.append(("Evaluación socioeconómica",
                     "Revisar elegibilidad para beca o subsidio."))
    if perfil[COL_EDAD] >= 25:
        recs.append(("Flexibilidad horaria",
                     "Revisar si compagina estudios con cargas familiares o laborales."))
    if not recs:
        recs.append(("Seguimiento regular", "Sin factores de atención en los datos ingresados."))
    return recs


def _limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Títulos sin espacios sobrantes y sin filas totalmente vacías (conserva el número de fila)."""
    df.columns = df.columns.astype(str).str.strip()
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed: \d+$")]
    texto = df.astype(str).apply(lambda s: s.str.strip())
    return df[~(df.isna() | (texto == "")).all(axis=1)]


def leer_lote(contenido: bytes) -> pd.DataFrame:
    """Lee un CSV separado por ',' o ';' (UTF-8 o ANSI de Excel). Lanza ValueError si no se puede leer."""
    cabecera = contenido.split(b"\n", 1)[0]
    sep = ";" if cabecera.count(b";") > cabecera.count(b",") else ","
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(io.BytesIO(contenido), sep=sep, encoding=codificacion, dtype=object)
            break
        except UnicodeDecodeError:
            continue
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            raise ValueError(f"No se pudo leer el CSV: {e}") from e
    else:
        raise ValueError("No se pudo leer el CSV: codificación de texto no reconocida.")
    return _limpiar(df)


def leer_excel(ruta) -> pd.DataFrame:
    """Lee la hoja «Estudiantes» (la de la plantilla) o, si no existe, la primera hoja de un .xlsx."""
    try:
        with pd.ExcelFile(ruta, engine="openpyxl") as libro:
            hoja = "Estudiantes" if "Estudiantes" in libro.sheet_names else libro.sheet_names[0]
            df = libro.parse(hoja)
    except Exception as e:  # openpyxl lanza tipos variados según el daño del archivo
        raise ValueError(f"No se pudo leer el Excel: {e}") from e
    return _limpiar(df)


def etiquetas_reales(df: pd.DataFrame):
    """Devuelve y (0/1) si el archivo trae el resultado real utilizable; si no, None.

    Columna «Abandonó» (Sí/No o 1/0) o, en el formato original, «Target» (Dropout = abandonó).
    """
    if COL_REAL in df.columns:
        texto = df[COL_REAL].map(lambda v: normalizar_texto(v) if isinstance(v, str) else v)
        y = pd.to_numeric(texto.replace({"si": 1, "no": 0}), errors="coerce")
    elif TARGET_COL in df.columns:
        y = (df[TARGET_COL].astype(str).str.strip() == "Dropout").astype(int)
    else:
        return None
    return y.astype(int) if y.isin([0, 1]).all() and y.nunique() == 2 else None


def metricas(y_true, y_proba, umbral: float) -> dict:
    """Métricas de la clase Dropout con el umbral indicado."""
    from sklearn.metrics import (
        accuracy_score, confusion_matrix, f1_score, precision_score,
        recall_score, roc_auc_score,
    )
    y_pred = (np.asarray(y_proba) >= umbral).astype(int)
    y_true = np.asarray(y_true)
    return {
        "n": int(len(y_true)),
        "abandonaron": int(y_true.sum()),
        "detectados": int(((y_pred == 1) & (y_true == 1)).sum()),
        "alertas": int(y_pred.sum()),
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred),
        "roc_auc": roc_auc_score(y_true, y_proba),
        "cm": confusion_matrix(y_true, y_pred),
    }
