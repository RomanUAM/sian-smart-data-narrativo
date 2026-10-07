# Ejecución local de SIAN

Seguir [README_EJECUTAR.md](README_EJECUTAR.md) para instalar, abrir, recuperar y exportar. La especificación completa está en [RECOLECCION_HISTORICA.md](RECOLECCION_HISTORICA.md).

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

La app y `scripts/collect_historical.py` usan el mismo coordinador. Los datos se guardan en `.sian_jobs` o `SIAN_DATA_DIR`, no en GitHub. Conservar el código privado y el ZIP completo. Si se ejecuta localmente, el disco de esa máquina conserva las bases; si se aloja en un servidor temporal, hace falta volumen persistente, respaldo externo o restauración desde ZIP.
