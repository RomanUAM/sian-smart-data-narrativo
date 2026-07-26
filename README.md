# SIAN · Sistema local de análisis narrativo

SIAN es un prototipo local para construir corpus narrativos trazables a partir
de fuentes públicas. No busca acumular Big Data indiscriminado: busca Smart
Data, es decir, pocas fuentes relevantes, estructura argumental, relaciones,
deltas, silencios, hashes y evidencia auditable.

El sistema actual corre con Streamlit, JSON y CSV. Neo4j, FastAPI, PostgreSQL,
embeddings semánticos y reportes ejecutivos automatizados son ruta futura de
escalamiento, no requisito del prototipo actual.

La versión actual incorpora disección estructural de narrativas: extracción
heurística de proposiciones, actos de habla, causalidad, premisas implícitas,
señales de falacia, vectores de desinformación, entropía narrativa y cadena de
custodia. El marco está documentado en
[`STRUCTURAL_NARRATIVE_DISSECTION.md`](STRUCTURAL_NARRATIVE_DISSECTION.md).
La poda inteligente Big Data → Smart Data está documentada en
[`SMART_DATA_NUCLEUS.md`](SMART_DATA_NUCLEUS.md).
La auditoría de coherencia lógica y pertinencia está en
[`SIAN_COHERENCE_AUDIT.md`](SIAN_COHERENCE_AUDIT.md).
La arquitectura computacional y el papel de los agentes locales están en
[`ARCHITECTURE.md`](ARCHITECTURE.md).
La ejecución local paso a paso está en
[`RUN_LOCAL.md`](RUN_LOCAL.md).
La revisión crítica por agentes está resumida en
[`AGENT_REVIEW_SUMMARY.md`](AGENT_REVIEW_SUMMARY.md).

Usa varios índices públicos según la capa seleccionada: GDELT, Google News RSS,
blogs/comunidades abiertas, Reddit/RSS público como fuente tardía, OpenAlex,
Crossref y, cuando existe URL abierta, PDFs. GDELT es uno de los índices
posibles, no el único.

El sistema está pensado para investigaciones que necesitan distinguir entre
géneros discursivos. Una noticia, una conversación en foro, un reporte
institucional y un artículo académico no hablan desde la misma posición; por eso
se recolectan, clasifican y analizan por separado antes de cualquier síntesis.

El objetivo no es mezclar todos los textos como si fueran equivalentes, sino separar géneros discursivos útiles para estudiar estructura narrativa:

1. `scientific_article`: artículos de investigación científica, revistas académicas, DOI, preprints y repositorios académicos.
2. `institutional_report`: gobierno, organismos públicos, regulación, comunicados, leyes y documentos institucionales.
3. `industry_report`: encuestas o reportes industriales, por ejemplo encuestas de desarrolladores.
4. `news`: noticias, medios periodísticos, revistas y portales informativos.
5. `forum`: foros, blogs públicos, comunidades y discusiones de usuarios.
6. `other`: fuente con evidencia insuficiente.

Además, cada corrida debe declarar una región analítica: mundo/global, México,
América Latina, Iberoamérica o una región personalizada.

## Campos guardados

Cada noticia se guarda con:

- `query`
- `query_variants`
- `geographic_scope`
- `geographic_terms`
- `year`
- `source_type`
- `source_type_confidence`
- `source_type_evidence`
- `evidence_level`
- `evidence_weight`
- `medium`
- `url`
- `title`
- `published_date`
- `language`
- `country`
- `text_raw_visible`
- `text_clean`
- `text_normalized`
- `text_length`
- `word_count`
- `paragraph_count`
- `cleaning_notes`
- `source_api`
- `fetched_at`
- `status`
- `error`

`text_raw_visible` conserva el texto visible extraido de la pagina. `text_clean`
intenta quedarse con el cuerpo editorial de la noticia. `text_normalized` baja
mayusculas, quita puntuacion y homogeneiza acentos para analisis textual.

`source_type` permite separar el corpus antes del análisis de narrativa. La
clasificación es automática y auditable: `source_type_confidence` indica qué tan
fuerte fue la evidencia y `source_type_evidence` explica la regla usada.

`evidence_weight` es metadato para auditoría, análisis estratificado o corridas
de sensibilidad. No debe usarse como ponderación base si se mezclan géneros de
fuente, porque produciría sesgos distintos en la red narrativa:

