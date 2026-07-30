# Arquitectura unificada: noticias, araña mezclada y narrativa

Fecha: 2026-07-29

## Cambio conceptual

La recolección de noticias no debe iniciar desde rubros interpretativos como
`tatuaje artístico`, `tatuaje discriminación` o `tinta corporal`. Esos rubros
son categorías de análisis, no necesariamente frases usadas por los medios.

El flujo correcto es:

```text
búsqueda amplia -> descarga -> limpieza -> deduplicación -> clasificación narrativa -> análisis
```

No:

```text
rubro -> frase exacta -> mes -> fuente -> búsqueda
```

## Regla implementada

Para fuentes públicas indexadas:

- noticias;
- foros y blogs;
- instituciones;
- reportes web;

el sistema usa términos núcleo amplios, por ejemplo:

```text
tatuaje, tatuajes, tattoo, tattoos, arte corporal, body art
```

Después de recuperar documentos, etiqueta cada registro con rubros narrativos
probables usando los términos definidos por el usuario.

Para artículos científicos:

- OpenAlex;
- Crossref;
- Redalyc;

sí se permite usar variantes más específicas por año, porque ahí se busca
evidencia especializada y no cobertura mensual de prensa.

## Campos nuevos

Cada registro puede incluir:

- `narrative_rubrics`: rubros detectados después de la recolección;
- `narrative_rubric_terms`: términos que dispararon esa clasificación.

Estos campos no reemplazan lectura humana; son una primera etiqueta auditable.

## Efecto esperado

La corrida secuencial deja de multiplicar búsquedas por:

```text
rubro x término x mes x fuente
```

y pasa a buscar por:

```text
términos núcleo x mes x fuente
```

Luego clasifica el corpus. Esto reduce:

- rate limits;
- falsos ceros;
- sesgo por frases demasiado específicas;
- duplicación de consultas;
- tiempo de corrida.

## Criterio crítico

Si una categoría narrativa aparece con cero documentos después de clasificar, eso
es un resultado analítico. Si aparece con cero documentos porque se buscó una
frase demasiado estrecha, es un error metodológico. Esta actualización evita ese
segundo caso.

