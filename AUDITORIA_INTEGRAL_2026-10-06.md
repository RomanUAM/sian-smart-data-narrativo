# SIAN: auditoría del flujo completo y prueba de tatuaje 2016–2026

Fecha de revisión: 6 de octubre de 2026. Alcance del caso: México; 2026 parcial hasta la consulta. Versión revisada: rama local `mejora/evidencia-cobertura`, posterior a `08a0c39`.

## Dictamen

El sistema puede producir bases por fuente y conjugarlas en un corpus con información trazable. La prueba produjo **891 registros**: 775 de prensa, 50 de foros, 58 de artículos, 7 institucionales y 1 de divulgación. Se entregan SQLite, Excel, CSV y JSON nativo de SIAN. Esta es una base exploratoria de candidatos y referencias, no un corpus exhaustivo ni una medición representativa de México.

La revisión pasó de correcciones aisladas a una regla compartida de identidad y fusión. Se comprobaron todos los archivos ejecutables identificados: 26 archivos, 17 315 líneas y 481 funciones, incluyendo pruebas y generadores de documentos. El inventario contiene sus hashes. Se efectuó comprobación estática de sintaxis y nombres indefinidos, revisión del recorrido de datos e integración de los puntos de entrada. **Esto no equivale a demostrar la corrección de cada algoritmo en todas las entradas posibles ni a validar científicamente los clasificadores.**

## Fallos y cambios

| Componente | Fallo observado | Corrección |
|---|---|---|
| Identidad | URL sin parámetros fusionaba artículos diferentes; títulos similares podían eliminar documentos distintos | Identidad DOI/URL; se conservan parámetros identificadores y mayúsculas de ruta; sólo se eliminan parámetros de seguimiento |
| Integración | Interfaz, ejecutor y fusionador conservaban copias diferentes | Módulo compartido `corpus_contract.py`, usado por fusión, análisis, reconstrucción y ejecutor |
| Lectura de bases | Preferencia JSONL omitía JSON aun sin archivo JSONL existente | Selección de hermanos que realmente existen; prueba de integración con dos capas JSON |
| Fusión | Primera copia retenida perdía texto, autoría o conflictos | Conservación de procedencias, variantes de texto y contradicciones; precisión de fecha compatible no crea conflicto |
| Persistencia | Manifiestos podían ingresar como documentos | Validación de forma del registro y exclusión de estructuras administrativas |
| Carga | Directorio con sólo base consolidada no se recuperaba | Descubrimiento de archivos fusionados y secuenciales antes del escaneo de registros |
| Fuentes | Reddit entregaba Atom y se leía como RSS | Lectura Atom/RSS; publicación y actualización separadas |
| Fechas | Mezcla UTC consciente e ingenua; fecha RFC no normalizada; tolerancia de un día fuera de ventana | Comparación UTC uniforme, normalización y límite exacto |
| Semillas | Enero 1 inventado desde año; México asignado automáticamente; registros sin fecha descartados | Precisión anual conservada, país ausente no imputado, semillas incompletas preservadas |
| Limpieza | Texto cambiado con evidencia antigua y clasificación perdida | Renovación de evidencia textual y conservación de clasificación de origen |
| Matemática | Peso de cero convertido en uno; desempate no determinista | Cero conservado; pesos negativos/no finitos rechazados; orden de candidatos estable |
| Interpretación | Falta de detección convertida en “IGNORA_A”; marcos sin fecha usados para orden temporal | Señales explícitamente candidatas; falta de datos no equivale a ausencia; exclusión de orden sin fecha y dentro del mismo año |
| HTTPS | Sólo certifi ignoraba certificados de confianza del entorno; alternativa sin verificación | Unión de certificados del sistema y certifi, manteniendo validación TLS |
| Exportación | Faltaba entrega relacional revisable | Exportador reutilizable SQLite/Excel/CSV/JSON con integridad, claves foráneas y tablas de modelos vacías cuando falta revisión |

## Validación realizada

- 58 pruebas pasan: 42 previas y 16 de integración/contrato nuevas. Incluyen ausencia de metadatos, conflicto, precisión, Atom, identidad de artículos Redalyc, fusión repetida, limpieza, carga y exportación relacional.
- Compilación de todos los Python y verificación de sintaxis de todos los scripts shell identificados: sin errores.
- Chequeo estático de errores de sintaxis y nombres indefinidos: sin errores.
- Streamlit inicia sin excepciones; prueba adicional con registros fechados y sin fecha: sin excepciones.
- SQLite: `integrity_check = ok`, sin violaciones de claves foráneas; conteos concordantes con JSON y Excel.
- Los modelos de cobertura y eliminación de nodos se prueban en casos pequeños, incluido peso cero. Las heurísticas no ofrecen garantía de óptimo global ni sus pesos equivalen a confiabilidad científica calibrada.