- 4 = artículo científico o fuente académica.
- 3 = reporte/encuesta industrial.
- 2 = noticia o fuente periodística.
- 1 = foro o discusión profesional.
- 0 = fuente no clasificada.

`geographic_scope` y `geographic_terms` registran si el estudio se diseñó para
México, América Latina, mundo/global u otra delimitación.

Además se generan:

- `news_output/news_records.json`
- `news_output/news_records.jsonl`
- un archivo `.json` por noticia dentro de carpetas por año.

## Análisis local de narrativas

La pestaña de análisis trabaja sobre los JSON guardados y no manda textos a modelos externos. Calcula:

El análisis parte de un marco común: una narrativa es una estructura situada de
sentido, no una simple frecuencia de palabras. En la app se analiza quién habla,
desde qué capa discursiva, qué actores aparecen, qué conflicto o tensión se
organiza, qué cambio se marca, qué consecuencias se atribuyen y qué validación
humana requiere la lectura.

Para el ejemplo `tatuaje`, el sistema permite distinguir tatuaje como archivo
corporal, práctica estética, oficio, memoria e identidad, riesgo sanitario,
estigma laboral, regulación pública y circulación visual/cultural. Estos rubros
son editables porque el tópico puede cambiar.

Los estados de texto se interpretan así:

- `ok`: cuerpo suficiente para análisis textual completo.
- `ok_partial`: título/resumen RSS o metadato corto usable como señal narrativa pública; debe reportarse separado.
- `too_short`: registro heredado o texto corto; sólo se analiza si conserva título/texto.
- `fetch_error`/`error`: no se usa para análisis textual.

La recolección distingue profundidad de búsqueda, cuota máxima y suficiencia
muestral. La profundidad por mes/motor controla cuántos resultados se piden a
cada índice. La cuota máxima anual por tipo discursivo, por defecto 100,
balancea el corpus: hasta 100 `news`, 100 `forum`, 100
`scientific_article`, 100 `industry_report` y 100 `other` por año. El mínimo
deseado por año y tipo audita representación: si algún tipo queda en cero o por
debajo de la meta, el sistema debe reportarlo como muestra insuficiente en lugar
de asumir representatividad.

Las fuentes de noticias se manejan mediante un catálogo auditable
(`source_profiles.py`), no como una lista informal de dominios. Cada perfil
declara dominio, país, región, idioma, tipo de acceso, patrón esperado de URL,
secciones útiles y marcadores de limpieza. El catálogo base incluye medios
mexicanos, latinoamericanos, estadounidenses, británicos y brasileños para que
la comparación regional sea explícita. Las fuentes con acceso parcial o paywall
no deben contarse como texto completo si sólo entregan título, resumen o
metadatos.

La extracción respeta límites técnicos y derechos de fuente: antes de intentar
texto completo se consulta `robots.txt`; si no está permitido, o si el sitio es
paywall/parcial, el registro se conserva como `ok_partial` con metadato
trazable. El sistema no automatiza sesiones, CAPTCHAs ni espacios privados. En
artículos o reportes se debe publicar análisis agregado y citas breves, no
redistribución masiva del texto.

Para las capas sociales hay controles más estrictos. Al correr el botón
`Noticias`, la araña sólo acepta registros clasificados como `news` y reporta si
no alcanza el mínimo anual configurado, por defecto 50. Al correr
`Foros/conversaciones`, sólo acepta registros `forum` y reporta la misma brecha
mínima, por defecto 50. Esta regla obliga a separar la búsqueda social de la
académica: los artículos científicos ya no pueden llenar artificialmente la
cuota social. Si la red abierta no entrega 50 registros por año, el resultado se
marca como insuficiente en vez de presentarse como corpus balanceado.

La capa `Gobierno/instituciones` se guarda aparte como `institutional_report`.
No representa conversación orgánica: representa autoridad pública, regulación,
política pública y documentos oficiales que pueden influir en prensa,
conversaciones e investigación.

La opción `Correr araña mezclada` muestra un tablero año × tipo de fuente con
metas mínimas y topes máximos. Durante la ejecución cada registro aceptado se
reporta con su `source_type` y contador, por ejemplo `news 17/100`. Al terminar
cada mes se emite `balance_status` para ver qué capas siguen incompletas. El
balance se intenta por cuota anual independiente; no significa que el sistema
invente registros ni que `other` sea una categoría interpretativa válida.

