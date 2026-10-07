# Ejecutar y recuperar SIAN

SIAN necesita Python 3.10 o superior e internet para consultar fuentes públicas. El análisis de corpus ya guardados no requiere nuevas descargas. La cuota es total anual entre fuentes y la operación vigente está en [RECOLECCION_HISTORICA.md](RECOLECCION_HISTORICA.md).

## Instalar

Desde la raíz del repositorio, en macOS o Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

En Windows:

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Abrir la dirección que muestra Streamlit, normalmente http://localhost:8501 .

## Recolección y guardado

Configurar tema, región, años y meta total anual. Para el caso de tatuaje, usar 2016 al presente, todos los rubros y la acción de corrida histórica con todas las capas. Descargar **Descargar ejecución completa ZIP** y conservar el código privado. La base guarda cada registro en SQLite; los JSON y la cobertura se exportan después de las tareas y al solicitar el respaldo.

El código recupera una ejecución en el mismo disco. Para restaurar después de perderlo, importar el ZIP y reanudar. El ZIP nuevo conserva estado, documentos y plan; los respaldos anteriores con manifiesto se migran al nuevo plan. Cerrar la página no detiene el proceso. El botón **Parar araña** solicita una pausa después de terminar la operación actual.

## Terminal

```bash
python scripts/collect_historical.py --config examples/tatuaje_2016_actualidad.json --plan-only
python scripts/collect_historical.py --resume CODIGO_DE_EJECUCION
python scripts/collect_historical.py --resume CODIGO_DE_EJECUCION --plan-only --export respaldo.zip
python scripts/collect_historical.py --restore respaldo.zip --plan-only
```

Eliminar `--plan-only` inicia la recolección. La restauración genera un código nuevo. Las tareas completadas se omiten, las fallidas o diferidas se vuelven a intentar y la identidad evita contar otra vez el mismo documento.

## Servidor y persistencia

Configurar `SIAN_DATA_DIR` sobre un volumen persistente. Como alternativa adicional, `SIAN_BACKUP_BUCKET`, `SIAN_BACKUP_PREFIX` y credenciales AWS en el entorno activan el respaldo privado S3. Nunca escribir credenciales en GitHub. Sin almacenamiento externo, conservar el ZIP para restaurar tras perder el servidor. La página muestra si el respaldo externo está configurado y si la última copia falló.

## Si no aparecen documentos

Consultar el estado, el avance y `coverage.json`. `waiting_sources` indica tareas fallidas o diferidas; `finished_with_gaps` indica que las tareas disponibles terminaron sin alcanzar la cuota. Los registros sin publicación verificable, cortos, fuera del periodo o duplicados se conservan con motivos. Un archivo de control guardado no significa que se hayan recuperado documentos.

Agregar fuentes históricas o sitemaps pertinentes cuando RSS no cubra años antiguos. GDELT DOC no se consulta para 2016 y las fechas `lastmod` de los sitemaps no cuentan como publicación. Reanudar después de una pausa del proveedor permite intentar tareas pendientes sin reiniciar toda la búsqueda.
