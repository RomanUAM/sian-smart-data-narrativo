# Ejecución local de SIAN

Este proyecto está diseñado para correr en la computadora del investigador.
No envía textos a servicios de IA externos. Las consultas a internet se usan
para recuperar fuentes públicas o metadatos abiertos; el análisis narrativo se
calcula localmente sobre JSON/CSV.

## 1. Crear entorno

Desde la carpeta del proyecto:

```bash
cd /Users/romananselmomoragutierrez/Documents/Codex/2026-06-20/c/news_spider
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Abrir la aplicación

```bash
streamlit run streamlit_app.py --server.port 8502
```

Abrir:

```text
http://localhost:8502
```

## 3. Corrida mínima recomendada

Antes de una corrida larga:

1. seleccionar un solo año;
2. dejar `Términos aleatorios por mes y capa = 8`;
3. correr una capa a la vez:
   - noticias;
   - foros/conversaciones;
   - gobierno/instituciones;
   - artículos + PDFs;
4. revisar `coverage_gap`;
5. fusionar bases sólo si hay balance mínimo.

## 4. Estrategia de búsqueda

La corrida secuencial publicable no usa fuerza bruta. Usa:

```text
año × mes × capa × muestra aleatoria reproducible de términos/rubros
```

Los artículos científicos son excepción: se consultan por año, no por mes,
porque OpenAlex/Crossref recuperan obras anuales y repetir mensualmente produce
duplicados.

Reddit RSS queda como opción manual exploratoria. No es la ruta principal para
conversación humana porque se bloquea con frecuencia y no representa toda la
conversación social.

## 5. Qué se guarda

Las salidas locales se guardan en:

```text
news_output/
news_output/by_source/
news_output/by_rubric/
```

Cada corrida iniciada desde la app crea:

```text
run_manifest.json
```

Si la corrida es secuencial, también crea:

```text
query_plan.json
```

Estos archivos registran parámetros, semilla, capas, cuotas y plan de búsqueda.
Sirven para saber qué se intentó aunque la corrida se detenga por red o por el
usuario.

Estas carpetas no deben subirse a GitHub salvo que se trate de una muestra
pequeña, pública, anonimizada y autorizada. Por defecto están ignoradas.

## 6. Qué sí va en GitHub

- código Python;
- documentación metodológica;
- agentes locales de revisión;
- semillas curadas públicas;
- TeX/PDF/DOCX publicables;
- `requirements.txt`;
- `.gitignore`.

## 7. Qué no va en GitHub

- bases completas descargadas;
- `news_output/`;
- `solver_output/`;
- `__pycache__/`;
- archivos temporales;
- credenciales;
- capturas/exportaciones privadas;
- comentarios de redes no autorizados.