- distribución del corpus por año, fuente, tipo de fuente, evidencia, idioma y localización;
- estructura narrativa por documento: evento inicial, conflicto, punto de cambio, resolución y consecuencias;
- actores detectados, validación humana de actores y contexto/situación del documento;
- monogramas, bigramas, trigramas y frases canónicas con stopwords editables;
- grupos de ideas locales;
- grafo de conocimiento con monogramas, bigramas, trigramas, fuentes, años, idioma y localización;
- red semántica por coocurrencia;
- disección estructural: sujeto-verbo-objeto, actos de habla, causalidad,
  premisas ocultas, señales heurísticas de falacia, vectores de desinformación,
  entropía de actos/predicados y cadena de custodia SHA-256;
- Smart Data Nucleus: cartografía Pareto de fuentes, marcos
  problema-culpable-solución-urgencia, detección de ecos, deltas temporales y
  silencios estructurales definidos por el analista;
- selección comparada de nodos relevantes mediante cubridor narrativo; la app permite comparar barrido glotón por suma ponderada, MOEA, MOSA y adaptación local multiobjetivo del método de composición musical (MMC-MO) de Mora-Gutiérrez et al.;
- frente Pareto, hipervolumen normalizado y superficie empírica \(u_1 \times u_3 \to u_2\) para comparar soluciones;
- exportaciones CSV.
- tonalidad léxica local por documento, año y tipo de fuente;
- gráficas radiales donde cada eje es una capa de fuente y el valor es el promedio de tonalidad normalizado;
- desde la app, JSON único enriquecido con registros filtrados, eventos, tonalidad léxica, redes, grupos y cubridor base.

La comparación de métodos del cubridor usa una región factible común. El mínimo
de nodos, la mínima relevancia nodal y el máximo daño estructural no son sólo
filtros posteriores: entran en la evaluación. La app aplica criterio de Coello:
factible sobre infactible; entre factibles, Pareto; entre infactibles, menor
violación. El hipervolumen se calcula únicamente sobre soluciones factibles y
cada método reporta presupuesto, evaluaciones usadas y llamadas reales a la
función objetivo.

## Corrida secuencial recomendada

Para trabajo publicable no conviene usar una sola búsqueda mezclada. La app
permite correr de manera lineal:

```text
mes × capa de fuente × muestra aleatoria reproducible de términos/rubros
```

El usuario puede seleccionar las capas que quiere correr:

- noticias;
- foros/conversaciones;
- artículos científicos + PDFs abiertos;
- reportes/otros.

La capa `reportes/otros` debe entenderse como búsqueda general clasificada
después por evidencia. Todavía no es un índice especializado de reportes
institucionales.

Cada paso guarda su salida por separado y muestra avance con rubro, año, fuente
y número de registros. En noticias, foros, instituciones y reportes, el plan
elige hasta N términos por mes/capa —por defecto 8— usando una semilla
reproducible. Así no se barre todo el diccionario cada mes y no se privilegia
siempre el primer sinónimo. En artículos científicos la búsqueda se mantiene
anual para evitar duplicados de OpenAlex/Crossref.

La estructura esperada es:

```text
news_output/
  by_rubric/
    <rubro>/
      <año-mes>/
        news/
        forums/
        articles/
        reports_other/
  news_records_sequential_merged.json
  news_records_sequential_merged.jsonl
```

Este diseño permite auditar si el corpus tiene sólo artículos, sólo noticias o
si realmente hay capas de diálogo social. Si un año o fuente no tiene resultados,
se reporta como vacío o insuficiente; no se inventa información.

## Documentación del algoritmo

Hay dos documentos metodológicos locales:

- `ALGORITMO_SISTEMA.md`: explicación operativa rápida del sistema.
- `publication/algoritmo_sistema_narrativo.tex`: versión LaTeX con diagramas TikZ del algoritmo.

El documento TikZ describe:

- arquitectura general;
- corrida secuencial;
- limpieza y composición de frases;
- tonalidad léxica local y radar por fuente;
- red narrativa;
- red semántica y grafo de conocimiento;
- disección estructural de proposiciones e influencia;
- cubridor nodal multiobjetivo;
- exportación final a `narrative_analysis_unified.json`.

