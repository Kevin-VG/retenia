"""Revisión fila por fila de la carga por lote y plantilla Excel."""
import openpyxl
import pandas as pd
import pytest

from tests.conftest import LOTE_COMPLETO
from app.core import scoring
from app.core.validacion import ADVERTENCIA, ERROR, ErrorArchivo
from app.core.variables import COL_ID, COLUMNAS_OBLIGATORIAS, COLUMNAS_PLANTILLA
from app.services.plantilla import crear_plantilla_excel, encabezado, fila_plantilla, valor_plantilla


@pytest.fixture
def plantilla():
    return pd.read_csv(LOTE_COMPLETO).astype(object)


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
    ("Age at enrollment", "", "Falta este dato"),
    ("Age at enrollment", None, "Falta este dato"),
    ("GDP", "abc", "Debe ser un número"),
    ("Course", 9238.5, "Debe ser un número entero"),
    ("Course", "Medicina", "Valor no reconocido"),
    ("Debtor", 2, "Valor no reconocido: usa «Sí» o «No»"),
    ("Debtor", "Tal vez", "Valor no reconocido: usa «Sí» o «No»"),
    ("Curricular units 1st sem (grade)", 25, "Fuera del rango permitido (0 a 20)"),
    ("Age at enrollment", -3, "Fuera del rango permitido (15 a 100)"),
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
    ("Course", 1234, "Código no reconocido"),
    ("Admission grade", 60, "Valor poco habitual"),
    ("GDP", 9.5, "Valor poco habitual"),
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


def test_columnas_obligatorias_faltantes_se_listan_en_espanol(servicio, plantilla):
    with pytest.raises(ErrorArchivo) as e:
        servicio.evaluar_lote(plantilla.drop(columns=["Debtor", "Course"]))
    assert all(t in str(e.value) for t in ("Tiene deudas pendientes", "Carrera", "plantilla"))


def test_columnas_opcionales_faltantes_o_vacias_usan_valor_tipico(servicio, plantilla):
    completo = servicio.evaluar_lote(plantilla).resultado.set_index(COL_ID)["Prob. Deserción"]
    reducido = plantilla.drop(columns=["GDP", "Gender", "Mother's occupation"])
    reducido["Admission grade"] = ""
    lote = servicio.evaluar_lote(reducido)
    assert lote.problemas.empty
    assert lote.resultado.set_index(COL_ID)["Prob. Deserción"].to_dict() == completo.to_dict()


def test_columnas_extra_se_ignoran_y_se_informan(servicio, plantilla):
    plantilla["Observaciones"] = "x"
    lote = servicio.evaluar_lote(plantilla)
    assert lote.validacion.columnas_extra == ["Observaciones"] and len(lote.resultado) == 4


def _fila_espanol(servicio, clave, **cambios):
    """Fila con títulos en español y opciones escritas como texto, como en la plantilla."""
    perfil = {**servicio.perfiles[clave], **cambios}
    return {encabezado(c): valor_plantilla(c, perfil[c]) for c in COLUMNAS_OBLIGATORIAS} | {
        "ID estudiante": clave}


def test_formato_espanol_da_lo_mismo_que_el_formulario(servicio):
    df = pd.DataFrame([_fila_espanol(servicio, c) for c in servicio.perfiles])
    assert "Carrera *" in df.columns and df.loc[0, "Pagos de matrícula al día *"] in ("Sí", "No")
    lote = servicio.evaluar_lote(df)
    assert lote.problemas.empty
    obtenidas = dict(zip(lote.resultado[COL_ID], lote.resultado["Prob. Deserción"]))
    esperadas = {c: round(servicio.evaluar(p).probabilidad, 4) for c, p in servicio.perfiles.items()}
    assert obtenidas == esperadas


def test_texto_escrito_a_mano_y_csv_de_excel_en_espanol(servicio):
    filas = [_fila_espanol(servicio, c) for c in servicio.perfiles]
    filas[0]["Tiene beca *"] = "si"                       # sin tilde ni mayúscula
    filas[1]["Carrera *"] = "  enfermeria "               # sin tilde y con espacios
    for f in filas:  # coma decimal; vacío donde no aprobó materias
        f["Promedio 1er semestre"] = "" if f["ID estudiante"] == "riesgo" else "12,5"
    csv = pd.DataFrame(filas).to_csv(sep=";", index=False).encode("cp1252")  # «CSV» de Excel en Windows
    lote = servicio.evaluar_lote(scoring.leer_lote(csv))
    assert lote.problemas.empty and len(lote.resultado) == 3
    fila = lote.resultado.set_index(COL_ID)
    assert fila.loc["riesgo", "Scholarship holder"] == 1 and fila.loc["vulnerable", "Course"] == 9500
    assert fila.loc["destacado", "Curricular units 1st sem (grade)"] == 12.5


def test_resultado_real_abandono_si_no(servicio):
    df = pd.DataFrame([_fila_espanol(servicio, c) for c in servicio.perfiles])
    df["Abandonó"] = ["Sí", "No", "No"]
    m = servicio.evaluar_lote(df).metricas
    assert m is not None and m["n"] == 3 and m["abandonaron"] == 1 and m["detectados"] == 1


def test_plantilla_excel_se_genera_y_se_vuelve_a_cargar(servicio, tmp_path):
    ruta = crear_plantilla_excel(tmp_path / "plantilla.xlsx", servicio)
    libro = openpyxl.load_workbook(ruta)
    assert libro.sheetnames == ["Instrucciones", "Estudiantes", "Listas", "Valores válidos"]
    hoja = libro["Estudiantes"]
    titulos = [c.value for c in hoja[1]]
    assert titulos == [encabezado(c) for c in [COL_ID, *COLUMNAS_PLANTILLA]]
    assert hoja.max_row == 1  # sin filas de ejemplo
    validaciones = hoja.data_validations.dataValidation
    assert len(validaciones) == len(titulos) and all(v.prompt for v in validaciones)
    assert libro["Valores válidos"].max_row == len(COLUMNAS_PLANTILLA) + 2

    with pytest.raises(ErrorArchivo, match="no tiene filas"):
        servicio.evaluar_lote(scoring.leer_excel(ruta))

    for clave, perfil in servicio.perfiles.items():
        hoja.append(fila_plantilla(perfil, clave))
    hoja.append([None] * len(titulos))  # fila vacía: se ignora
    libro.save(ruta)
    lote = servicio.evaluar_lote(scoring.leer_excel(ruta))  # lee la hoja «Estudiantes»
    assert len(lote.resultado) == 3 and lote.problemas.empty
