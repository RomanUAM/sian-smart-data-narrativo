# SIAN: arquitectura de corpus y registros v2

La ejecución histórica versión 3 está implementada en el coordinador independiente y documentada en [RECOLECCION_HISTORICA.md](RECOLECCION_HISTORICA.md). Mantiene el contrato de evidencia v2, añade tareas transaccionales, cuota total anual, control compartido de límites, archivo recuperable y cobertura por motivos. Esta especificación sustituye la ejecución ligada a una sesión y las cuotas automáticas por tipo; no convierte los informes históricos en nuevas mediciones.

Actualización del 6 de octubre de 2026. Implementación posterior a la auditoría integral, con migración conservadora del piloto de tatuaje México 2016–2026.

## Qué cambia

El sistema separa el contrato de datos, identidad y fusión, almacenamiento, adaptación de fuentes y ejecución por etapas. Los lectores y analizadores existentes se conservan como motores compatibles. No se ha reescrito toda la lógica heurística ni se presenta como científicamente validada.

| Módulo | Responsabilidad |
|---|---|
| `record_schema.py` | Esquema v2, validación, IDs, contenido, fechas, geografía e invalidación de revisiones |
| `evidence_model.py` | Evidencia por campo y requisitos de cada análisis |
| `corpus_contract.py` | Identidad compartida y fusión con versiones/procedencias conservadas |
| `corpus_storage.py` | Escrituras atómicas y registro SQLite transaccional |
| `source_adapters.py` | Contrato de resultados de fuente, caché y reintentos limitados |
| `corpus_pipeline.py` | Etapas, puntos de control, cuarentena y selección revisada |
| `streamlit_app.py` | Presentación, preparación del corpus y entrada de revisiones |

## Documento, versión y recuperación

`document_id` conserva la identidad histórica para no romper revisiones. `canonical_document_id` corresponde a la clave DOI/URL disponible; los enlaces intermediarios todavía necesitan resolución con evidencia. `version_id` cambia al cambiar contenido o metadatos, pero no por consultar el mismo documento de nuevo. `retrieval_id` distingue fuente, consulta, momento y versión. Si falta el momento original, se conserva ausente: no se inventa.

El registro tiene listas `versions`, `retrievals` y `record_history`. El registro SQLite usa tablas distintas para documentos, versiones, recuperaciones y relaciones. Las versiones conservan su evidencia; las recuperaciones conservan resultado y error. El historial registra modificaciones e invalidación de interpretaciones. Una base bibliográfica verificada no se transforma automáticamente en un documento incluido para interpretación social.

Cada celda incorpora procedencia: URL, lector, momento observado y referencia de extracción. En registros antiguos, la ubicación se etiqueta como referencia heredada; no se inventan posiciones de caracteres ni número de página. El esquema JSON está en `examples/record_schema_v2.schema.json` y la validación de dominio añade condiciones de inclusión/exclusión y autoría.

## Estados y suficiencia

Selección: `candidate`, `pending`, `included`, `excluded`. Una inclusión o exclusión requiere motivo, evidencia y revisor, además de corresponder a la versión actual. Los excluidos no entran en la elegibilidad analítica. Cambiar el registro invalida la selección concluida y las interpretaciones validadas; la evidencia anterior permanece en el historial.

Contenido: título, resumen, fragmento, texto completo o ninguno. Texto completo sólo se declara cuando existe evidencia explícita de esa extensión. No se deduce de `status=ok` ni de un enlace PDF. Un título puede servir para descubrimiento bibliográfico, pero no acredita suficiencia argumentativa.

Geografía: tema, editor y participantes. Publicación, actualización, consulta, acontecimiento y periodo estudiado son campos separados. Lugar o periodo de búsqueda no completan esos campos.

## Etapas y reanudación

Las seis etapas son descubrimiento, recuperación, extracción, selección, revisión y análisis. El ejecutor de corpus guardados migra y organiza la evidencia ya recuperada; sus etapas de recuperación y extracción **no hacen nuevas descargas**. La disponibilidad real permanece parcial, fallida o desconocida por registro. La revisión sólo cambia cuando se aporta una decisión; no se simulan revisores humanos.

