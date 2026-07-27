# Disección estructural de narrativas

## Cambio de paradigma

El sistema no debe limitarse a leer textos, contar palabras o promediar
sentimiento. Una narrativa se trata como un ecosistema de información: fuentes,
actores, proposiciones, actos de habla, relaciones causales, premisas
implícitas, sesgos de circulación y huellas de influencia.

La pregunta robusta no es “qué palabras aparecen”, sino:

- quién afirma, promete, ordena, acusa o declara;
- qué relación causal se propone;
- qué hipótesis de premisa queda sin decir;
- qué actores ganan centralidad;
- qué fuentes amplifican o estabilizan una formulación;
- qué marcadores retóricos requieren revisión humana;
- cómo cambia la estructura narrativa a través del tiempo.

## Trinidad de validación

### Computólogo: arquitecto de sistemas cognitivos

Responsable de infraestructura, extracción local, grafos y reproducibilidad.

Entregables mínimos:

- extracción heurística de proposiciones `sujeto -> verbo -> objeto`;
- detección local de causalidad;
- clasificación de actos de habla;
- cálculo de entropía narrativa;
- construcción de grafo estructural de influencia;
- exportación auditable a JSON/CSV.

### Experto legal: arquitectura de licitud y evidencia

Responsable de perímetro OSINT, trazabilidad y límites de extracción.

Entregables mínimos:

- protocolo de fuente pública;
- respeto de `robots.txt`;
- no automatizar sesiones, CAPTCHAs ni espacios privados;
- hash SHA-256 por registro;
- trazabilidad técnica con URL, fecha, estado, fuente y método de captura;
- separación entre texto completo `ok` y señal parcial `ok_partial`.

### Analista/estratega: sintetizador humano

Responsable de hipótesis, interpretación y validación de falsos positivos.

Entregables mínimos:

- diccionario de relaciones;
- revisión de actores;
- validación de hipótesis implícitas;
- descarte de marcadores retóricos falsos;
- lectura cercana de fragmentos clave;
- decisión sobre qué puede publicarse.

## Pipeline de cuatro capas

Antes de extraer proposiciones masivas, el sistema aplica el enfoque Smart Data
Nucleus: cartografía de fuentes, poda Pareto, extracción de marcos, detección de
ecos, deltas temporales y silencios. Esta capa evita que la disección
estructural se convierta en fuerza bruta.

### 1. RIG: Recopilación Inteligente de Grafos

Entrada: texto, audio transcrito, metadatos y URLs semilla.

Acción:

- deduplicar;
- clasificar fuente;
- registrar quién dijo qué, cuándo y dónde;
- guardar estado de evidencia;
- generar hash de integridad.

### 2. Segmentación estructural

Entrada: texto limpio.

Acción:

- separar oraciones;
- extraer proposiciones `SVO`;
- clasificar actos de habla:
  - afirmación;
  - directiva;
  - promesa/compromiso;
  - expresiva;
  - declarativa;
- detectar causalidad;
- proponer hipótesis de premisa implícita.

### 3. Marcación retórica revisable

Entrada: proposiciones.

Acción:

- marcar señales argumentales revisables:
  - ad hominem;
  - falsa causa;
  - pendiente resbaladiza;
  - falso dilema;
  - apelación al miedo;
  - generalización apresurada;
  - apelación a autoridad;
- marcar señales de presión narrativa:
  - sobrecarga emocional;
  - urgencia de compartir;
  - marco conspirativo;
  - chivo expiatorio;
  - afirmación absoluta;
- calcular confianza estructural.

Importante: estas marcas son señales de auditoría, no sentencias.

### 4. Tablero de deriva e influencia

Entrada: proposiciones ponderadas.

Acción:

- resumen por año y tipo de fuente;
- entropía de actos de habla;
- entropía de predicados;
- grafo fuente--actor--acto--marcador--señal;
- exportación de trazabilidad técnica;
- mapas para lectura cercana.

## Métricas nuevas

- `pareto_core`: fuente incluida en el núcleo de influencia 20/80.
- `frame_density`: proporción de marco problema-culpable-solución-urgencia
  detectado.
- `echo_status`: indica si un marco es original/variante o eco.
- `delta_type`: baseline, cambio o repetición estable.
- `missing_share`: proporción de fuentes Pareto que omiten un tema esperado.
- `speech_act_entropy`: diversidad de actos de habla. Baja entropía puede
  indicar repetición disciplinada; alta entropía puede indicar dispersión.
- `predicate_entropy`: diversidad de verbos/predicados. Mide repetición
  estructural de relaciones.
- `fallacy_signals`: número de proposiciones con marcadores retóricos revisables.
- `disinformation_vector_signals`: número de proposiciones con señales de
  presión, miedo, conspiración o absolutismo.
- `mean_structural_confidence`: confianza heurística de extracción SVO.
- `record_hash`: hash SHA-256 para trazabilidad técnica.

## Límite crítico

El sistema no prueba intención, delito ni verdad factual por sí mismo. Detecta
patrones estructurales que deben ser revisados por una persona experta. Para
publicación se debe reportar:

- corpus usado;
- fuentes excluidas;
- proporción `ok/ok_partial`;
- reglas heurísticas;
- validación humana;
- límites de inferencia.
