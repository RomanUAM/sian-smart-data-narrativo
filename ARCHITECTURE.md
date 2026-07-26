# Arquitectura de SIAN

SIAN es un sistema local para construir y analizar corpus narrativos
estratificados. No es una araña de fuerza bruta ni un detector automático de
verdad. Su función es organizar evidencia pública, separar capas discursivas y
producir mapas revisables para lectura humana.

## Principios

1. **Local primero.** El análisis se calcula en la máquina del usuario.
2. **Smart Data antes que Big Data.** Se prefieren muestras trazables,
   balanceadas y auditables sobre volúmenes grandes pero sesgados.
3. **Capas separadas.** Noticias, foros, instituciones y artículos científicos
   se recolectan y evalúan por separado.
4. **Muestreo reproducible.** La corrida secuencial usa una semilla para elegir
   términos/rubros por mes y capa.
5. **Interpretación humana.** Los algoritmos sugieren nodos, relaciones y
   brechas; no sustituyen la lectura crítica.

## Módulos

| Módulo | Papel |
|---|---|
| `streamlit_app.py` | Interfaz local, configuración, corrida secuencial, visualizaciones y exportación. |
| `news_spider.py` | Recolección pública, extracción permitida, limpieza inicial, clasificación de fuentes y guardado incremental. |
| `source_profiles.py` | Catálogo auditable de medios, foros, blogs, instituciones y perfiles de limpieza. |
| `narrative_analysis.py` | Análisis local: n-gramas, eventos narrativos, grafos, cubridor, Louvain y métodos de optimización. |
| `structural_narrative.py` | Disección estructural: proposiciones, actos de habla, marcos, ecos, deltas, silencios y trazabilidad técnica. |
| `reclean_outputs.py` | Reprocesamiento local de textos ya recolectados. |
| `scripts/` | Utilidades reproducibles de extracción y solución. |
| `publication/` | TeX, PDF, DOCX y scripts de documentos publicables. |
| `.agents/` | Memoria crítica de agentes: criterios de revisión computacional, humanística y editorial. |

## Flujo de recolección

```text
tópico
  → rubros y variantes
  → año
  → mes
  → capa de fuente
  → muestra aleatoria reproducible de términos
  → consulta pública corta
  → extracción permitida por robots/HTML visible
  → limpieza
  → clasificación de fuente
  → JSON incremental
```

La unidad de búsqueda es un término por consulta. No se concatenan todos los
sinónimos porque eso satura índices, genera 429 y vuelve opaco qué término
recuperó cada documento.

## Ejecución recuperable

La interfaz genera `run_manifest.json` y, en corridas secuenciales,
`query_plan.json`. El archivo `scripts/run_query_plan.py` permite repetir ese
plan sin Streamlit:

```text
query_plan.json → scripts/run_query_plan.py → corpus fusionado + manifiesto replay
```

Esto separa diseño interactivo y ejecución reproducible. La app sigue siendo el
laboratorio de configuración; el script permite repetir o auditar la corrida de
forma local.

## Capas de fuente

| Capa | Qué intenta captar | Riesgo |
|---|---|---|
| Noticias | Agenda pública mediada por prensa. | Sesgo editorial, sindicación, notas repetidas. |
| Foros/blogs/comunidades | Lenguaje situado y experiencia pública indexable. | Cobertura incompleta; Reddit bloquea; no representa toda la sociedad. |
| Instituciones | Normas, alertas, reportes y política pública. | Voz formal, no conversación social. |
| Artículos científicos | Estabilización académica/técnica. | Puede dominar el corpus si no se separa por capa. |

## Agentes locales

Los archivos en `.agents/` no son procesos autónomos. Son memoria crítica local:

- `roman_mora_cognitive_agent.md`: exige coherencia, límites, trazabilidad y
  claridad para públicos no computacionales.
- `sinergia_narrativas_humanidades.md`: define narrativa como estructura
  situada de sentido y obliga a separar capas discursivas.
- `legal_ethics_agent.md`: revisa fuentes públicas, límites OSINT,
  trazabilidad técnica y riesgos de publicación.
- `computational_architecture_agent.md`: revisa ejecución local,
  reproducibilidad, manifiestos, planes y acoplamiento de módulos.
- `logical_consistency_agent.md`: revisa coherencia formal entre modelo,
  objetivos, restricciones, métricas y visualizaciones.

Estos agentes se aplican como criterios de revisión documental y de diseño. Si
una regla del usuario cambia la validez del sistema, debe actualizarse ahí.

## Publicación en GitHub

Debe versionarse:

- código fuente;
- documentación;
- agentes;
- semillas públicas;
- documentos publicables.

Debe ignorarse:

- bases descargadas completas;
- salidas experimentales grandes;
- cachés;
- credenciales;
- datos privados o no autorizados.
