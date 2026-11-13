"""Valores de referencia del modelo: si cambian, cambió el modelo o el entorno (scikit-learn, NumPy…)."""
import pandas as pd
import pytest

from app import rutas
from tests.conftest import LOTE_COMPLETO
from app.services.modelo import ErrorModelo, cargar_pipeline

# Probabilidades obtenidas con pipeline_ganador.joblib y las versiones de requirements.txt
REFERENCIA_PERFILES = {"riesgo": 0.9625, "vulnerable": 0.4577, "destacado": 0.0269}
REFERENCIA_PLANTILLA = {"EJ-RIESGO": 0.9625, "EJ-VULNERABLE": 0.4577, "EJ-MEDIANO": 0.0545,
                        "EJ-DESTACADO": 0.0269}


def test_configuracion(servicio):
    assert servicio.nombre_modelo == "Gradient Boosting"
    assert servicio.umbral == 0.4


def test_perfiles_dan_probabilidades_de_referencia(servicio):
    obtenidas = {c: round(servicio.evaluar(p).probabilidad, 4) for c, p in servicio.perfiles.items()}
    assert obtenidas == REFERENCIA_PERFILES


def test_formato_completo_da_probabilidades_de_referencia(servicio):
    lote = servicio.evaluar_lote(pd.read_csv(LOTE_COMPLETO))
    obtenidas = dict(zip(lote.resultado["id_estudiante"], lote.resultado["Prob. Deserción"]))
    assert obtenidas == REFERENCIA_PLANTILLA


def test_version_distinta_de_sklearn_se_rechaza(monkeypatch):
    import warnings

    import joblib
    from sklearn.exceptions import InconsistentVersionWarning

    def carga_con_aviso(ruta):
        warnings.warn(InconsistentVersionWarning(
            estimator_name="Pipeline", current_sklearn_version="9.9", original_sklearn_version="1.9.1"))
        return object()

    monkeypatch.setattr(joblib, "load", carga_con_aviso)
    with pytest.raises(ErrorModelo, match="1.9.1"):
        cargar_pipeline(rutas.MODELO)
