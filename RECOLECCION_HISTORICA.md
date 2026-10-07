# Recolección histórica recuperable de SIAN

Versión de ejecución 3. Fecha de revisión 7 de octubre de 2026. El contrato de registros continúa en versión 2.

SIAN construye una base común con documentos de distintas fuentes, conserva su procedencia y muestra lo que pudo recuperar. La meta de 200 documentos por año significa 200 documentos únicos seleccionados entre todas las capas. Las etiquetas temáticas no multiplican esa meta. Tener 200 registros no demuestra representatividad social ni permite concluir que las voces ausentes no existen.

## Unidad y criterios de selección

La unidad es el documento, identificado por DOI cuando existe o por URL canónica. Cada documento conserva versiones de texto, recuperaciones y estados de evidencia. Autor, publicación y fuente se buscan; una búsqueda puede terminar sin encontrarlos. Una ausencia de autor no impide por sí sola incluir un documento en la muestra temporal.

El año contado procede exclusivamente de publicación explícita y válida. Publicación, actualización, consulta y detección por un índice permanecen separadas. El año solicitado a un buscador nunca rellena una fecha ausente. Una fecha anual puede contribuir al total anual, pero no aporta a la distribución mensual. Las publicaciones posteriores al día de ejecución no cuentan. El año corriente se identifica como periodo incompleto.

La selección exige texto de al menos el umbral configurado, estado de recuperación `ok` u `ok_partial`, pertinencia al tema y publicación dentro de los años solicitados. Un fragmento suficiente puede contar como evidencia parcial; no se presenta como texto completo. Los registros cortos, sin fecha, contradictorios o fuera del intervalo se conservan con motivos de exclusión de la cuota. Las exclusiones geográficas y léxicas del lector se registran en el avance antes de llegar al corpus retenido.

Primero se fusionan DOI y URL mediante `corpus_contract.py`, conservando conflictos y procedencias. Después, un hash del texto sustantivo normalizado detecta copias exactas entre URLs distintas: se retienen ambas, se marca `duplicate_of` y una sola cuenta. La coincidencia de títulos no basta para eliminar documentos. La similitud semántica y las reproducciones con cambios menores requieren revisión; todavía no hay deduplicación semántica validada.

`collection_assessment` contiene `eligible`, `selected`, `reason`, `duplicate_of` y versión de política. `collection_rubrics` contiene etiquetas temáticas; la representación anterior `narrative_rubrics` se conserva para compatibilidad. La revisión humana del contrato v2 y la selección operativa de cuota son decisiones distintas. Las etiquetas automáticas son hipótesis léxicas, no diagnósticos sociológicos.

## Plan de búsqueda por capacidad

| Fuente | Uso histórico | Fecha que debe verificarse |
|---|---|---|
| GDELT DOC 2 | Ventanas desde enero de 2017; consultas mensuales | La detección por GDELT no equivale a publicación |
| Google News RSS | Complemento de cobertura histórica débil | Publicación del RSS o de la página |
| Foros y RSS públicos | Cobertura parcial y dependiente del proveedor | Publicación del mensaje o página |
| OpenAlex Crossref Redalyc | Consultas anuales a repositorios e índices | Metadatos bibliográficos explícitos |
| URLs semilla | Fuentes curadas disponibles antes de los índices | Metadatos de la página o fecha explícitamente verificada |
| Sitemaps configurados | Descubrimiento por fuente con cursor recuperable | Publicación de la página; nunca `lastmod` |

El plan intercalará meses, años y capas. Los motores académicos se consultan por año, sin repetir la misma consulta doce veces. Las consultas públicas mantienen un término central y variantes temáticas acotadas; la rotación opcional usa una semilla reproducible. No se consultan meses futuros. GDELT no se solicita para 2016. Su pausa se comparte entre noticias, foros e instituciones dentro de la ejecución.

Los sitemaps se proporcionan como URLs HTTPS. Cada tarea examina como máximo cinco mapas y entrega hasta mil URLs pertinentes por tramo, conserva mapas pendientes y URLs aún no procesadas, y respeta robots. Los errores mantienen la fuente pendiente para una reanudación explícita. La búsqueda en URL es un filtro de descubrimiento que puede omitir páginas con rutas genéricas. Una fuente que no ofrece archivo o sitemap útil requiere otra estrategia; no se declara cobertura exhaustiva.

El ejemplo `examples/tatuaje_2016_actualidad.json` incluye todos los rubros disponibles, cinco capas y 200 documentos por año. Al 7 de octubre de 2026 produce 573 tareas. Ese número es un plan, no 573 documentos ni un resultado empírico. Para estudiar una región hay que configurar términos y restricciones geográficas; el ejemplo usa alcance global y sus semillas no equilibran países.

