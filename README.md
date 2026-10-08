# SIAN Sistema de Información y Análisis de Narrativas

SIAN significa **Sistema de Información y Análisis de Narrativas**. Reúne elementos proporcionados por el usuario y documentos públicos y organiza evidencia para analizar narrativas. Conserva procedencia, versiones, estados de autoría y fecha, y permite revisión humana de actores, conceptos, posturas y relaciones. Las señales automáticas son exploratorias: no demuestran opinión pública, intenciones ni causalidad social.

La ejecución versión 3 usa un coordinador independiente de la página, tareas transaccionales y una meta total anual compartida entre fuentes. El contrato de registros permanece en versión 2. Noticias, foros, instituciones, artículos y reportes se conjugan conservando sus diferencias y conflictos. Seleccionar todos los rubros no multiplica la cuota.

## Empezar con tus elementos

La página inicia en **Proyecto propio**, sin tema ni semillas de tatuaje. En **Cargar tus elementos** puedes importar JSON, JSONL, CSV o TXT sin ejecutar búsquedas, o abrir **Añadir un elemento manualmente**. La plantilla CSV usa `titulo,texto,autor,fuente,fecha,url`; sólo se necesita contenido y los metadatos ausentes se conservan como faltantes. Para analizar por tema escribe tu consulta y tus rubros. Una fecha proporcionada no se considera comprobada automáticamente.

**Ejemplo: tatuaje** carga el caso didáctico de tatuaje, sus rubros y semillas. Es opcional y editable. Las bases e informes sobre tatuaje ilustran el uso de SIAN; no definen el dominio del sistema ni se mezclan automáticamente con los elementos de otros proyectos.

La pantalla muestra un resumen de tema, región, años, capas de fuentes y meta anual. **Ver diseño de recolección** permite abrir la configuración detallada y las estrategias de las semillas; inicia cerrado.

## Abrir y recolectar

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

En la página configurar tema, región, años, texto mínimo y meta total anual. **México incluye automáticamente sus 32 entidades federativas, incluida Ciudad de México** en los términos de búsqueda y filtrado; también reconoce CDMX y Edomex. Se puede agregar vocabulario local. La coincidencia de un nombre territorial es una señal para revisión, no prueba suficiente de que todo el documento trate del país. El país del medio sigue separado del lugar del tema. La acción histórica con todas las capas crea una ejecución recuperable. El caso de tatuaje usa 2016 al presente, todos los rubros y 200 documentos únicos por año. La búsqueda debe intentarlo, pero la disponibilidad de fuentes puede dejar brechas.

Para preparar el caso por comandos sin iniciar búsquedas:

```bash
python scripts/collect_historical.py --config examples/tatuaje_2016_actualidad.json --plan-only
python scripts/collect_historical.py --resume CODIGO_DE_EJECUCION
```

## Guardado y recuperación

Cada documento se confirma en SQLite. La página muestra cobertura real por año y motivos de exclusión. Descargar **Descargar ejecución completa ZIP** para conservar corpus, plan y tareas. El código privado recupera la ejecución en el mismo servidor; **Importar respaldo de ejecución** permite restaurarla después de perder su disco. Los ZIP antiguos se migran conservando documentos.

Recargar o cerrar el navegador no cancela el proceso. Un reinicio del servidor puede interrumpirlo. Para recuperación automática después de perder el disco configurar un volumen persistente mediante `SIAN_DATA_DIR` o respaldo privado S3. Sin esa infraestructura hay que conservar el ZIP. No se guardan archivos automáticamente en la computadora del usuario.

La acción **Fusionar bases por fuente** recibe códigos de ejecuciones y crea una base conjunta con procedencias. Importar JSON, JSONL, CSV o TXT crea una ejecución guardada; la captura manual también se conserva y puede descargarse. DOI y URL canónica definen identidad; las copias exactas entre URLs se conservan pero sólo una cuenta para la cuota.

## Fechas y calidad

El año contado procede de publicación explícita y válida. El año solicitado, `lastmod`, consulta y detección por índices no lo sustituyen. Los documentos sin fecha siguen disponibles para análisis temático, pero no cuentan para la cuota anual. El año corriente es incompleto y las consultas no pasan del presente.

