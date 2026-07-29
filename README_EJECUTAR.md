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

