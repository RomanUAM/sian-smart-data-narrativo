# Ejecución robusta para corridas largas

El sistema no debe depender de que una pestaña de Streamlit permanezca abierta
durante horas. Para generar bases grandes, siga estas reglas:

1. Verifique espacio libre antes de iniciar.
   - Recomendado: al menos 10 GB libres.
   - Mínimo operativo: 3 GB libres.

2. Mantenga la app en una terminal independiente.

```bash
streamlit run streamlit_app.py --server.port 8502 --server.fileWatcherType none
```

3. No cierre la terminal durante la recolección.

4. Para producción, prefiera scripts de lote:

```bash
python3 scripts/run_query_plan.py --help
```

5. Guarde salidas grandes fuera del repositorio.

Ejemplo:

```bash
mkdir -p ~/SIAN_outputs
```

Use ese directorio como carpeta de salida desde la interfaz.

## Razón técnica

Streamlit es una interfaz interactiva, no un gestor de trabajos largos. Si el
disco está lleno, si la pestaña se recarga o si una fuente limita peticiones, el
trabajo puede detenerse. Por eso el diseño correcto es:

```text
araña de fondo -> JSON incremental -> archivo de estado -> Streamlit monitorea
```

El sistema actual ya guarda registros incrementales, pero aún debe evolucionar a
un gestor de trabajos separado para que la recolección no dependa de la sesión
web.