Cada etapa conserva hash de entrada/configuración y firma del código, resultado, hash de salida y estado. Sólo se reutiliza un resultado terminado cuya integridad coincide. Un punto de control corrupto se recalcula. Un fallo no se transforma en búsqueda vacía. La escritura del resultado precede a la confirmación del manifiesto.

Los lectores nativos Google News RSS, Reddit, OpenAlex, Crossref y Redalyc usan el adaptador de caché. Los resultados vacíos se distinguen de fallos; los fallos no se reutilizan como resultados vacíos. Máximo dos intentos por defecto, como máximo tres configurables; sólo se reintentan errores transitorios. La caché dura una hora por defecto y se puede configurar con `SIAN_CACHE_DIR` y `SIAN_CACHE_TTL`. Los cambios en formato o errores de programación no se encubren mediante reintentos indefinidos. La paginación Redalyc del piloto usa también esta infraestructura.

La caché es por consulta pública, no un archivo histórico completo ni un mecanismo para saltar permisos de acceso. Se conserva la validación HTTPS.

## Persistencia

Corpus, planes y manifiestos se sustituyen con archivos temporales únicos y reemplazo atómico. El registro SQLite confirma o revierte cada lote completo. JSONL incremental permanece como bitácora; la instantánea final se escribe por separado. En la exportación se construye una base SQLite temporal y se conserva la anterior hasta completar la nueva. El manifiesto de exportación indica `running` o `completed`: los distintos formatos no constituyen una sola transacción de sistema de archivos.

La cuarentena conserva registros inválidos y motivos. El ejecutor no convierte un manifiesto administrativo en documento. Un esquema futuro desconocido se rechaza, en lugar de degradarlo silenciosamente.

## Pseudocódigo

```text
recibir registros y configuración
para cada registro:
    validar forma; migrar conservando IDs históricos
    si inválido: conservar en cuarentena con motivo
    registrar evidencia, versión y recuperación
para cada etapa:
    calcular hash de entrada y configuración
    si punto terminado e íntegro: reutilizar
    de otro modo: ejecutar, guardar y confirmar estado
aplicar selección únicamente a la versión revisada
conservar versiones, conflictos, relaciones y procedencias
calcular disponibilidad por contenido y requisitos analíticos
confirmar lote en registro SQLite
escribir corpus y manifiesto de finalización
```

## Verificación y migración del caso

Pasan **74 pruebas**: las 58 anteriores y 16 nuevas. Se prueban migración idempotente, preservación de IDs, versiones frente a consultas, revisión invalidada, campos no imputados, selección por versión, reanudación, punto corrupto, caché, fallos, reintentos, reemplazo atómico y rollback transaccional. Se incluye una muestra de Atom real guardada, reducida a metadatos. El chequeo estático y la compilación pasan; Streamlit abre con registros v2 sin excepciones.

Los **891 registros** anteriores conservan sus IDs. Se distinguen **790 títulos, 51 resúmenes y 50 fragmentos**. Todos quedan pendientes de revisión de contenido/selección; los 15 con bibliografía revisada conservan esa nota. El registro y la exportación pasan integridad SQLite y no presentan violaciones de claves foráneas. Una segunda ejecución reutiliza las seis etapas y no crea registros nuevos.

La cobertura de búsqueda permanece desconocida cuando no existe denominador definido. El reporte separa conteos de resultados, estados de recuperación, tipos de contenido y elegibilidad analítica. No ofrece representatividad ni inferencia social por esos conteos. El conjunto migrado conserva las limitaciones de la extracción original; no se ha hecho una nueva búsqueda de tatuajes.

## Uso

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 scripts/run_corpus_pipeline.py corpus_original.json --output corpus_v2
# Repetir el mismo comando reutiliza los puntos de control íntegros.
python3 scripts/export_corpus_database.py corpus_v2/news_records.json --output corpus_v2
python3 scripts/run_corpus_pipeline.py corpus_original.json --output corpus_revisado --selection-reviews decisiones.json
```

En Streamlit, el panel de evidencia permite preparar un corpus por etapas, inspeccionar contenido/selección y descargar una plantilla de selección con documento y versión. Las tablas vacías de posturas o recepción siguen vacías hasta contar con evidencia revisada.