## Coordinador y almacenamiento

| Módulo | Responsabilidad |
|---|---|
| `historical_sources.py` | Capacidades de fuentes, planificación y cursor de sitemaps |
| `source_control.py` | Pausas persistentes y caché de consultas GDELT |
| `source_adapters.py` | Caché y reintentos acotados de los demás índices |
| `collection_jobs.py` | Tareas, documentos, eventos y exportación transaccional |
| `collection_runner.py` | Proceso de ejecución independiente de Streamlit |
| `collection_policy.py` | Pertinencia, fecha, duplicados, cuota y cobertura |
| `process_lock.py` | Exclusión mutua de trabajadores en Linux macOS y Windows |
| `job_backup.py` | Respaldos privados opcionales en S3 y recuperación |
| `streamlit_app.py` | Configuración, recuperación, conjugación y presentación |

Cada ejecución recibe un identificador aleatorio. SQLite guarda configuración, tareas, documentos, eventos, pausas y consultas compartidas. El registro se confirma después de cada documento mediante `on_record`, antes de terminar una tarea. Los JSON y el manifiesto se reemplazan atómicamente. Un bloqueo de proceso impide que dos trabajadores ejecuten la misma base a la vez. Recargar o cerrar el navegador no cancela el proceso.

Una interrupción del proceso o del servidor deja registros confirmados y tareas recuperables. Al reanudar, las tareas en curso vuelven a pendientes; las completadas se omiten. Las tareas fallidas o diferidas se vuelven a intentar una vez por reanudación. La misma identidad vuelve a fusionarse y no incrementa el total artificialmente. Una consulta ya completada puede aprovechar la caché. Los fallos no se convierten en búsquedas vacías exitosas.

Un HTTP 429 establece una pausa persistente que respeta `Retry-After`, con espera mínima de 60 segundos y máxima de un día. Durante esa pausa se avanza en otros motores y la tarea queda diferida. No se reinicia la pausa en cada rubro ni se insiste en un bucle continuo. El resto de errores conserva su estado; la persona decide cuándo reanudar y ampliar fuentes.

| Estado de ejecución | Significado |
|---|---|
| `ready` | Plan guardado sin iniciar |
| `running` | Trabajador activo |
| `paused` | Parada solicitada o respaldo restaurado |
| `interrupted` | Terminó el proceso sin cierre normal |
| `waiting_sources` | Quedan tareas fallidas o diferidas |
| `finished_with_gaps` | Tareas terminadas y cuota incompleta |
| `target_met` | Todas las cuotas anuales se alcanzaron |

Llegar a la cuota puede omitir tareas de ese año. Por eso esta ejecución produce una muestra de disponibilidad, no una serie temporal de intensidad pública. Para comparar meses o estimar tendencias se necesita un diseño de muestreo independiente y denominadores comparables. Cambiar metas o diseño se hace creando una nueva ejecución y conjugando bases con configuración explícita.

## Uso de la página

1. Configurar tema, región, años, texto mínimo y meta total anual.
2. Seleccionar todos los rubros y las capas deseadas para la corrida histórica.
3. Agregar sitemaps históricos cuando se disponga de ellos; las semillas curadas son un complemento.
4. Ejecutar la acción. Consultar la cobertura anual y los motivos de exclusión.
5. Conservar el código privado y descargar **Descargar ejecución completa ZIP**.
6. Para continuar en el mismo servidor, usar **Recuperar ejecución** y **Reanudar tareas pendientes**.
7. Si el servidor perdió su disco, importar el ZIP completo y reanudar. La restauración genera un nuevo código y mantiene documentos, plan y cursor.
8. Para conjugar corridas, elegir **Fusionar bases por fuente** e introducir sus códigos, uno por línea. La nueva base mantiene procedencias y cuenta identidades únicas.

El ZIP contiene `job.sqlite3`, corpus JSON y JSONL, `coverage.json`, `coverage_annual.csv`, manifiesto y plan. La copia SQLite es consistente aun durante una ejecución. No contiene credenciales ni descarga todos los PDF o cachés HTML auxiliares: el texto recuperado y su procedencia permanecen en los registros. El respaldo de corpus anterior conserva documentos, pero el respaldo completo es el que permite continuar tareas.

