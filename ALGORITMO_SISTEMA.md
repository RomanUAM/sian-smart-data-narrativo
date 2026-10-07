# Guía metodológica del sistema local de análisis narrativo

La ejecución histórica versión 3 está implementada en el coordinador independiente y documentada en [RECOLECCION_HISTORICA.md](RECOLECCION_HISTORICA.md). Mantiene el contrato de evidencia v2, añade tareas transaccionales, cuota total anual, control compartido de límites, archivo recuperable y cobertura por motivos. Esta especificación sustituye la ejecución ligada a una sesión y las cuotas automáticas por tipo; no convierte los informes históricos en nuevas mediciones.

Este documento resume la arquitectura actual del sistema. La versión formal con
figuras TikZ está en `publication/algoritmo_sistema_narrativo.tex`.

## Idea central

El sistema no debe mezclar todas las fuentes como si fueran equivalentes. Para
un tópico adaptable —por ejemplo `tatuaje`, pero también cualquier otro— se
separan:

1. rubros de variantes o sinónimos;
2. años;
3. capas de fuente;
4. registros recuperados;
5. análisis local.

Después se integra todo en un archivo estructurado que conserva procedencia,
limpieza, clasificación y resultados de análisis.

## Fases explicadas para humanidades

El sistema puede leerse como nueve fases interpretativas:

1. **Delimitar.** Se define el tópico, la región, los años y los rubros. Esto
   evita mezclar sentidos distintos del mismo término.
2. **Reunir voces.** Se buscan documentos por año y por tipo de fuente. Esto
   permite distinguir prensa, foros, artículos y reportes.
3. **Depurar.** Se limpian textos, duplicados, menús, publicidad y términos
   contaminantes. Esto evita que el ruido web se vuelva “resultado”.
4. **Describir.** Se calculan expresiones frecuentes, eventos narrativos,
   actores y tonalidad léxica exploratoria. Esto da una primera lectura auditable.
5. **Podar inteligentemente.** Se aplica Smart Data Nucleus: fuentes Pareto,
   marcos problema--culpable--solución--urgencia, ecos, deltas temporales y
   silencios definidos por el analista.
6. **Diseccionar.** Se extraen proposiciones, actos de habla, causalidad,
   hipótesis de premisas implícitas y marcadores retóricos revisables. No
   son sentencias: son señales para revisión humana.
7. **Relacionar.** Se construyen redes entre textos, actores, ideas, fuentes,
   años y momentos del relato. Esto muestra conexiones, no causalidades
   automáticas.
8. **Seleccionar.** Se resuelve el cubridor nodal multiobjetivo para proponer
   nodos de entrada relevantes sin confundirlos con “la verdad” del corpus.
9. **Sintetizar.** Se exporta un JSON único con evidencia, métricas, redes,
   Smart Data, disección estructural y trazabilidad.
   Esto permite comparar interpretaciones y revisar evidencia.

Las figuras del documento LaTeX están pensadas para lectores de humanidades:
nombran las fases como decisiones interpretativas y dejan los detalles técnicos
en el texto.

## Entrada

El usuario define:

- tópico base;
- rubros de variantes;
- región de estudio;
- años inicial y final;
- capas de fuente a correr;
- exclusiones conceptuales;
- dominios incluidos o excluidos;
- meta total de documentos únicos por año, compartida entre capas;
- texto mínimo y fuentes históricas disponibles.

No se imponen automáticamente 50 noticias y 50 foros. La distribución por fuentes se informa como cobertura y requiere un diseño independiente para inferencias sociales.

Los medios no se tratan como dominios sueltos. El sistema usa un catálogo de
perfiles de fuente (`source_profiles.py`) donde cada medio tiene país, región,
idioma, acceso, patrón de URL, secciones y reglas de limpieza. Para noticias
pueden activarse perfiles de México, América Latina, Estados Unidos, Reino Unido
y Brasil. Esto hace transparente qué parte de la narrativa procede de prensa
nacional, prensa extranjera o fuentes parcialmente extractables.

Ejemplo para tatuaje:

