# Ficha del modelo — RetenIA

## Resumen

| | |
|---|---|
| **Tarea** | Clasificación binaria: el estudiante abandona (`Dropout` = 1) o no (`Enrolled` + `Graduate` = 0) |
| **Algoritmo** | `GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=4, subsample=0.8)` |
| **Preprocesamiento** | `ColumnTransformer`: One-Hot (9 nominales) · passthrough (8 binarias) · `StandardScaler` (19 numéricas) → 235 columnas |
| **Archivo** | `app/resources/model/pipeline_ganador.joblib` · configuración en `config.json` |
| **Dependencias** | scikit-learn 1.9.1 · NumPy 2.4.4 · pandas 3.0.2 (fijadas) |

## Datos

- **Fuente:** UCI #697 *Predict Students' Dropout and Academic Success* (CC BY 4.0). 4,424 estudiantes de
  una institución de educación superior de Portugal, 36 variables (demográficas, socioeconómicas,
  académicas del 1er y 2do semestre, macroeconómicas).
- **Partición:** 80 % entrenamiento (3,539) / 20 % prueba (885), estratificada, semilla 42.
- **Tasa base de abandono:** 32.1 %.

## Selección

Validación cruzada estratificada de 5 pliegues sobre entrenamiento; métrica principal F1 de la clase Dropout.

| Modelo | F1 (VC) | ROC-AUC (VC) |
|---|---|---|
| **Gradient Boosting** | **0.7907 ± 0.0085** | 0.9146 |
| Random Forest | 0.7873 ± 0.0177 | 0.9130 |
| Regresión logística | 0.7860 ± 0.0147 | 0.9209 |
| Árbol de decisión | 0.7481 ± 0.0219 | 0.8630 |

Los tres primeros están en **empate técnico** (diferencias menores que la variación entre pliegues).

## Rendimiento

| Conjunto | Umbral | F1 | Precision | Recall | Accuracy | ROC-AUC |
|---|---|---|---|---|---|---|
| Prueba (885) | 0.50 | 0.808 | 86.1 % | 76.1 % | 88.4 % | 0.934 |
| **Prueba (885)** | **0.40 (operativo)** | **0.827** | **82.2 %** | **83.1 %** | **88.8 %** | **0.934** |
| Validación cruzada (train) | 0.40 | 0.793 | 81.1 % | 77.5 % | — | 0.915 |

- Intervalo bootstrap 95 % en prueba (umbral 0.40): F1 0.79–0.86 · Recall 0.79–0.87.
- La validación cruzada es la estimación más prudente: con umbral 0.40 el recall esperado ronda 0.78.
- **Calibración:** buena (Brier 0.084); las probabilidades se pueden leer como frecuencias aproximadas.

## Semáforo

| Probabilidad | Nivel | Acción sugerida |
|---|---|---|
| < 40 % | 🟢 Riesgo bajo | Seguimiento regular |
| 40 % – 60 % | 🟡 Riesgo moderado | Seguimiento cercano y tutoría preventiva |
| ≥ 60 % | 🔴 Riesgo alto | Prioridad: entrevista con Bienestar, plan financiero o beca |

## Variables más influyentes (permutación, prueba)

1. Materias aprobadas en 2do semestre (caída de F1 ≈ 0.226)
2. Pagos de matrícula al día (≈ 0.076)
3. Materias aprobadas en 1er semestre (≈ 0.010)
4. Tiene beca · materias convalidadas 2do semestre · edad al matricularse

## Uso previsto

- **Sí:** priorizar a qué estudiantes ofrecer acompañamiento (tutoría, apoyo financiero, orientación).
- **No:** sancionar, negar admisión, becas o servicios, ni sustituir el juicio de una persona.

## Limitaciones

- **Momento de la predicción.** Las variables más fuertes (notas del 2do semestre) solo existen al terminar
  el primer año. Con datos de matrícula solamente, el rendimiento cae (ROC-AUC ≈ 0.82).
- **Otra población.** El modelo aprendió de una institución portuguesa (2008–2019). Antes de usarlo en otra
  universidad conviene validarlo con datos locales.
- **Clase `Enrolled`.** Los estudiantes aún matriculados cuentan como «no abandono», aunque algunos podrían
  abandonar después. Parte de las «falsas alarmas» puede ser riesgo real aún no materializado.
- **Equidad.** El modelo usa género, edad y nacionalidad. Género aparece entre las 10 variables más
  influyentes; revisar disparidades por grupo antes de un uso institucional.
- **Formulario individual.** Solo se ingresan 10 variables; las otras 26 toman la mediana de entrenamiento.
  Para una evaluación completa, usar la carga por lote con las 36 variables.
- **Explicaciones.** Los «puntos» de cada factor se obtienen cambiando un dato a la vez frente al perfil
  mediano. Describen cómo razona el modelo, no relaciones causales, y no se suman.