La cuota exige texto suficiente, pertinencia y fecha utilizable. Los fragmentos pueden contar como evidencia parcial y deben interpretarse como tales. Alcanzar 200 documentos no prueba representatividad: el criterio de parada puede sesgar distribuciones mensuales y de fuentes. Los análisis de tendencias necesitan un diseño independiente.

## Documentación vigente

- [Recolección histórica y recuperación](RECOLECCION_HISTORICA.md): algoritmo, capacidades, estados, comandos y persistencia.
- [Arquitectura](ARCHITECTURE.md): responsabilidades y flujo de datos.
- [Instalación y uso](README_EJECUTAR.md): ejecución local y recuperación.
- [Contrato de registros v2](ARQUITECTURA_REGISTROS_V2.md): documento, versión, recuperación, evidencia y revisión.
- [Evidencia y modelos](EVIDENCIA_Y_MODELOS.md): requisitos de cada análisis y modelos descriptivos.
- [Disección estructural](STRUCTURAL_NARRATIVE_DISSECTION.md) y [Smart Data](SMART_DATA_NUCLEUS.md): heurísticas y poda revisable.
- [Manual Word](publication/SIAN_Recoleccion_Historica_2026-10-07.docx) y [PDF](publication/SIAN_Recoleccion_Historica_2026-10-07.pdf).

Los informes y pilotos del 6 de octubre conservan su fecha y límites; actualizar el código no los convierte en nuevas mediciones. Los modelos de cubridor y las propuestas metodológicas especializadas están en `publication/`.

## Verificación y publicación

```bash
python -m unittest discover -s tests -q
```

Las pruebas comprueban identidad, fechas, conflictos, contratos, pausas compartidas, interrupción, restauración, cursores históricos, cuota y conjugación. La interfaz también se verifica con Streamlit AppTest. Estas pruebas no garantizan disponibilidad de proveedores ni una cuota conseguida.

GitHub contiene código, documentación y semillas curadas. Las bases de ejecución, corpus descargados, cachés y credenciales se excluyen. Los textos se analizan en el proceso donde se ejecuta SIAN, sin enviarlos a un modelo externo; en la app alojada ese proceso está en el servidor.

## Respaldo y análisis cada 20 minutos

El trabajador crea una copia consistente al iniciar, cada 1 200 segundos y al terminar, pausar o sufrir una excepción controlada. El temporizador es independiente de las búsquedas. Cada copia incluye los registros, SQLite, plan, cobertura y `checkpoint_analysis.json`/`.md`, con disponibilidad para lectura temática, comparación por fuentes, descripción temporal y extracción revisable de redes. El informe no valida representatividad, posturas ni causalidad.

`latest_checkpoint.zip` se actualiza en el disco del trabajador. **Eso no es almacenamiento permanente en Streamlit Cloud.** Sólo si `SIAN_BACKUP_BUCKET` está configurado se envía el ZIP a S3 y se confirma `backup_saved_at` después de un envío exitoso. Las copias fallidas se indican y se reintentan en el siguiente intervalo; el código de ejecución permite recuperar la última copia externa. Un cierre abrupto puede perder hasta el avance posterior al último envío confirmado.

En Streamlit Cloud, configurar en los Secrets de la app (nunca en GitHub ni en el chat):

```toml
SIAN_BACKUP_BUCKET = "NOMBRE_DEL_BUCKET_PRIVADO"
SIAN_BACKUP_PREFIX = "sian/jobs"
AWS_DEFAULT_REGION = "REGION_DEL_BUCKET"
AWS_ACCESS_KEY_ID = "CLAVE_DE_ACCESO"
AWS_SECRET_ACCESS_KEY = "CLAVE_SECRETA"
```

El bucket debe existir y las credenciales deben permitir `s3:PutObject` y `s3:GetObject` sólo sobre el prefijo elegido. Activar versionado del bucket si se quieren conservar copias anteriores; la app actualiza el objeto de la ejecución. Las credenciales se pasan al trabajador independiente sin incluirse en las bases o respaldos. La interfaz muestra la fecha de la última copia externa confirmada y permite descargar la copia analizada. Sin Secrets configurados, esta función queda en modo local y no evita pérdidas por reinicio del servidor.
