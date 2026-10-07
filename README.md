# SIAN Smart Data Narrativo

SIAN reúne documentos públicos y organiza evidencia para analizar narrativas. Conserva procedencia, versiones, estados de autoría y fecha, y permite revisión humana de actores, conceptos, posturas y relaciones. Las señales automáticas son exploratorias: no demuestran opinión pública, intenciones ni causalidad social.

La ejecución versión 3 usa un coordinador independiente de la página, tareas transaccionales y una meta total anual compartida entre fuentes. El contrato de registros permanece en versión 2. Noticias, foros, instituciones, artículos y reportes se conjugan conservando sus diferencias y conflictos. Seleccionar todos los rubros no multiplica la cuota.

## Abrir y recolectar

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

En la página configurar tema, región, años, texto mínimo y meta total anual. La acción histórica con todas las capas crea una ejecución recuperable. El caso de tatuaje usa 2016 al presente, todos los rubros y 200 documentos únicos por año. La búsqueda debe intentarlo, pero la disponibilidad de fuentes puede dejar brechas.

Para preparar el caso por comandos sin iniciar búsquedas:

```bash
python scripts/collect_historical.py --config examples/tatuaje_2016_actualidad.json --plan-only
python scripts/collect_historical.py --resume CODIGO_DE_EJECUCION
```

## Guardado y recuperación

Cada documento se confirma en SQLite. La página muestra cobertura real por año y motivos de exclusión. Descargar **Descargar ejecución completa ZIP** para conservar corpus, plan y tareas. El código privado recupera la ejecución en el mismo servidor; **Importar respaldo de ejecución** permite restaurarla después de perder su disco. Los ZIP antiguos se migran conservando documentos.

Recargar o cerrar el navegador no cancela el proceso. Un reinicio del servidor puede interrumpirlo. Para recuperación automática después de perder el disco configurar un volumen persistente mediante `SIAN_DATA_DIR` o respaldo privado S3. Sin esa infraestructura hay que conservar el ZIP. No se guardan archivos automáticamente en la computadora del usuario.

La acción **Fusionar bases por fuente** recibe códigos de ejecuciones y crea una base conjunta con procedencias. Importar JSON o JSONL crea una ejecución guardada. DOI y URL canónica definen identidad; las copias exactas entre URLs se conservan pero sólo una cuenta para la cuota.

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
