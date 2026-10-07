# SIAN: evidencia disponible, datos faltantes y modelos descriptivos

Versión metodológica: 6 de octubre de 2026. Esta política sustituye cualquier
instrucción anterior que permita confundir año de búsqueda con publicación,
enlace PDF con texto completo, coocurrencia con relación validada o falta de
datos con ausencia del fenómeno. Los informes históricos conservan su alcance.

## Qué cambió

La recolección busca autoría y fechas en metadatos HTML etiquetados y JSON-LD.
OpenAlex, Crossref y Redalyc conservan la autoría disponible en sus registros.
La publicación, actualización y consulta son campos distintos. La búsqueda
no garantiza recuperar ninguno de ellos. No se inventan autores ni fechas.
Las firmas visibles sin metadatos etiquetados requieren revisión manual.
La dirección institucional o el dominio no determinan autoría, territorio del
acontecimiento ni identidad editorial.

El núcleo `evidence_model.py` se integra con la carga, enriquecimiento,
persistencia de la araña, manifiesto y tablero Streamlit. El comando de auditoría
migra los JSON existentes a una salida independiente. No modifica el corpus de
entrada. `year` representa únicamente el año de publicación explícita utilizable;
`search_year` conserva el valor heredado para rastrear el diseño de búsqueda.
Los registros antiguos de procedencia temporal ambigua necesitan revisión.

## Estados por campo

| Estado de código | Significado | Uso |
|---|---|---|
| explicit | Encontrado explícitamente | Valor y evidencia disponibles; no garantiza veracidad de la afirmación |
| inferred | Inferido | Hipótesis identificada; fuera de análisis que exigen dato explícito |
| not_found | Buscado y no encontrado | Solo describe la búsqueda realizada |
| not_evaluable | No evaluable | Acceso, formato o procedencia insuficiente; incluye búsqueda no documentada en registros antiguos |
| not_applicable | No aplica | Decisión justificada según documento y pregunta |
| conflicting | Evidencias contradictorias | Se conservan candidatos; se necesita revisión |

Cada celda contiene `value`, `state`, `evidence` y `method`. Las fechas conservan
precisión de año, mes o día. No se completa día/mes. Los formatos no ISO deben
normalizarse con evidencia o revisión; una fecha inválida queda fuera de la serie.
El año encontrado en el cuerpo o en una URL no se convierte automáticamente en
fecha de publicación. La fecha de detección de GDELT tampoco es publicación.

## Requisitos por análisis

| Análisis | Requisito | Alcance |
|---|---|---|
| Temático | Texto recuperado utilizable | Fragmentos incluidos, con cobertura parcial visible |
| Por fuente | Texto y fuente editorial identificada explícitamente | Diferencias entre documentos cubiertos |
| Temporal | Texto y publicación explícita de precisión suficiente | Subconjunto fechado; no representa automáticamente todo el corpus |
| Afirmaciones | Concepto, afirmación, cita literal y revisión validated | Interpretación humana documentada |
| Actor–concepto–postura | Afirmación revisada, emisor y respaldo textual de atribución | Posiciones expresadas; emisor no equivale al autor de la página |
| Narrativa | Descripción revisada y fragmento de respaldo | Lectura interpretativa documentada; el sistema no prueba por sí mismo que exista una narrativa |
| Recepción | Descripción revisada de recepción y evidencia recuperada | Debe revisarse sustantivamente que sean respuestas al mensaje, no solo contenido del mensaje |

El tablero presenta utilizables/total, motivos de exclusión y distribución de
cobertura por tipo de fuente. La cobertura mide disponibilidad, no
representatividad o suficiencia estadística. Un documento sin autor o fecha
sigue disponible para los análisis que no requieren esos campos.

## Modelos matemáticos implementados

1. Matriz documento–concepto: 1 cuando existe una afirmación revisada del concepto;
   0 solo cuando `reviewed_concepts` declara que se revisó ese concepto y no se
   registró presencia; null cuando no se sabe. Una coincidencia léxica nunca
   sustituye automáticamente este registro.
2. Fuente–concepto: proporción de documentos con el concepto sobre documentos
   efectivamente revisados para ese concepto y con fuente explícita. Se exportan
   numerador y denominador. Conceptos distintos pueden tener denominadores distintos.
3. Actor–concepto–postura: conteo de afirmaciones revisadas por actor, concepto y
   postura. Apoyo y rechazo permanecen separados; no se cancelan. La ambivalencia
   se conserva. La postura indeterminada no participa en esta red.
4. Relaciones dirigidas: source, target y type con documento y cita de respaldo.
   Son relaciones afirmadas o interpretadas en el texto; una causa atribuida no
   es un efecto causal estimado.
5. Conteos temporales: documentos con conceptos revisados y publicación explícita,
   agregados a la precisión solicitada. El resultado exporta la cobertura de la
   intersección revisado–fechado, además de la disponibilidad temporal general.

