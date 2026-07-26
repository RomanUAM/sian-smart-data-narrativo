# Revisión crítica por agentes

Fecha: 2026-07-26

Esta revisión resume dos dictámenes: uno computacional/arquitectónico y otro
metodológico-humanístico. Los agentes no son módulos autónomos de ejecución; son
perfiles críticos usados para revisar coherencia, límites y publicación.

## Dictamen general

SIAN es coherente como prototipo local de humanidades computacionales para
construir corpus públicos estratificados y producir mapas narrativos revisables.
No debe presentarse todavía como plataforma validada, detector de verdad,
sistema legal operativo ni inferencia completa de la sociedad.

Formulación recomendada:

> SIAN no interpreta “la sociedad”; organiza evidencia pública estratificada y
> produce mapas narrativos revisables para lectura humana.

## Puntos fuertes

- Separación explícita de capas: noticias, foros/blogs/comunidades,
  instituciones y artículos científicos.
- Enfoque Smart Data: muestras trazables antes que acumulación masiva.
- Ejecución local sin envío de textos a modelos externos.
- Validación humana prevista para actores, grupos y exclusiones.
- Catálogo auditable de fuentes en `source_profiles.py`.
- Reddit tratado como señal opcional, no como columna vertebral.

## Riesgos

- `streamlit_app.py` concentra demasiadas responsabilidades: UI, planificador,
  ejecución, análisis y exportación.
- `news_spider.py` mezcla clientes de búsqueda, extracción, limpieza,
  clasificación y persistencia.
- Las señales de falacia, desinformación y silencios son heurísticas; deben
  leerse como indicios, no diagnósticos.
- “Cadena de custodia” debe entenderse como trazabilidad técnica, no como
  admisibilidad jurídica.
- Si faltan foros/blogs/conversaciones, no se debe afirmar narrativa social
  completa.

## Correcciones incorporadas tras la revisión

- Se añadió `.gitignore` para no subir bases, cachés ni salidas pesadas.
- Se añadió `RUN_LOCAL.md`.
- Se añadió `ARCHITECTURE.md`.
- Se actualizó `requirements.txt`.
- La app guarda `run_manifest.json` al iniciar cada corrida.
- La corrida secuencial guarda `query_plan.json`.
- Se añadió `scripts/run_query_plan.py` para repetir un plan secuencial sin
  depender de Streamlit.
- La documentación ya no presenta el manifiesto como pendiente total.

## Pendientes antes de artículo fuerte

- Extraer completamente el planificador secuencial a un módulo compartido; por
  ahora existe un runner independiente que re-ejecuta `query_plan.json`.
- Añadir hash final del corpus fusionado.
- Crear microcaso verificable: fuente → limpieza → clasificación → frame →
  lectura humana.
- Auditar manualmente una muestra por fuente y estado (`ok`, `ok_partial`,
  `too_short`, `fetch_error`).
- Separar cuerpo humanístico y apéndice técnico del cubridor/multiobjetivo.
