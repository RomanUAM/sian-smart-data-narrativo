# Guía metodológica del sistema local de análisis narrativo

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
- cuota máxima por año y tipo de fuente.
- mínimos obligatorios para capas sociales: por defecto 50 noticias y 50
  registros de foros/conversaciones por año cuando se corren esas capas.

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

## Corrida secuencial

La recolección publicable se ejecuta linealmente:

```text
para cada año:
  para cada mes:
    para cada capa pública seleccionada:
      tomar una muestra reproducible de N términos/rubros
      para cada término muestreado:
        construir consulta corta
        buscar índices
        revisar permisos de extracción
        descargar texto permitido o registrar señal parcial
        limpiar texto
        clasificar fuente
        guardar JSON incremental
        si la cuota año/tipo ya se cumplió, saltar pasos restantes
```

La unidad de recuperación ya no es “todos los sinónimos juntos”, sino un término
por vez. Además, en noticias, foros, instituciones y reportes la corrida no usa
todos los términos cada mes: toma una muestra aleatoria reproducible, por defecto
ocho términos por mes y capa. Esto reduce saturación de índices públicos,
disminuye sesgo por orden fijo, permite saber qué término recuperó cada documento
y evita mezclar sentidos distintos del tópico. Reddit se usa como fuente pública
opcional y tardía; no debe ser la ruta principal para construir conversación
social.

Los artículos científicos se tratan de forma anual, no mensual, porque OpenAlex
y Crossref recuperan obras por año y repetir la búsqueda cada mes duplicaría
registros sin aportar nueva evidencia temporal fina.

Capas disponibles:

- noticias;
- foros/conversaciones públicas;
- gobierno/instituciones;
- artículos científicos + PDFs cuando exista URL abierta;
- reportes/otros.

Los botones por capa aplican una regla de aceptación: `Noticias` sólo guarda
registros `news`; `Foros/conversaciones` sólo guarda registros `forum`;
`Gobierno/instituciones` sólo guarda `institutional_report`. Esto evita que
artículos científicos o fuentes no sociales llenen la cuota. Si no se alcanza
el mínimo anual configurado, el sistema reporta `coverage_gap` y la muestra
debe leerse como insuficiente para narrativa social amplia.

La araña mezclada conserva un tablero de balance antes y durante la corrida:
por cada año se muestran tipos objetivo, mínimo deseado y máximo anual. Cada
registro aceptado actualiza un contador tipo/año (`news 17/100`,
`forum 8/100`). Al cierre de cada mes se reporta `balance_status` separando
mínimo y máximo (`news 19/min 50 · max 100`). La categoría
`other` se conserva para auditoría, pero no debe usarse como objetivo de balance
social porque mezcla casos dudosos.

Si la corrida mezclada incluye artículos científicos, la ejecución se estratifica
automáticamente: primero se consulta OpenAlex/Crossref por año y después se
recorren las capas mensuales de prensa, foros e instituciones. Así la ausencia
de artículos aparece pronto como brecha real de recuperación y no como un cero
temporal causado por el orden del pipeline.

La capa `reportes/otros` todavía debe leerse con cautela: actualmente funciona
como búsqueda general que después puede clasificarse como reporte u otro tipo
cuando la evidencia lo indique. No equivale todavía a un índice especializado de
reportes institucionales.

Esto permite saber qué fuente, año y rubro ya terminaron y qué parte quedó
vacía o falló.

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

Cada corrida desde la app guarda un manifiesto local inicial:
`run_manifest.json`. Cuando existe corrida secuencial, también guarda
`query_plan.json` con el plan exacto de términos, meses, capas y semilla. Esto
permite auditar qué se intentó aunque la recolección se detenga. Para una
publicación estrictamente reproducible conviene añadir después un hash final del
corpus resultante y una auditoría manual de una muestra por fuente.

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