```text
tópico: tatuaje
rubros:
  núcleo: tatuaje, tatuajes, tattoo, tattoos, arte corporal
  oficio_industria: tatuador, tatuadora, tattoo artist, estudio de tatuajes
  sentido_identidad: significado de tatuaje, tatuaje identidad, tatuaje memoria
  sociedad_trabajo: tatuaje juventud, tatuaje género, tatuaje discriminación
  salud_regulacion: tatuaje salud, tintas para tatuaje, regulación sanitaria tatuajes
exclusiones:
  cigar, cigars, tobacco, tabaco, robusto, colonoscopic tattooing
```

Los conectores solos (`y`, `e`, `o`, `and`, `or`, `de`, `en`) no se usan como
variantes. Si se quiere estudiar una relación, se expresa como frase sustantiva:
`tatuaje empleo`, no `tatuaje y empleo`.

## Coordinador histórico recuperable

El plan se guarda antes de consultar. Se intercalan años, meses y capas; las consultas académicas son anuales y las públicas mensuales. Las fuentes se eligen por capacidad temporal. Los sitemaps tienen cursor y no aportan fechas de publicación mediante `lastmod`.

```text
guardar configuración y plan en SQLite
para cada tarea pendiente o diferida:
  comprobar pausa solicitada y cuota total del año
  comprobar capacidad temporal y cooldown del motor
  consultar índices, semillas o archivos permitidos
  recuperar y limpiar el contenido disponible
  confirmar cada registro con identidad y procedencia
  validar publicación, pertinencia y copias exactas
  actualizar cuota anual compartida y motivos de exclusión
  confirmar tarea o conservarla como pendiente, fallida o diferida
  exportar corpus y cobertura; intentar respaldo configurado
cerrar con pausa, cuota alcanzada, fuentes pendientes o brechas
```

`collection_runner.py` corre fuera de la sesión Streamlit. `collection_jobs.py` guarda tareas y documentos; `source_control.py` comparte pausas dentro de la ejecución. Una recarga recupera la misma base mediante su código. Un ZIP completo permite restaurarla si se pierde el disco. El bloqueo de proceso evita trabajadores simultáneos sobre la misma ejecución.

Noticias, foros, instituciones, artículos y reportes conservan su tipo y procedencia. La capa de reportes sigue siendo búsqueda general, no un índice especializado. La conjugación fusiona identidades mediante DOI o URL y preserva versiones y conflictos. Copias exactas entre URLs se retienen pero sólo una contribuye a la cuota.

La pantalla muestra meta total, documentos seleccionados y brecha por año, además de distribuciones por fuente, rubro y mes. Los parciales, faltantes de fecha y errores no se transforman en éxito. Alcanzar la cuota puede omitir tareas pendientes de ese año: el corpus es una muestra de disponibilidad y no una serie representativa de tendencias.

La especificación completa, estados y comandos están en [RECOLECCION_HISTORICA.md](RECOLECCION_HISTORICA.md).

## Extracción responsable

El sistema sólo debe usar índices públicos, RSS públicos, páginas abiertas o
URLs semilla. Antes de descargar HTML completo consulta `robots.txt`; si la
fuente no permite extracción, está cerrada o sólo ofrece resumen/metadato, el
registro queda como `ok_partial`. Esta señal puede servir para cobertura y
trazabilidad, pero no equivale a texto completo. No se automatizan sesiones,
CAPTCHAs ni espacios privados.

## Salidas de recolección

La salida se guarda por separado:

```text
news_output/
  by_rubric/
    <rubro>/
      <año>/
        news/
        forums/
        articles/
        reports_other/
  news_records_sequential_merged.json
  news_records_sequential_merged.jsonl
```

El JSON fusionado conserva:

- rubro;
- capa de fuente;
- año;
- tipo de fuente;
- medio;
- URL;
- título;
- texto limpio;
- estado de extracción;
- evidencia de clasificación.

Cada ejecución guarda `run_manifest.json`, `query_plan.json`, `coverage.json`, `coverage_annual.csv` y la base SQLite. El manifiesto incluye hashes de configuración y plan, capacidades y estado de tareas. Esto
permite auditar qué se intentó aunque la recolección se detenga. Para una
publicación estrictamente reproducible conviene añadir después un hash final del
corpus resultante y una auditoría manual de una muestra por fuente.

