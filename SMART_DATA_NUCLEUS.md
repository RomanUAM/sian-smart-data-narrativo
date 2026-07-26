# Smart Data Nucleus (SDN)

## Filosofía

El sistema no busca volumen bruto. Pasa de Big Data a Smart Data:

- Big Data frágil: indexar miles o millones de publicaciones y buscar palabras
  clave.
- Smart Data defendible: identificar fuentes influyentes, extraer marcos
  argumentales, guardar estructura, relaciones, hashes y deltas.

La unidad de análisis no es el texto completo, sino el ecosistema de influencia:
quién habla, quién amplifica, quién reacciona, qué problema formula, a quién
culpa, qué solución propone, qué urgencia invoca y qué omite.

## Cuatro capas de profundidad

### Capa 1: Cartografía de fuentes

Objetivo: ubicar autoridad y flujo antes de extraer más contenido.

La app calcula una cartografía por fuente con:

- registros;
- años activos;
- tipo principal de fuente;
- proporción de texto completo/parcial;
- peso estructural;
- núcleo Pareto.

La poda 20/80 conserva el conjunto de fuentes que acumula cerca del 80% del
peso estructural. Es una aproximación local: para una versión Neo4j se puede
reemplazar por PageRank, betweenness y centralidad temporal.

### Capa 2: Marcos argumentales

Para cada fuente Pareto, el sistema extrae estructura:

- problema;
- culpable;
- solución;
- urgencia.

Si un marco es casi idéntico a otro, se marca como `ECO_DE`. En ese caso no
conviene duplicar texto: se conserva el hash, el vínculo y la relación.

### Capa 3: Evolución temporal

La narrativa se entiende como película, no como fotografía. El sistema compara
marcos por fuente y año:

- `baseline`: primer marco observado;
- `change`: cambio en problema, culpable, solución o urgencia;
- `stable_repetition`: repetición sin novedad estructural.

La poda guarda deltas. Las repeticiones se tratan como contador temporal.

### Capa 4: Silencios estructurales

El sistema no inventa hechos faltantes. El analista define una lista de temas o
hechos esperados. La app compara esos temas contra los marcos del núcleo Pareto
y marca alertas cuando una proporción alta de fuentes no los menciona.

Ejemplo para tatuaje:

- regulación sanitaria;
- riesgos de infección;
- consentimiento informado;
- discriminación laboral;
- tintas no autorizadas.

## Ontología DRO

Relaciones base:

1. `APOYA_A`
2. `ATACA_A`
3. `CONTRADICE_A`
4. `AMPLIFICA_A`
5. `DESINFORMA_SOBRE`
6. `VERIFICA_A`
7. `DEPENDE_DE`
8. `ANTECEDE_A`
9. `CAUSA_A`
10. `PREVIENE_A`
11. `JUSTIFICA_A`
12. `CUESTIONA_A`
13. `IGNORA_A`
14. `ECO_DE`
15. `NARRATIVA_ALTERNATIVA_DE`

## Retención y legalidad

La versión local conserva el corpus si el usuario decide mantener los JSON de
extracción. El export SDN, sin embargo, privilegia:

- hashes;
- metadatos;
- frames;
- relaciones;
- decisiones de poda;
- deltas;
- alertas de silencio.

No automatiza acceso a espacios privados, sesiones, CAPTCHAs ni paywalls. Para
publicación se debe reportar la proporción `ok/ok_partial` y aclarar que las
falacias o silencios son señales heurísticas sujetas a validación humana.

## Neo4j: ruta posterior, no requisito actual

La app actual trabaja localmente con JSON/CSV para no introducir dependencia
pesada. La arquitectura está pensada para exportarse a Neo4j:

- nodos: fuente, actor, marco, problema, culpable, solución, urgencia, vector;
- relaciones: `AMPLIFICA_A`, `ECO_DE`, `CAUSA_A`, `IGNORA_A`, etc.;
- evidencia: hashes de documentos;
- temporalidad: año, fecha de captura, delta.

Neo4j debe verse como siguiente fase de infraestructura, no como condición para
que el prototipo funcione.

