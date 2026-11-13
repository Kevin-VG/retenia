"""Variables del modelo, etiquetas en español y descripciones de valores.

Los nombres de columna son los del dataset UCI #697. El orden de ALL_FEATURE_COLS
debe coincidir con el usado al entrenar el modelo.
"""

NOMINAL_COLS = [
    "Marital Status",
    "Application mode",
    "Course",
    "Previous qualification",
    "Nacionality",
    "Mother's qualification",
    "Father's qualification",
    "Mother's occupation",
    "Father's occupation",
]

BINARY_COLS = [
    "Daytime/evening attendance",
    "Displaced",
    "Educational special needs",
    "Debtor",
    "Tuition fees up to date",
    "Gender",
    "Scholarship holder",
    "International",
]

NUMERIC_COLS = [
    "Application order",
    "Age at enrollment",
    "Previous qualification (grade)",
    "Admission grade",
    "Curricular units 1st sem (credited)",
    "Curricular units 1st sem (enrolled)",
    "Curricular units 1st sem (evaluations)",
    "Curricular units 1st sem (approved)",
    "Curricular units 1st sem (grade)",
    "Curricular units 1st sem (without evaluations)",
    "Curricular units 2nd sem (credited)",
    "Curricular units 2nd sem (enrolled)",
    "Curricular units 2nd sem (evaluations)",
    "Curricular units 2nd sem (approved)",
    "Curricular units 2nd sem (grade)",
    "Curricular units 2nd sem (without evaluations)",
    "Unemployment rate",
    "Inflation rate",
    "GDP",
]

ALL_FEATURE_COLS = NOMINAL_COLS + BINARY_COLS + NUMERIC_COLS

# Columnas del formulario individual
COL_CARRERA = "Course"
COL_EDAD = "Age at enrollment"
COL_MATRIC_1 = "Curricular units 1st sem (enrolled)"
COL_APROB_1 = "Curricular units 1st sem (approved)"
COL_CONV_1 = "Curricular units 1st sem (credited)"
COL_MATRIC_2 = "Curricular units 2nd sem (enrolled)"
COL_APROB_2 = "Curricular units 2nd sem (approved)"
COL_CONV_2 = "Curricular units 2nd sem (credited)"
COL_PAGOS = "Tuition fees up to date"
COL_DEUDA = "Debtor"
COL_BECA = "Scholarship holder"
COL_ID = "id_estudiante"

ENTRADAS_FORMULARIO = [
    COL_CARRERA, COL_EDAD,
    COL_MATRIC_1, COL_APROB_1,
    COL_MATRIC_2, COL_APROB_2, COL_CONV_2,
    COL_PAGOS, COL_DEUDA, COL_BECA,
]

COLUMNAS_SI_NO = set(BINARY_COLS)

ETIQUETAS = {
    "Marital Status": "Estado civil",
    "Application mode": "Modalidad de postulación",
    "Course": "Carrera",
    "Previous qualification": "Nivel educativo previo",
    "Nacionality": "Nacionalidad",
    "Mother's qualification": "Estudios de la madre",
    "Father's qualification": "Estudios del padre",
    "Mother's occupation": "Ocupación de la madre",
    "Father's occupation": "Ocupación del padre",
    "Daytime/evening attendance": "Turno diurno",
    "Displaced": "Estudiante desplazado",
    "Educational special needs": "Necesidades educativas especiales",
    "Debtor": "Tiene deudas pendientes",
    "Tuition fees up to date": "Pagos de matrícula al día",
    "Gender": "Género masculino",
    "Scholarship holder": "Tiene beca",
    "International": "Estudiante internacional",
    "Application order": "Orden de preferencia de la carrera",
    "Age at enrollment": "Edad al matricularse",
    "Previous qualification (grade)": "Nota de estudios previos",
    "Admission grade": "Nota de admisión",
    "Curricular units 1st sem (credited)": "Materias convalidadas 1er semestre",
    "Curricular units 1st sem (enrolled)": "Materias matriculadas 1er semestre",
    "Curricular units 1st sem (evaluations)": "Evaluaciones 1er semestre",
    "Curricular units 1st sem (approved)": "Materias aprobadas 1er semestre",
    "Curricular units 1st sem (grade)": "Promedio 1er semestre",
    "Curricular units 1st sem (without evaluations)": "Materias sin evaluar 1er semestre",
    "Curricular units 2nd sem (credited)": "Materias convalidadas 2do semestre",
    "Curricular units 2nd sem (enrolled)": "Materias matriculadas 2do semestre",
    "Curricular units 2nd sem (evaluations)": "Evaluaciones 2do semestre",
    "Curricular units 2nd sem (approved)": "Materias aprobadas 2do semestre",
    "Curricular units 2nd sem (grade)": "Promedio 2do semestre",
    "Curricular units 2nd sem (without evaluations)": "Materias sin evaluar 2do semestre",
    "Unemployment rate": "Tasa de desempleo (%)",
    "Inflation rate": "Tasa de inflación (%)",
    "GDP": "Crecimiento del PBI (%)",
}

CARRERAS = {
    33: "Tecnologías de Producción de Biocombustibles",
    171: "Diseño de Animación y Multimedia",
    8014: "Servicio Social (nocturno)",
    9003: "Agronomía",
    9070: "Diseño de Comunicación",
    9085: "Enfermería Veterinaria",
    9119: "Ingeniería Informática",
    9130: "Equinocultura",
    9147: "Administración",
    9238: "Servicio Social",
    9254: "Turismo",
    9500: "Enfermería",
    9556: "Higiene Oral",
    9670: "Gestión de Publicidad y Marketing",
    9773: "Periodismo y Comunicación",
    9853: "Educación Básica",
    9991: "Administración (nocturno)",
}

# Valores decimales: se muestran con 1–2 decimales en vez de enteros
COLUMNAS_DECIMALES = {
    "Previous qualification (grade)", "Admission grade",
    "Curricular units 1st sem (grade)", "Curricular units 2nd sem (grade)",
    "Unemployment rate", "Inflation rate", "GDP",
}


def describir_valor(col: str, valor) -> str:
    """Texto legible para un valor de una variable del modelo."""
    if col == COL_CARRERA:
        return CARRERAS.get(int(valor), f"Código {int(valor)}")
    if col in COLUMNAS_SI_NO:
        return "Sí" if int(valor) == 1 else "No"
    if col in COLUMNAS_DECIMALES:
        return f"{float(valor):.2f}"
    if col in NOMINAL_COLS:
        return f"Código {int(valor)}"
    return str(int(round(float(valor))))