No se implementan inferencias poblacionales, pruebas de causalidad, difusión,
alianzas o efectos psicológicos. Tampoco imputación de valores faltantes.
Los resultados heurísticos anteriores continúan como candidatos exploratorios.
Los documentos pueden depender de una misma institución o acontecimiento: los
conteos no son observaciones independientes para pruebas inferenciales.

## Algoritmos en pseudocódigo

```text
PARA cada documento:
    conservar contenido original y procedencia
    buscar metadatos etiquetados cuando el acceso lo permita
    PARA cada campo:
        conservar valor, evidencia, método y estado
        si hay conflicto: conservar candidatos sin elegir arbitrariamente
    separar publicación, actualización, consulta y año de búsqueda
    no usar año de búsqueda o detección del índice como publicación
    PARA cada análisis:
        comprobar sus requisitos con evidencia disponible
        registrar inclusión o motivo de exclusión
    mantener documento para otros análisis si faltan datos opcionales
```

```text
PARA cada revisión:
    buscar document_id estable; rechazar ID desconocido o duplicado
    comprobar estado de metadatos y precisión de fechas
    comprobar cita literal en texto recuperado
    conservar interpretación revisada sin confundirla con verdad factual
PARA cada concepto y documento revisado:
    si hay evidencia validada: X = 1
    si la revisión declara cobertura de ese concepto y no presencia: X = 0
    de otro modo: X = null
AGRUPAR posiciones por actor, concepto y postura sin cancelar signos
CONTAR por fuente usando solo denominadores revisados
CONTAR por periodo usando intersección revisado y fechado
EXPORTAR matrices, relaciones, cobertura y limitaciones
```

## Uso local y conservación de revisiones

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
python3 scripts/audit_evidence.py news_output --output audit_output --precision year
python3 scripts/audit_evidence.py news_output --output reviewed_output --reviews revisiones.json
python3 -m unittest discover -s tests -v
```

La interfaz permite descargar una plantilla, importar revisiones y descargar el
corpus con evidencia y modelos. La revisión aplicada en la interfaz es temporal
hasta descargar el corpus; no modifica silenciosamente el archivo de entrada.
La CLI produce JSON/JSONL migrados, auditoría CSV, cobertura JSON y matrices CSV.
Los IDs estables permiten conservar la revisión aunque se corrija la fecha.

Ejemplo de revisión, con texto sintético exclusivamente demostrativo:

```json
[
  {
    "document_id": "copiar el identificador de review_template.json",
    "claims": [
      {
        "concept": "empleo",
        "statement": "La formación mejora el empleo",
        "speaker": "Ana",
        "speaker_evidence": "Ana",
        "stance": "support",
        "quote": "Ana sostiene que la formación mejora el empleo.",
        "review_status": "validated",
        "relations": [
          {"source": "formación", "target": "empleo", "type": "consecuencia_atribuida"}
        ]
      }
    ],
    "reviewed_concepts": ["empleo"]
  }
]
```

La cita debe existir literalmente en el texto recuperado. El sistema verifica
consistencia del registro, no reemplaza el juicio sociológico o psicológico.
El código no estima confianza numérica ni convierte revisión humana en certeza.

## Validación y límites pendientes

Las pruebas verifican fechas incompletas/contradictorias, bloqueos, migración sin
mutación, IDs, citas inexistentes, denominadores, null frente a cero, conservación
de apoyo/rechazo y rutas bibliográficas. Falta validar exhaustividad de extracción
con un corpus externo y acuerdos entre codificadores. La limpieza heredada sigue
siendo heurística: los textos deben revisarse antes de interpretar relaciones.
Los modelos estadísticos multivariados, sensibilidad por institución/evento y
contraste de codificadores requieren diseño y datos adicionales; no se presentan
como implementados en esta actualización.

## Contrato compartido de corpus y prueba integral

La revisión integral de octubre centraliza identidad y fusión en `corpus_contract.py`.
Interfaz, ejecutor de planes, fusión por fuente y reconstrucción conservan evidencia y
procedencia, sin fusionar documentos distintos por su título. Las URLs conservan
parámetros identificadores. Un conflicto persiste; distintas fechas de consulta son
historial de recuperación. El texto recleaned renueva su evidencia.

Las señales estructurales son candidatos. La no detección en fragmentos no significa
que una fuente ignora un tema. Sin fecha no se establece orden temporal, y una fecha
anual no permite ordenar publicaciones dentro de ese año. Pesos nulos permanecen
nulos; el denominador de cálculo no altera el peso observado.

El exportador `scripts/export_corpus_database.py` entrega SQLite, Excel, CSV y JSON;
las tablas de modelos sin revisión permanecen vacías. El caso de tatuaje produjo
891 registros exploratorios con contenido parcial y 15 referencias bibliográficas
revisadas, sin atribuir posturas ni recepción. Véase `AUDITORIA_INTEGRAL_2026-10-06.md`
para defectos, alcance de pruebas y límites de esta evaluación.


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
