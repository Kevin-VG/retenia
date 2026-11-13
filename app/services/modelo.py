"""Servicio del modelo: carga del pipeline y evaluación individual o por lote."""
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app import rutas
from app.core import scoring
from app.core.validacion import Validacion, validar_lote
from app.core.variables import ALL_FEATURE_COLS, COL_CONV_1, COL_ID, ETIQUETAS, NOMINAL_COLS


class ErrorModelo(RuntimeError):
    """El modelo no se puede usar con garantías (versión de scikit-learn incompatible)."""


@dataclass
class ResultadoIndividual:
    perfil: dict                 # 36 variables usadas por el modelo
    entradas: dict               # variables ingresadas por el usuario
    probabilidad: float
    semaforo: str
    umbral: float
    riesgo_mediano: float
    suben: list = field(default_factory=list)       # [(col, aporte)]
    bajan: list = field(default_factory=list)
    recomendaciones: list = field(default_factory=list)  # [(titulo, detalle)]


@dataclass
class ResultadoLote:
    resultado: pd.DataFrame      # filas sin errores + Prob. Deserción + Semáforo, ordenadas por riesgo
    validacion: Validacion       # problemas detectados fila por fila
    metricas: dict | None        # si el archivo trae el resultado real

    @property
    def descartadas(self) -> int:
        return self.validacion.n_errores

    @property
    def problemas(self) -> pd.DataFrame:
        return self.validacion.problemas


def categorias_del_modelo(pipeline) -> dict:
    """Códigos nominales que el modelo vio al entrenar ({} si el pipeline no tiene ese paso)."""
    try:
        encoder = pipeline.named_steps["preprocessor"].named_transformers_["nominal"]
        return {col: {float(v) for v in cats} for col, cats in zip(NOMINAL_COLS, encoder.categories_)}
    except (AttributeError, KeyError):
        return {}


def cargar_pipeline(ruta: Path):
    """Carga el .joblib tal cual y rechaza versiones de scikit-learn distintas a la del modelo.

    scikit-learn avisa con InconsistentVersionWarning si el modelo se guardó con otra versión;
    aquí ese aviso se convierte en error para no dar predicciones poco fiables.
    """
    import joblib
    from sklearn.exceptions import InconsistentVersionWarning

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always", InconsistentVersionWarning)
        pipeline = joblib.load(ruta)
    for aviso in avisos:
        if issubclass(aviso.category, InconsistentVersionWarning):
            m = aviso.message
            raise ErrorModelo(
                f"El modelo se guardó con scikit-learn {m.original_sklearn_version} pero está instalada "
                f"la versión {m.current_sklearn_version}. Las predicciones podrían no ser fiables."
            )
    return pipeline


class ServicioModelo:
    """Carga el pipeline una sola vez y expone las operaciones de la app."""

    def __init__(self, ruta_modelo: Path = rutas.MODELO, ruta_config: Path = rutas.CONFIG):
        self.config = json.loads(Path(ruta_config).read_text(encoding="utf-8"))
        self.pipeline = cargar_pipeline(Path(ruta_modelo))
        self.umbral = float(self.config["umbral_operativo"])
        self.medianas = {c: float(v) for c, v in self.config["medianas"].items()}
        self.rangos = {c: tuple(v) for c, v in self.config["rangos"].items()}
        self.perfiles = self.config["perfiles_ejemplo"]
        self.rangos_entrenamiento = {
            c: tuple(v) for c, v in self.config.get("rangos_entrenamiento", {}).items()
        }
        self.categorias_conocidas = categorias_del_modelo(self.pipeline)

    @property
    def nombre_modelo(self) -> str:
        return self.config["modelo"]

    def probabilidades(self, X: pd.DataFrame):
        return self.pipeline.predict_proba(X[ALL_FEATURE_COLS])[:, 1]

    # ----- Evaluación individual -----
    def validar(self, entradas: dict) -> list:
        completas = {**entradas, COL_CONV_1: int(self.medianas[COL_CONV_1])}
        return scoring.validar_perfil(completas, self.rangos, ETIQUETAS)

    def evaluar(self, entradas: dict, umbral: float | None = None) -> ResultadoIndividual:
        """Evalúa las variables del formulario; el resto toma la mediana de train."""
        umbral = self.umbral if umbral is None else umbral
        perfil_df = scoring.construir_perfil(self.medianas, entradas)
        prob = float(self.pipeline.predict_proba(perfil_df)[0, 1])
        return self._resultado(perfil_df.iloc[0].to_dict(), entradas, prob, umbral)

    def explicar(self, perfil: dict, umbral: float | None = None) -> ResultadoIndividual:
        """Resultado completo para un perfil de 36 variables (p. ej. una fila de lote)."""
        umbral = self.umbral if umbral is None else umbral
        perfil = {c: float(perfil[c]) for c in ALL_FEATURE_COLS}
        prob = float(self.pipeline.predict_proba(pd.DataFrame([perfil])[ALL_FEATURE_COLS])[0, 1])
        return self._resultado(perfil, perfil, prob, umbral)

    def _resultado(self, perfil, entradas, prob, umbral) -> ResultadoIndividual:
        riesgo_mediano, factores = scoring.factores_riesgo(self.pipeline, self.medianas, entradas)
        return ResultadoIndividual(
            perfil=perfil,
            entradas=dict(entradas),
            probabilidad=prob,
            semaforo=str(scoring.semaforo([prob], umbral)[0]),
            umbral=umbral,
            riesgo_mediano=riesgo_mediano,
            suben=[(c, v) for c, v in factores if v >= 0.01][:3],
            bajan=[(c, v) for c, v in reversed(factores) if v <= -0.01][:3],
            recomendaciones=scoring.recomendaciones(perfil, prob, umbral),
        )

    # ----- Evaluación por lote -----
    def validar_lote(self, df: pd.DataFrame) -> Validacion:
        return validar_lote(df, self.categorias_conocidas, self.rangos_entrenamiento)

    def evaluar_lote(self, df: pd.DataFrame, umbral: float | None = None) -> ResultadoLote:
        """Valida fila por fila y evalúa las filas sin errores. Lanza ErrorArchivo si el archivo
        no se puede usar en absoluto (p. ej. faltan columnas)."""
        umbral = self.umbral if umbral is None else umbral
        df = df.reset_index(drop=True)
        v = self.validar_lote(df)
        validas = ~v.con_error
        X = v.X[validas]

        resultado = df[validas].drop(columns=[COL_ID], errors="ignore").copy()
        resultado[ALL_FEATURE_COLS] = X
        proba = self.probabilidades(X) if len(X) else pd.Series(dtype=float).to_numpy()
        avisos = v.avisos_por_fila()
        resultado.insert(0, "Avisos", v.filas[validas].map(avisos).fillna("").to_numpy())
        resultado.insert(0, "Fila", v.filas[validas].to_numpy())
        resultado.insert(0, "Semáforo", scoring.semaforo(proba, umbral))
        resultado.insert(0, "Prob. Deserción", proba.round(4))
        resultado.insert(0, COL_ID, v.ids[validas].to_numpy())
        resultado = resultado.sort_values("Prob. Deserción", ascending=False, kind="stable")

        y = scoring.etiquetas_reales(df[validas]) if len(X) else None
        return ResultadoLote(
            resultado=resultado.reset_index(drop=True),
            validacion=v,
            metricas=None if y is None else scoring.metricas(y, proba, umbral),
        )
