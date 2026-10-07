# SIAN - Smart Data Narrativo

Paquete local para construir y analizar corpus narrativos desde fuentes públicas:
noticias, artículos científicos abiertos, fuentes institucionales, blogs, foros y
otros documentos web.

## Requisitos

- Python 3.10 o superior.
- Conexión a internet para recolectar datos públicos.
- En macOS/Linux se recomienda crear un entorno virtual.

## Instalación

Desde la carpeta del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

En Windows:

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Ejecutar la app

```bash
streamlit run streamlit_app.py --server.port 8502 --server.fileWatcherType none
```

Luego abrir:

```text
http://localhost:8502
```

En macOS también puedes abrir:

```bash
scripts/start_sian_terminal.command
```

## Notas importantes

- Para bases grandes, no cierres la terminal donde corre Streamlit.
- La recolección usa fuentes públicas y puede encontrar límites de tasa.
- No se garantiza un mínimo de documentos por fuente si no existen o si no son
  legalmente accesibles; el sistema debe reportar brechas de cobertura.
- Los JSON generados deben guardarse fuera del ZIP si se van a mover bases muy
  grandes.

## Documentos incluidos

Los documentos metodológicos están en `publication/`:

- `sian_metodologia_narrativa_es.pdf`
- `modelo_multiobjetivo_cubridor_narrativo.pdf`
- `sian_narrative_method_en.pdf`



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

## Archivos en la versión web
La recolección guarda JSON en el servidor de Streamlit, no en la computadora del usuario.
Cada sesión web nueva tiene una carpeta propia; el almacenamiento del servidor es temporal.
En **Archivos y respaldo** se puede descargar un ZIP de los JSON/JSONL/CSV disponibles,
incluso los registros parciales de una corrida y el manifiesto si no hubo resultados.
No cierre la sesión sin descargar el respaldo. Un archivo de control no implica documentos recuperados.
Para recuperar un corpus descargado, use **Importar corpus desde tu computadora** y
**Cargar archivos importados**. Se pueden cargar varios JSON/JSONL y fusionarlos.
Las corridas secuenciales guardan un consolidado tras cada paso completado.
No se garantiza recuperar archivos de una sesión antigua ni después de reiniciar el servidor.