Las figuras están redactadas para una audiencia de humanidades: muestran fases
interpretativas, decisiones de corpus y trazabilidad metodológica. Los detalles
computacionales quedan en el texto para no abrumar al lector no especializado.

## Apéndice técnico: modelo matemático del cubridor

El cubridor se define como un SCP multiobjetivo sobre la red narrativa
ponderada. El universo es el conjunto de aristas objetivo \(A^*\), no el conjunto
de documentos. Cada nodo candidato \(v\in B\) cubre sus aristas incidentes
\(S_v\).

Variables:

- \(x_v\in\{0,1\}\): selecciona el nodo candidato \(v\).
- \(r_a\in\{0,1\}\): indica si la arista \(a\in A^*\) se remueve al retirar el conjunto seleccionado.
- \(b_{av}\in\{0,1\}\): incidencia entre arista \(a\) y nodo \(v\).

Restricciones principales:

- \(r_a \geq b_{av}x_v\): una arista se marca como removida si toca un nodo seleccionado.
- \(r_a \leq \sum_v b_{av}x_v\): una arista no puede removerse si no toca ningún nodo seleccionado.
- \(\sum_v x_v \leq k\): presupuesto de nodos interpretables.
- \(x_v \leq e_v\): exclusión manual/metodológica de nodos, medios o términos.
- \(L_h \leq \sum_v q_{vh}x_v \leq U_h\): cuotas opcionales por tipo de nodo.

Objetivos:

- minimizar \(\sum_v x_v/|B|\);
- maximizar \(\sum_v \sigma_vx_v/\sum_v\sigma_v\);
- minimizar \(\sum_a w_ar_a/\sum_aw_a\), es decir, el daño estructural que ocurriría al retirar el cubridor.

En la app, las soluciones se comparan por dominancia de Pareto con el mismo criterio de
factibilidad en todos los métodos: factible domina infactible; entre infactibles
gana la menor violación total; entre factibles se aplica Pareto. Los métodos se
comparan con el mismo presupuesto de evaluaciones de función objetivo y con las
mismas métricas: hipervolumen normalizado, puntos no dominados globales,
distancia generacional inversa (IGD), spacing y dispersión del frente en
\((u_1,u_2,u_3)\). La función escalar interna sólo guía la búsqueda; no sustituye
el modelo multiobjetivo.

La comparación estadística no debe hacerse sobre todas las soluciones generadas.
Para cada método y corrida se calcula primero su subconjunto factible no
dominado. Sobre ese frente se calculan hipervolumen, IGD, spacing y dispersión.
La IGD usa como referencia el frente empírico ideal: la unión factible no
dominada de todos los métodos y corridas. La app exige al menos 10 corridas por
método, con semillas pareadas y el mismo presupuesto de evaluaciones. Reporta
promedio, mediana, moda redondeada, mínimo, máximo, varianza, intervalo
bootstrap al 95% para la media y prueba pareada de Wilcoxon entre métodos.

Por defecto, la red narrativa usa ponderación neutral: documentos, actores,
etapas, fuentes y metadatos no reciben jerarquía previa. Su importancia emerge
de frecuencia y conectividad observada. El modo con énfasis en etapas/completitud
queda sólo como análisis de sensibilidad.

El sistema considera un flujo analítico de producción narrativa:

1. diálogo individual / foros;
2. noticias y prensa;
3. derivaciones técnicas o institucionales;
4. investigación científica;
5. otras derivaciones.

Este flujo no es un peso automático. Es una capa para analizar cómo una narrativa
circula y retroalimenta discursos posteriores. Las investigaciones también pueden
impactar noticias y diálogos futuros, por lo que debe analizarse como ciclo, no
como cadena causal rígida.

Los pesos de nodos y aristas se calculan por conteo de apariciones. Se conserva
el conteo crudo (`raw_weight`, `raw_count`) y se agrega una versión normalizada
en \([0,1]\) (`weight`, `weight_norm`, `count_norm`, `weighted_degree_norm`) para
comparar redes y resolver el cubridor sin mezclar escalas.

