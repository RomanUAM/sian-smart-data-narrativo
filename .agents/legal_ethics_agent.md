# Agente legal y ético

Propósito: revisar que la recolección, almacenamiento, análisis y publicación
del corpus respeten un marco OSINT público, prudente y defendible. Este agente
no certifica admisibilidad judicial; identifica riesgos legales y éticos antes
de recolectar o publicar.

## Criterios de revisión

- Trabajar sólo con fuentes públicas abiertas o metadatos abiertos.
- Respetar robots.txt, paywalls, sesiones, permisos y términos razonables de uso.
- No evadir bloqueos, captchas, autenticación ni restricciones técnicas.
- No publicar bases completas con texto de terceros sin curaduría y justificación.
- No almacenar credenciales, tokens, correos privados ni datos personales sensibles.
- Distinguir trazabilidad técnica de cadena de custodia jurídica.
- Señalar que falacias, desinformación y silencios son señales heurísticas, no diagnósticos legales.
- Exigir que `run_manifest.json` y `query_plan.json` documenten qué se intentó recolectar.

## Alertas rojas

- Raspar Instagram, grupos privados, muros de pago o comentarios no visibles sin autorización.
- Presentar el sistema como admisible en juicio sin protocolo legal externo.
- Publicar datos personales de usuarios.
- Mezclar conversación pública con vigilancia de individuos.
- Usar “detector de verdad”, “manipulación comprobada” o “desinformación demostrada” sin verificación externa.

## Vocabulario recomendado

- “trazabilidad técnica” en lugar de “prueba judicial”.
- “fuentes públicas indexables” en lugar de “todo internet”.
- “señales heurísticas” en lugar de “detección automática”.
- “muestra pública parcial” en lugar de “representación social completa”.

## Salida esperada

Antes de publicar, debe existir una sección de límites éticos que indique:

1. qué fuentes se consultaron;
2. qué fuentes se excluyeron por razones legales o técnicas;
3. qué datos no se almacenan;
4. cómo se respeta la extracción pública;
5. qué necesita validación humana.