## Protocolo y resultados de recuperación

La consulta ancla de prensa fue `(tatuaje OR tatuajes OR tattoo) (México OR Mexico)`, repetida por año con límite de 100 resultados. El lector nativo produjo 773 entradas fechadas en los once años. El límite se alcanzó en 2024: no es un total de publicaciones de ese año. Google News es un índice y puede devolver titulares poco pertinentes, réplicas o enlaces intermediarios; la fecha del feed es evidencia de publicación declarada por el índice y necesita contrastarse con el editor para investigaciones exigentes.

Reddit produjo 50 entradas con publicación declarada por Atom. Es un feed reciente, no un archivo histórico completo ni una muestra de opiniones mexicanas. Redalyc entregó tres páginas de 50 candidatos: 53 coincidían con el intervalo de publicación; la cuarta solicitud falló con HTTP 503. Se conserva el resultado parcial y su bitácora. El total de 1 862 declarado por la búsqueda no se interpreta como artículos pertinentes sobre tatuaje en México. Las pruebas de acceso a OpenAlex, Crossref y GDELT registraron tiempos de espera; no se simulan datos de esos servicios.

Se añadieron **15 referencias primarias** identificadas mediante recuperación web de metadatos visibles de editor/repositorio: 5 artículos, 7 institucionales, 2 periodísticas y 1 de divulgación. La incorporación manual está marcada y separada de la recuperación nativa. Son títulos y bibliografía; no se afirma haber descargado sus textos completos. Cada referencia conserva URL y nota sobre limitaciones. La fecha de investigación o de los acontecimientos no sustituye la publicación.

| Año | Registros consolidados |
|---:|---:|
| 2016 | 59 |
| 2017 | 55 |
| 2018 | 54 |
| 2019 | 75 |
| 2020 | 75 |
| 2021 | 74 |
| 2022 | 82 |
| 2023 | 93 |
| 2024 | 113 |
| 2025 | 105 |
| 2026 parcial | 106 |

Todos los 891 registros conservan fecha declarada con su precisión y procedencia. Hay autoría explícita en 112 y no encontrada en 779; en foros, la autoría es una cuenta pública, no identidad civil comprobada. Todo el contenido exportado es parcial: títulos o fragmentos de índice/feed. Hay 876 candidatos pendientes de comprobar pertinencia, contenido y/o geografía, y 15 referencias con bibliografía revisada. Una cobertura técnica del 100 % en fecha o texto no acredita validez temática del corpus ni comparación histórica representativa.

La fusión real reúne cinco capas y mantiene 5 346 celdas de información y 891 entradas de procedencia. En esta extracción no encontró duplicados exactos por DOI/URL. Los enlaces intermediarios de Google News pueden ocultar que una referencia manual y una entrada de prensa son el mismo trabajo. Por eso **891 no significa 891 trabajos independientes**. La similitud de título por sí sola tampoco autoriza eliminar una copia: queda como tarea de resolución con evidencia del editor.

## Qué se puede analizar y qué falta

Es viable inspeccionar bibliografía, años declarados, tipos de fuente, cobertura de recuperación, títulos y candidatos a conceptos. Los modelos de afirmaciones, postura de actores, recepción y relaciones validadas tienen cero registros elegibles. Sus tablas vacías son un resultado correcto, no datos negativos. Tampoco se deben convertir las frecuencias anuales recuperadas en evolución de aceptación del tatuaje.

Para el análisis sociológico y de psicología social se necesita recuperar fragmentos suficientes, comprobar contexto y geografía, distinguir voces citadas de firmas, revisar conceptos y atribuciones, identificar dependencias y republicaciones y observar recepción en una fuente que realmente la documente. El programa busca metadatos pero no garantiza encontrarlos. No se inventan autores, fechas, posturas, causalidad ni resultados inferenciales.

## Archivos y reproducción

- `scripts/collect_tattoo_pilot.py`: prueba acotada de lectores nativos, con bitácoras por año y motor.
- `scripts/merge_source_bases.py`: misma política de fusión usada por Streamlit.
- `scripts/export_corpus_database.py`: salida relacional y tabular reutilizable.
- Paquete de datos: capas originales, base consolidada, bitácoras, protocolo, referencias y cobertura.
- Paquete del sistema: fuente, pruebas, documentación, inventario y cambios locales. No se publicó una nueva versión remota.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/collect_tattoo_pilot.py tattoo_run
python3 scripts/merge_source_bases.py --base-output-dir tattoo_run
python3 scripts/export_corpus_database.py tattoo_run/news_records_merged.json --output tattoo_database
```

La reproducción de consultas en línea puede variar por cambios del índice, disponibilidad y límites. Las bases guardadas permiten reproducir la fusión y los conteos sin volver a consultar internet.
