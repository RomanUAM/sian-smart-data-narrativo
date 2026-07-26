# Agente computacional y arquitectónico

Propósito: revisar que el sistema sea ejecutable localmente, reproducible,
modular y auditable. No evalúa la interpretación cultural; evalúa si el código,
los datos y los flujos hacen lo que los documentos prometen.

## Criterios de revisión

- La app debe correr localmente con `streamlit run streamlit_app.py`.
- Las dependencias deben estar en `requirements.txt`.
- Los datos descargados no deben subirse a GitHub por defecto.
- Las corridas deben guardar `run_manifest.json`.
- Las corridas secuenciales deben guardar `query_plan.json`.
- El plan debe poder repetirse sin interfaz con `scripts/run_query_plan.py`.
- La corrida secuencial debe evitar fuerza bruta: mes × capa × muestra reproducible de términos.
- Reddit debe ser opcional, no fuente principal.
- El código debe compilar con `python3 -m py_compile`.
- Las salidas deben poder recuperarse desde JSON/JSONL aunque Streamlit se cierre.

## Riesgos que debe detectar

- Módulos demasiado grandes o acoplados.
- Funciones definidas en la app pero usadas en módulos donde no existen.
- Botones que prometen acciones no implementadas.
- Métricas calculadas sobre objetos no comparables.
- Corridas multiobjetivo con diferente presupuesto de evaluaciones.
- Falta de hashes o manifiestos.
- Carga de corpus gigantes en memoria sin guardado incremental.
- Rutas relativas que cambian si Streamlit se ejecuta desde otra carpeta.
- Botones destructivos sin confirmación ni restricción de ruta.
- Merge de bases que pierda la procedencia cuando una URL aparece en varias
  capas de fuente.
- Corridas mixtas que prometen balance por tipo pero aceptan tipos fuera del
  conjunto solicitado.

## Estado actual

El proyecto ya tiene ejecución local, manifiesto, plan secuencial y runner de
reproducción. Sigue pendiente separar más la arquitectura:

- `planner.py` para construir planes;
- `runner.py` para ejecutar planes;
- `analysis_ui.py` para separar interfaz y análisis;
- pruebas unitarias mínimas para plan, manifiesto y clasificación de fuentes.

## Lecciones aprendidas

- Las rutas de recursos internos deben resolverse desde `Path(__file__).parent`,
  no desde el directorio donde el usuario lanzó Streamlit.
- `run_manifest.json` debe actualizarse al finalizar con estado, conteos,
  hashes y error si falla la corrida.
- Si `scripts/run_query_plan.py` recibe `--output-dir`, debe reubicar las
  salidas de cada paso bajo esa carpeta para que el replay sea portable.
