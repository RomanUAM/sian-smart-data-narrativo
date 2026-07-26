# Auditoría de coherencia del sistema SIAN

Fecha: 2026-07-26

## Dictamen breve

El sistema es pertinente si se define como prototipo local de análisis
estructural de narrativas sobre fuentes públicas. No es pertinente presentarlo
todavía como plataforma judicial completa, detector automático de verdad,
sistema de monitoreo masivo o infraestructura Neo4j/FastAPI productiva.

La arquitectura robusta debe formularse así:

> SIAN construye un corpus público trazable, separa capas discursivas, aplica
> poda Smart Data, extrae estructuras narrativas locales y produce mapas,
> métricas y alertas heurísticas que requieren validación humana.

## Principio ordenador

El proyecto tiene dos niveles:

### Nivel A: prototipo local implementado

Existe y puede correrse en la app:

- recolección por fuente;
- clasificación `news`, `forum`, `scientific_article`, `institutional_report`,
  `industry_report`, `other`;
- separación `ok`, `ok_partial`, `too_short`, `fetch_error`;
- limpieza local;
- n-gramas;
- grupos de ideas;
- geolocalización heurística;
- red narrativa;
- red semántica;
- grafo de conocimiento;
- cubridor nodal multiobjetivo;
- análisis de sentimiento léxico local;
- disección estructural:
  - proposiciones `Sujeto -> Verbo -> Objeto`;
  - actos de habla;
  - causalidad;
  - premisas implícitas;
  - señales heurísticas de falacia;
  - vectores de desinformación;
  - trazabilidad técnica con SHA-256;
- Smart Data Nucleus:
  - fuentes Pareto;
  - marcos problema/culpable/solución/urgencia;
  - ecos `ECO_DE`;
  - deltas temporales;
  - silencios `IGNORA_A`.

### Nivel B: arquitectura futura

Debe nombrarse como ruta de escalamiento, no como hecho:

- Neo4j;
- PostgreSQL;
- FastAPI;
- autenticación JWT;
- grafos 3D;
- embeddings semánticos con SentenceTransformers;
- retención automatizada de texto crudo;
- informes PDF ejecutivos automatizados;
- protocolo judicial formal de admisibilidad.

## Coherencia lógica por capa

| Capa | Pertinencia | Riesgo | Corrección |
|---|---|---|---|
| Recolección | Alta si se limita a OSINT público. | GDELT/Reddit pueden saturarse o sesgar corpus. | Usar fuentes por capa, cuotas y registrar brechas. |
| Smart Data | Alta. Evita fuerza bruta. | Pareto puede invisibilizar fuentes minoritarias. | Mostrar fuente completa y núcleo Pareto, no borrar minorías. |
| Frames | Alta para humanidades y análisis cultural. | Heurísticas pueden simplificar discursos complejos. | Usar como entrada a lectura cercana. |
| Ecos | Pertinente para no duplicar ruido. | Similitud léxica no equivale a dependencia real. | Etiquetar como `ECO_DE` candidato, no prueba causal. |
| Deltas | Alta. Narrativa es temporal. | Fechas incompletas distorsionan cambio. | Exigir fecha o marcar incertidumbre. |
| Silencios | Muy potente pero delicado. | La app puede parecer que inventa omisiones. | El analista debe declarar temas esperados antes. |
| Falacias | Útil como auditoría. | Riesgo de sobrediagnóstico. | Llamarlas señales heurísticas, no falacias probadas. |
| Cadena de custodia | Pertinente. | Hash no basta para admisibilidad legal. | Llamarlo trazabilidad técnica, no certificado judicial. |
| Cubridor nodal | Pertinente si se explica como selección de nodos relevantes. | Puede parecer optimización objetiva de “verdad”. | Explicar objetivos: compacidad, relevancia y daño estructural. |

## Correcciones de lenguaje necesarias

Evitar:

- “detector de verdad”;
- “prueba judicial”;
- “lavado de cerebro” como salida directa;
- “admisible en juicio” sin protocolo legal externo;
- “IA detecta intención”;
- “la narrativa social completa”.

Usar:

- “señal estructural”;
- “indicador heurístico”;
- “candidato a revisión”;
- “muestra pública trazable”;
- “lectura asistida”;
- “brecha de cobertura”;
- “cadena técnica de trazabilidad”.

## Pertinencia para publicación

El proyecto puede ser publicable si se presenta como metodología híbrida:

1. construcción de corpus público balanceado;
2. trazabilidad y límites éticos;
3. Smart Data frente a Big Data;
4. extracción estructural local;
5. redes narrativas y semánticas;
6. selección de nodos relevantes;
7. validación humana;
8. estudio de caso, por ejemplo tatuaje.

No conviene presentarlo como sistema legal-operativo cerrado. Conviene
presentarlo como prototipo metodológico reproducible.

## Chequeo antes de correr

Antes de ejecutar una corrida larga:

1. definir tópico y región;
2. elegir capas separadas, no araña mezclada;
3. declarar fuentes semilla;
4. declarar exclusiones;
5. declarar temas esperados para silencios;
6. fijar mínimo y máximo por tipo/año;
7. correr primero un año pequeño;
8. revisar `source_type`, `status`, `ok_partial`;
9. revisar n-gramas ruidosos;
10. revisar si Smart Data Pareto no está eliminando voces relevantes.

## Decisión final

La arquitectura es coherente si mantiene esta frontera:

- local, auditable, heurística, reproducible;
- no intrusiva;
- no totalizante;
- validada por humano;
- escalable a grafos reales en una fase posterior.
