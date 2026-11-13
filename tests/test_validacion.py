"""Revisión fila por fila de la carga por lote y plantilla Excel."""
import openpyxl
import pandas as pd
import pytest

from app import rutas
from app.core import scoring
from app.core.validacion import ADVERTENCIA, ERROR, ErrorArchivo
from app.core.variables import ALL_FEATURE_COLS, COL_ID
from app.services.plantilla import crear_plantilla_excel


@pytest.fixture
def plantilla():
    return pd.read_csv(rutas.PLANTILLA_LOTE).astype(object)


class _Problemas(set):
    """Conjunto de (fila, nivel, texto); `in` compara el texto por prefijo."""

    def __contains__(self, buscado):
        fila, nivel, texto = buscado
        return any(f == fila and n == nivel and t.startswith(texto) for f, n, t in self)

    def __ge__(self, otros):
        return all(o in self for o in otros)


def _problemas(servicio, df):
    lote = servicio.evaluar_lote(df)
    return lote, _Problemas((p.Fila, p.Nivel, p.Problema) for p in lote.problemas.itertuples())


@pytest.mark.parametrize("columna, valor, problema", [
    ("Age at enrollment", "", "Valor vacío"),
    ("Age at enrollment", None, "Valor vacío"),
    ("GDP", "abc", "No es un número"),
    ("Course", 9238.5, "Debe ser un número entero"),
    ("Debtor", 2, "Debe ser 0 (No) o 1 (Sí)"),
    ("Curricular units 1st sem (grade)", 25, "Valor imposible: debe estar entre 0 y 20"),
    ("Age at enrollment", -3, "Valor imposible: debe estar entre 15 y 100"),
    ("Curricular units 1st sem (approved)", 9, "Aprobadas mayor que matriculadas"),
    ("Curricular units 2nd sem (credited)", 9, "Convalidadas mayor que matriculadas"),
])
def test_errores_excluyen_la_fila(servicio, plantilla, columna, valor, problema):
    plantilla.loc[0, columna] = valor
    lote, problemas = _problemas(servicio, plantilla)
    assert (2, ERROR, problema) in problemas
    assert lote.descartadas == 1 and len(lote.resultado) == 3
    assert plantilla.loc[0, COL_ID] not in set(lote.resultado[COL_ID])


@pytest.mark.parametrize("columna, valor, problema", [
    ("Course", 1234, "Código que el modelo no conoce"),
    ("Admission grade", 60, "Fuera de lo visto en entrenamiento"),
    ("GDP", 9.5, "Fuera de lo visto en entrenamiento"),
])
def test_advertencias_evaluan_con_aviso(servicio, plantilla, columna, valor, problema):
    plantilla.loc[0, columna] = valor
    lote, problemas = _problemas(servicio, plantilla)
    assert (2, ADVERTENCIA, problema) in problemas
    assert lote.descartadas == 0 and len(lote.resultado) == 4
    fila = lote.resultado[lote.resultado["Fila"] == 2].iloc[0]
    assert problema in fila["Avisos"]


def test_id_duplicado_y_promedio_sin_aprobadas(servicio, plantilla):
    plantilla.loc[1, COL_ID] = plantilla.loc[0, COL_ID]
    plantilla.loc[2, "Curricular units 2nd sem (approved)"] = 0
    plantilla.loc[2, "Curricular units 2nd sem (grade)"] = 13.5
    _, problemas = _problemas(servicio, plantilla)
    assert {(2, ADVERTENCIA, "ID repetido en el archivo"), (3, ADVERTENCIA, "ID repetido en el archivo"),
            (4, ADVERTENCIA, "Promedio mayor que 0 sin materias aprobadas")} <= problemas


def test_plantilla_limpia_no_tiene_problemas(servicio, plantilla):
    lote = servicio.evaluar_lote(plantilla)
    assert lote.problemas.empty and lote.descartadas == 0


def test_todas_las_filas_con_error_no_rompe(servicio, plantilla):
    plantilla["GDP"] = "x"
    lote = servicio.evaluar_lote(plantilla)
    assert lote.resultado.empty and lote.descartadas == 4 and len(lote.problemas) == 4


def test_columnas_faltantes_las_lista_todas(servicio, plantilla):
    with pytest.raises(ErrorArchivo) as e:
        servicio.evaluar_lote(plantilla.drop(columns=["GDP", "Gender", "Course"]))
    assert all(c in str(e.value) for c in ("GDP", "Gender", "Course")) and "plantilla" in str(e.value)


def test_columnas_extra_se_ignoran_y_se_informan(servicio, plantilla):
    plantilla["Observaciones"] = "x"
    lote = servicio.evaluar_lote(plantilla)
    assert lote.validacion.columnas_extra == ["Observaciones"] and len(lote.resultado) == 4


def test_plantilla_excel_se_genera_y_se_vuelve_a_cargar(servicio, tmp_path):
    ruta = crear_plantilla_excel(tmp_path / "plantilla.xlsx", servicio)
    libro = openpyxl.load_workbook(ruta)
    assert libro.sheetnames == ["Instrucciones", "Estudiantes", "Listas", "Diccionario"]
    hoja = libro["Estudiantes"]
    assert [c.value for c in hoja[1]] == [COL_ID, *ALL_FEATURE_COLS]
    assert len(hoja.data_validations.dataValidation) >= 30
    assert libro["Diccionario"].max_row == len(ALL_FEATURE_COLS) + 2

    lote = servicio.evaluar_lote(scoring.leer_excel(ruta))  # lee la hoja «Estudiantes»
    assert len(lote.resultado) == 4 and lote.problemas.empty