Los ZIP antiguos con manifiesto se migran al nuevo plan y conservan los documentos recuperados. No se interpreta que las consultas anteriores, vacías o limitadas, hayan cumplido la cuota. Las rutas del servidor antiguo no se ejecutan como lecturas de archivos del nuevo servidor. Importar JSON o JSONL crea una ejecución guardada y mantiene la posibilidad de exportarla.

## Uso por comandos

Desde la raíz del repositorio:

```bash
python -m pip install -r requirements.txt
python scripts/collect_historical.py --config examples/tatuaje_2016_actualidad.json --plan-only
python scripts/collect_historical.py --resume CODIGO_DE_EJECUCION
python scripts/collect_historical.py --resume CODIGO_DE_EJECUCION --plan-only --export respaldo.zip
python scripts/collect_historical.py --restore respaldo.zip --plan-only
python -m unittest discover -s tests -q
python -m streamlit run streamlit_app.py
```

Eliminar `--plan-only` en la creación inicia la recolección real. La restauración se deja pausada con `--plan-only`; sin esa opción ejecuta las tareas. Ctrl C conserva el avance y solicita una parada. Los comandos y la página usan el mismo coordinador y la misma política.

## Persistencia fuera de la sesión

`SIAN_DATA_DIR` define la raíz de las ejecuciones. Debe apuntar a un volumen persistente para sobrevivir al reemplazo del servidor. El directorio predeterminado `.sian_jobs` es local y se excluye de Git. Un código recupera una ejecución sólo mientras exista ese disco, salvo que se haya configurado respaldo externo.

Opcionalmente, configurar `SIAN_BACKUP_BUCKET`, `SIAN_BACKUP_PREFIX` y credenciales AWS en el entorno del servidor, con permisos privados de lectura y escritura para ese prefijo. El SDK boto3 cifra los objetos en el servidor con AES256. Después de cada tarea y al cerrar la ejecución se intenta un respaldo completo. Un fallo de respaldo se muestra como fallo y no detiene ni simula éxito de la recolección. Si el disco se pierde, el mismo código puede recuperar el último checkpoint externo. No se crea ni publica un bucket automáticamente.

Los secretos no se escriben en el código, el corpus ni el ZIP. El identificador sirve como capacidad de acceso a la ejecución: debe conservarse privado. El sistema no implementa cuentas, equipos ni auditoría de accesos por usuario. El servidor puede perder trabajo posterior al último respaldo confirmado. Antes de depender de S3 conviene probar una restauración real en la infraestructura elegida.

## Cobertura y análisis social

`coverage.json` informa meta, seleccionados y brecha por año; distribución por fuente, rubro y mes; motivos de exclusión, copias y procedencias adicionales. Cada rubro puede coexistir con otros en el mismo documento. La suma de sus conteos no equivale al tamaño del corpus. Una publicación con precisión anual no se asigna artificialmente a enero.

Los datos permiten describir la muestra recuperada y construir hipótesis sobre encuadres, actores y relaciones. No justifican estimar opinión pública, prevalencia de tatuajes, efectos psicológicos, intenciones o causalidad social. Las matrices revisadas conservan ausencia explícita y dato faltante como estados diferentes. Las relaciones actor concepto postura requieren atribución y fragmento revisado, según `EVIDENCIA_Y_MODELOS.md`.

La cuota reduce una brecha operativa, no estima el total existente en internet. Para evaluar calidad científica deben revisarse pertinencia, errores de clasificación, cobertura geográfica, distribución de fuentes, variantes de texto y evidencia de las interpretaciones. Los registros sin fecha pueden aportar al análisis temático aunque se excluyan de comparaciones anuales.

## Verificación y alcance

Las pruebas incluyen publicación frente a año solicitado; fechas faltantes; textos cortos; pertinencia; copias exactas; cuota entre fuentes; capacidades históricas; corte al presente; cursor de sitemaps; pausa compartida; confirmación por documento; restauración y reanudación; fallos recuperables; conjugación con procedencias. Los lectores se prueban con resultados controlados para reproducir errores sin depender de proveedores cambiantes.

Además se verifica la interfaz con Streamlit AppTest y se restaura un respaldo real anterior. Estas comprobaciones no prueban alcanzar 200 documentos en cada año, disponibilidad de todo internet, restauración S3 en producción o validez de inferencias sociales. Las fuentes externas pueden entregar cero resultados y el sistema debe mostrar esa brecha.

Fuentes técnicas primarias: actualización oficial GDELT DOC de 2018 sobre búsqueda desde enero de 2017, https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/ ; protocolo de sitemaps y definición de `lastmod`, https://www.sitemaps.org/protocol.html ; boto3 S3 `put_object`, https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html .
