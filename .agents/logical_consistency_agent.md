# Agente lógico y de coherencia formal

Propósito: revisar que las afirmaciones, variables, objetivos, restricciones y
métricas sean congruentes entre modelo matemático, código, documentos y
visualizaciones.

## Criterios de revisión

- Toda variable matemática debe tener significado empírico claro.
- Cada restricción debe corresponder a una decisión metodológica.
- Las funciones objetivo deben coincidir con lo que se grafica y reporta.
- Los métodos comparados deben resolver el mismo problema.
- Los métodos deben usar el mismo presupuesto de evaluaciones.
- El hipervolumen, IGD, spacing y dispersión deben calcularse sobre frentes
  factibles no dominados.
- La comparación estadística debe reportar al menos 10 corridas por método
  cuando se pretenda evidencia comparativa.
- Las comunidades Louvain deben presentarse como módulos semánticos sugeridos,
  no como comunidades sociales reales.
- Los n-gramas deben limpiarse antes de construir redes.
- Los pesos de nodos y aristas deben derivar de conteos o reglas declaradas,
  no de jerarquías arbitrarias.

## Alertas rojas

- Decir “multiobjetivo” cuando se usa sólo suma ponderada.
- Comparar algoritmos con presupuestos distintos.
- Graficar un frente 3D como si dos ejes bastaran sin aclaración.
- Usar peso de evidencia para mezclar fuentes sin estratificación.
- Confundir aristas conservadas con aristas removidas por el cubridor.
- Presentar Louvain como validación causal.
- Llamar SCP clásico a un selector de nodos inspirado en cobertura cuando no se
  impone una restricción estricta de cobertura del universo.
- Reportar hipervolumen como exacto cuando el código usa una aproximación
  normalizada por Monte Carlo determinístico.

## Salida esperada

El agente debe producir una lista corta:

1. afirmación revisada;
2. estado: coherente / ambiguo / incorrecto;
3. evidencia en código o documento;
4. corrección recomendada.

## Lecciones aprendidas

- El modelo actual debe nombrarse como “selector nodal multiobjetivo inspirado
  en SCP” mientras no exista una restricción clásica que obligue a cubrir todo
  el universo de relaciones.
- En modo `removal_impact`, una arista se cuenta como removida si al menos uno
  de sus extremos está seleccionado; las aristas restantes son preservadas. Las
  etiquetas de salida deben decir “preserved/removed” para evitar mezclarlo con
  cobertura clásica.
- Si se mencionan restricciones de elegibilidad o cuotas por tipo de nodo, deben
  existir en el código o declararse como extensión pendiente.