Antes de construir los grafos semántico y de conocimiento, los n-gramas se
componen en frases canónicas: si un bigrama o trigama repetido explica la mayor
parte de las apariciones de sus partes, las partes se marcan como
`absorbed_ngram` y la frase queda como nodo principal. Lo mismo se refleja en
las aristas, porque la coocurrencia y las relaciones documento--concepto se
calculan sobre nodos canónicos del documento, no sobre palabras sueltas. La
composición exige al menos dos apariciones para evitar que una frase accidental
se vuelva concepto.

El MMC-MO no resuelve las relajaciones lineales en cada iteración. Para cada
instancia del problema resuelve una vez las relajaciones monoobjetivo de
\(u_1=1-f_1\), \(u_2=f_2\), \(u_3=1-f_3\) y un punto balanceado. Esas soluciones
se guardan en memoria como guía inicial y después se actualizan con soluciones
no dominadas encontradas durante la búsqueda.

La extracción de eventos narrativos es heurística y auditable. Cada etapa guarda
la oración detectada y los marcadores textuales que activaron la clasificación.
Esto es menos opaco que usar un LLM directamente y permite corrección manual
para trabajo publicable.

## Correr con Streamlit

Desde esta carpeta de proyecto:

```bash
cd /Users/romananselmomoragutierrez/Documents/Codex/2026-06-20/c/news_spider
streamlit run streamlit_app.py
```

Luego abre la URL que indique Streamlit, normalmente:

```text
http://localhost:8501
```

## Correr por terminal

```bash
cd /Users/romananselmomoragutierrez/Documents/Codex/2026-06-20/c/news_spider
python3 news_spider.py \
  --query "ciencias basicas ingenieria" \
  --query-variants "educacion STEM,formacion en ingenieria" \
  --start-year 2020 \
  --end-year 2024 \
  --geographic-scope "mexico" \
  --geographic-terms "Mexico,México,mexicano,mexicana" \
  --domains "jornada.com.mx,elpais.com" \
  --output-dir news_output \
  --max-records-per-month 30 \
  --delay 1
```

La corrida por terminal cubre la recolección básica. La corrida secuencial por
rubro × año × fuente, la tonalidad léxica, la exportación del JSON único y la
comparación multiobjetivo completa están implementadas principalmente en la app
Streamlit. Para ejecución reproducible fuera de la app, esas rutas deben
extraerse a scripts dedicados.

## Recomendación metodológica

Para investigación seria:

1. Define una consulta estable.
2. Define si analizarás noticias, artículos científicos, foros o una comparación entre esos tres tipos.
3. Declara la región: México, América Latina, mundo/global u otra.
4. Registra años, medios/dominios, tipo de fuente y fecha de descarga.
5. Usa `max-records-per-month` para evitar que años recientes dominen el corpus.
6. Conserva registros con `fetch_error`; sirven para reportar sesgo de acceso.
7. No interpretes el corpus como “todas las fuentes”, sino como una muestra reproducible basada en los índices públicos seleccionados y extracción local.

## Ejemplo de diseño para IA y programación

Para estudiar la narrativa sobre asistentes de IA en programación, conviene
buscar por variantes como:

- `AI pair programming`
- `AI coding assistants`
- `GitHub Copilot`
- `developer productivity`
- `software engineering AI`
- `supervisory engineering work`

Y comparar por tipo de evidencia:

- artículos científicos sobre productividad, supervisión, errores y revisión;
- encuestas industriales como Stack Overflow Developer Survey;
- noticias especializadas sobre cambios en la profesión;
- foros de desarrolladores donde aparecen problemas prácticos, seguridad,
  arquitectura y corrección de código generado.

## Limitaciones

- Algunos sitios bloquean descargas automáticas.
- Algunos textos quedan contaminados por menús o publicidad.
- La limpieza elimina bloques tipicos como related posts, author bio,
  publicidad, cookies, titulos repetidos y duplicados, pero conviene auditar
  una muestra manualmente por cada medio.
- Paywalls y PDFs pueden no producir texto limpio.
- La clasificación de tipo de fuente es una primera capa automática; conviene auditar manualmente una muestra de cada tipo.
- Si necesitas corpus académico/publicable, conviene revisar una muestra manualmente para estimar error de extracción.
- Cada corrida desde la app guarda `run_manifest.json`; las corridas secuenciales guardan además `query_plan.json`. Para publicación estricta todavía conviene añadir hash final del corpus y auditoría manual por muestra/fuente.