En artículos científicos el sistema no equipara “indexado” con “libre”. OpenAlex
se consulta en modo OA; Crossref se usa como índice DOI y sólo se acepta por
defecto cuando hay enlace abierto/PDF. Google Scholar no se raspa. Dominios como
ScienceDirect o Springer sólo son señales bibliográficas si aparecen por índices
o presets; no autorizan descarga ni almacenamiento de texto cerrado.

## Limpieza y normalización

Antes del análisis:

- se pasa el texto a minúsculas;
- se normalizan acentos;
- se eliminan menús, publicidad, cookies, títulos repetidos y bloques comunes;
- se aplican stopwords en español e inglés;
- se eliminan términos excluidos por el usuario;
- se filtran documentos con baja relevancia tópica.

La limpieza se aplica antes de monogramas, bigramas, trigramas, red semántica y
grafo de conocimiento.

## Análisis local

El análisis no usa LLM ni servicios externos. Calcula localmente:

- distribución por año, fuente, medio, idioma y localización;
- monogramas, bigramas y trigramas;
- composición de frases canónicas;
- eventos narrativos: evento inicial, conflicto, punto de cambio, resolución y consecuencias;
- actores candidatos y validación humana;
- grupos de ideas;
- Smart Data Nucleus: fuentes Pareto, frames, ecos, deltas y silencios;
- disección estructural: sujeto-verbo-objeto, actos de habla, causalidad,
  hipótesis de premisas implícitas, marcadores retóricos revisables y señales
  de presión narrativa;
- trazabilidad técnica con hash por registro;
- tonalidad léxica exploratoria;
- red narrativa;
- red semántica;
- grafo de conocimiento;
- módulos semánticos Louvain cuando está disponible;
- cubridor nodal multiobjetivo.

Antes de calcular, la app explicita el marco de lectura: una narrativa no es
sólo una palabra frecuente ni una medición de sentimiento. Se entiende como una
estructura situada de sentido donde una fuente habla, nombra actores, organiza
una tensión, marca cambios y deja consecuencias en un tiempo, lugar y capa
discursiva. Por eso las salidas deben leerse como indicios, mapas y síntesis
revisables, no como interpretación automática.

## Tonalidad léxica exploratoria

La tonalidad léxica es exploratoria. Se calcula con un léxico local bilingüe,
incluyendo reglas simples de negación e intensificación:

```text
score = (positivos - negativos) / (positivos + negativos)
```

Se reporta por documento, año y tipo de fuente. Las gráficas radiales usan:

```text
radio = (score + 1) / 2
```

Cada eje del radar es una capa de fuente. No debe interpretarse como emoción
colectiva; sólo indica vocabulario valorativo observado en el corpus.

## Red narrativa

La red contiene nodos de:

- documentos;
- actores;
- etapas narrativas;
- fuente;
- año;
- localización;
- tipo de fuente;
- conceptos.

Las aristas pesan por conteo de aparición. La ponderación base es neutral: no
se asigna mayor valor previo a noticias, artículos o foros. Las diferencias
entre fuentes se analizan estratificando o comparando capas.

Los actores, ideas y momentos narrativos pueden provenir de reglas locales,
diccionarios editables, n-gramas, patrones lingüísticos y validación humana. Si
el tópico cambia, cambian también los rubros, las exclusiones y los grupos de
ideas. En el caso `tatuaje`, por ejemplo, el mapa puede separar archivo corporal,
oficio, memoria, identidad, salud, estigma, regulación y circulación visual.

## Cúbridor multiobjetivo

El problema usa una adaptación del set covering problem.

Objetivos:

1. minimizar el número relativo de nodos seleccionados;
2. maximizar el peso relativo de los nodos seleccionados;
3. minimizar el peso relativo de las aristas que se perderían si se retiraran esos nodos.

Una arista se considera removida si toca al menos un nodo seleccionado. No se
usa el subgrafo inducido como definición de daño estructural.

Todos los métodos deben resolver la misma instancia:

- mismo grafo;
- mismas restricciones;
- mismo criterio de factibilidad;
- mismo presupuesto de evaluaciones;
- mismas métricas.

