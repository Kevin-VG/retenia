import pandas as pd
import pytest

from app import rutas
from app.core import scoring
from app.core.variables import (
    ALL_FEATURE_COLS, COL_APROB_1, COL_APROB_2, COL_ID, COL_MATRIC_1, ENTRADAS_FORMULARIO,
    describir_valor,
)


# ---------------------------------------------------------------- scoring
def test_semaforo_cortes():
    assert scoring.semaforo([0.39, 0.40, 0.59, 0.60, 0.95], 0.40).tolist() == [
        "Verde", "Amarillo", "Amarillo", "Rojo", "Rojo"]
    # Si el umbral supera 0.60, no hay franja amarilla
    assert scoring.semaforo([0.65, 0.70], 0.70).tolist() == ["Verde", "Rojo"]


def test_validacion_cruzada_de_materias(servicio):
    entradas = {c: int(servicio.perfiles["vulnerable"][c]) for c in ENTRADAS_FORMULARIO}
    assert servicio.validar(entradas) == []
    entradas[COL_APROB_1] = entradas[COL_MATRIC_1] + 1
    errores = servicio.validar(entradas)
    assert any("aprobadas no puede superar" in e for e in errores)


def test_perfiles_de_ejemplo_dan_los_tres_colores(servicio):
    colores = {c: servicio.evaluar(p).semaforo for c, p in servicio.perfiles.items()}
    assert colores == {"riesgo": "Rojo", "vulnerable": "Amarillo", "destacado": "Verde"}


def test_resultado_individual_completo(servicio):
    r = servicio.evaluar(servicio.perfiles["riesgo"])
    assert 0 <= r.probabilidad <= 1
    assert r.suben and all(v > 0 for _, v in r.suben)
    assert any(t == "Apoyo financiero" for t, _ in r.recomendaciones)
    assert set(r.perfil) == set(ALL_FEATURE_COLS)


def test_aprobadas_cero_fuerza_promedio_cero(servicio):
    perfil = scoring.construir_perfil(servicio.medianas, {COL_APROB_2: 0})
    assert perfil["Curricular units 2nd sem (grade)"].iat[0] == 0.0


def test_mas_aprobadas_menos_riesgo(servicio):
    probs = [servicio.evaluar({COL_APROB_2: k}).probabilidad for k in range(0, 7)]
    assert probs == sorted(probs, reverse=True)


def test_describir_valor():
    assert describir_valor("Course", 9500) == "Enfermería"
    assert describir_valor("Debtor", 1) == "Sí"
    assert describir_valor("Admission grade", 127.3) == "127.30"


# ---------------------------------------------------------------- lotes
def test_lote_csv_punto_y_coma_con_alias(servicio):
    df = pd.read_csv(rutas.PLANTILLA_LOTE).rename(columns={"Marital Status": "Marital status"})
    contenido = df.to_csv(sep=";", index=False).encode("utf-8-sig")
    lote = servicio.evaluar_lote(scoring.leer_lote(contenido))
    assert len(lote.resultado) == 4 and lote.metricas is None
    probs = lote.resultado["Prob. Deserción"].tolist()
    assert probs == sorted(probs, reverse=True)
    assert lote.resultado[COL_ID].iat[0] == "EJ-RIESGO"


def test_lote_excel_y_filas_invalidas(servicio, tmp_path):
    df = pd.read_csv(rutas.PLANTILLA_LOTE)
    df["GDP"] = df["GDP"].astype(object)
    df.loc[1, "GDP"] = "no-numérico"
    ruta = tmp_path / "lote.xlsx"
    df.to_excel(ruta, index=False)
    lote = servicio.evaluar_lote(scoring.leer_excel(ruta))
    assert len(lote.resultado) == 3 and lote.descartadas == 1


def test_lote_sin_columnas_da_error_claro(servicio):
    with pytest.raises(ValueError, match="Faltan"):
        servicio.evaluar_lote(pd.DataFrame({"a": [1]}))


def test_lote_sin_id_genera_identificador(servicio):
    df = pd.read_csv(rutas.PLANTILLA_LOTE).drop(columns=[COL_ID])
    lote = servicio.evaluar_lote(df)
    assert lote.resultado[COL_ID].str.startswith("FILA-").all()


# ---------------------------------------------------------------- historial
def test_historial_guardar_buscar_eliminar(servicio, historial):
    r = servicio.evaluar(servicio.perfiles["riesgo"])
    rid = historial.guardar(estudiante_id="A-001", nombre="Ana", origen="individual",
                            probabilidad=r.probabilidad, semaforo=r.semaforo, umbral=r.umbral,
                            perfil=r.perfil, entradas=r.entradas, notas="primera")
    n = historial.guardar_lote([
        {"estudiante_id": f"L-{i}", "probabilidad": 0.1, "semaforo": "Verde", "umbral": 0.4,
         "perfil": r.perfil} for i in range(5)
    ])
    assert n == 5 and historial.contar() == 6
    assert [x.id for x in historial.buscar("Ana")] == [rid]
    assert len(historial.buscar(semaforo="Verde")) == 5
    assert len(historial.buscar(origen="individual")) == 1

    reg = historial.obtener(rid)
    assert reg.entradas == {k: float(v) for k, v in r.entradas.items()}
    # Reevaluar desde el historial reproduce la misma probabilidad
    assert servicio.evaluar(reg.entradas, umbral=reg.umbral).probabilidad == pytest.approx(r.probabilidad)

    historial.actualizar_notas(rid, "seguimiento")
    assert historial.obtener(rid).notas == "seguimiento"
    assert historial.eliminar([rid]) == 1 and historial.contar() == 5