La factibilidad no se trata como filtro visual posterior. Forma parte de la
evaluación de cada solución:

- tamaño mínimo del conjunto;
- tamaño máximo del conjunto;
- peso nodal mínimo requerido;
- daño estructural máximo permitido;
- nodos válidos y no duplicados.

La comparación usa el criterio de Coello:

1. entre solución factible e infactible, gana la factible;
2. entre dos factibles, se aplica dominancia de Pareto;
3. entre dos infactibles, gana la de menor suma de violaciones absolutas a la
   región factible.

El hipervolumen se calcula sólo con soluciones factibles. Si un método no
produce factibles, su hipervolumen es cero y debe reportarse la violación.

Cada evaluación discreta de una solución cuenta como llamada a la función
objetivo. `weighted_greedy_sweep`, `MOEA`, `MOSA` y `MMC-MO` usan el mismo
presupuesto. Las semillas de PL relajado de `MMC-MO` también se cuentan cuando
son evaluadas como soluciones discretas.

La evaluación estadística de métodos se hace por corridas repetidas, no con una
sola ejecución. En cada corrida se conserva sólo el frente factible no dominado
de cada método. Sobre ese frente se calculan:

- hipervolumen;
- IGD contra el frente empírico ideal;
- dispersión del frente;
- spacing.

El frente empírico ideal se construye como la unión factible no dominada de
todos los métodos y todas las corridas. Para comparación publicable se
recomienda ejecutar al menos 10 corridas por método con semillas pareadas y el
mismo número de evaluaciones de función objetivo. Después se reporta promedio,
mediana, moda redondeada, máximo, mínimo, varianza, intervalo bootstrap al 95%
para la media y prueba de Wilcoxon pareada para cada métrica.

Métodos:

- barrido glotón ponderado;
- MOEA;
- MOSA;
- MMC-MO guiado por memoria de soluciones relajadas.

## JSON único de análisis

Desde la app, la pestaña `Exportar` crea:

```text
narrative_analysis_unified.json
```

Incluye:

- registros filtrados;
- tonalidad léxica;
- eventos narrativos;
- actores;
- grupos de ideas;
- red narrativa;
- red semántica;
- grafo de conocimiento;
- cubridor base y resultados asociados disponibles en la sesión de análisis.

Este archivo es la base para análisis posterior, publicación o reproducción.
La comparación multiobjetivo completa entre métodos se consulta en las pestañas
de cubridor y red semántica de la app; si se requiere reproducibilidad fuera de
Streamlit, debe trasladarse esa exportación a un script dedicado.


## Actualización de evidencia: 6 de octubre de 2026

La disponibilidad de autor, fecha, fuente, actores o postura no se garantiza.
Cada campo conserva valor, evidencia, método y estado; los faltantes no son cero.
La publicación se separa de actualización, consulta y año de búsqueda.
Cada análisis informa su subconjunto utilizable y cobertura. Los resultados
heurísticos son candidatos; las afirmaciones y relaciones revisadas requieren
fragmentos de respaldo. Un enlace PDF no equivale a texto completo recuperado.

La especificación vigente, modelos descriptivos y pseudocódigos están en
[EVIDENCIA_Y_MODELOS.md](EVIDENCIA_Y_MODELOS.md). Esta política prevalece sobre
supuestos de completitud de versiones anteriores. Los documentos históricos
conservan sus límites y no se recalculan por actualizar el software.


## Arquitectura y registros v2 (6 de octubre de 2026)

El contrato versionado separa documento, versión y recuperación. Las etapas tienen
puntos de control íntegros y reanudación; los lectores públicos usan caché y
reintentos limitados. La selección revisada requiere motivo, evidencia y revisor,
y los cambios invalidan revisiones dependientes. Las escrituras de corpus y
manifiestos son atómicas y el registro SQLite es transaccional.

El ejecutor de corpus guardados organiza evidencia existente; no simula nuevas
descargas ni revisión humana. Títulos, resúmenes y fragmentos se distinguen, y la
cobertura de búsqueda requiere un denominador independiente. La especificación,
pseudocódigo y comandos están en `ARQUITECTURA_REGISTROS_V2.md`.
