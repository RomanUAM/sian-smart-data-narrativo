# Estrategias de extracción por medio

## Arquitectura de perfiles de fuente

La extracción ya no debe depender de una lista suelta de dominios. Cada medio se
registra en `source_profiles.py` con estos campos mínimos:

- medio y dominio canónico;
- país, región e idioma;
- tipo de fuente: noticia, foro/blog público, reporte institucional/gobierno,
  artículo científico o reporte industrial;
- acceso: abierto, parcial, paywall o sólo índice/metadato;
- patrones de URL esperados;
- secciones relevantes;
- marcadores de corte para limpiar recomendaciones, publicidad, pies de página
  y módulos editoriales.

Esto permite que el corpus sea auditable: si una noticia viene de México,
Estados Unidos, Reino Unido, Brasil o América Latina, el sistema sabe cómo
clasificarla antes del análisis. También evita el error conceptual de tratar
un artículo científico, una nota periodística y una conversación pública como
evidencia equivalente.

## Medios base por región

El catálogo inicial incluye:

- México: La Jornada, Milenio, El Universal, Aristegui Noticias, NMAS, Proceso
  y Animal Político.
- Reino Unido/global: The Guardian, BBC News, BBC Mundo, The Independent y
  Financial Times como índice/metadato cuando no haya acceso completo.
- Estados Unidos/global: Reuters, Associated Press, CNN, NPR, Vox, Los Angeles
  Times, New York Times y Washington Post; los paywalls no deben contarse como
  cuerpo completo si sólo se recupera metadato.
- Europa/global: El País, Le Monde, Deutsche Welle, France 24 y Al Jazeera
  para contraste multilingüe y no sólo anglosajón.
- Brasil: Folha de S.Paulo, G1 Globo, Agência Brasil, Estadão, O Globo y UOL.
- América Latina: Página/12 y El Tiempo, más dominios regionales configurables
  desde la app.
- Gobierno e instituciones: gob.mx, Secretaría de Salud, COFEPRIS, DOF,
  INEGI, Cámara de Diputados, Senado, OMS/WHO, OPS/PAHO y UNESCO. Esta capa no
  es conversación orgánica; sirve para observar regulación, comunicados,
  políticas públicas y marcos institucionales.

Las fuentes parcialmente cerradas no deben inflar el corpus como texto completo:
si sólo se obtiene título/resumen, deben quedar como `ok_partial` o como
metadato trazable, no como cuerpo periodístico equivalente.

## Regla ética y legal de extracción

El sistema debe operar como herramienta local de investigación, no como extractor
agresivo ni como mecanismo para evadir restricciones. Por tanto:

1. Sólo se consultan índices públicos, RSS públicos, páginas web abiertas o URLs
   semilla proporcionadas por el investigador.
2. Antes de descargar HTML completo se revisa `robots.txt`. Si la ruta no permite
   extracción, no se fuerza el cuerpo: se conserva sólo metadato/título/resumen
   como `ok_partial`.
3. Sitios con paywall o acceso parcial se usan como índice o señal bibliográfica,
   no como texto completo salvo que el investigador tenga acceso legítimo.
4. No se automatiza inicio de sesión, no se saltan CAPTCHAs y no se raspan
   espacios privados o cerrados como Instagram/Facebook/TikTok sin API,
   exportación autorizada o consentimiento.
5. Los textos completos se guardan para análisis local y trazabilidad; en
   publicación se reportan resultados agregados, citas breves y metadatos, no
   redistribución masiva de contenido protegido.

Para foros/conversación pública, la muestra debe reportarse como señal indexable
parcial. No equivale a “lo que dice toda la gente en redes”.

Reddit no debe ser el cuello de botella del corpus. En la implementación actual
se consulta como fuente opcional y tardía porque produce límites 429 con
facilidad. Antes de Reddit se prueban blogs y comunidades abiertas como Medium,
Substack, WordPress, Blogspot, Tumblr, Tattoo.com, Tattoodo, Tattooing101,
Quora o StackExchange cuando el tópico lo justifica.

## La Jornada

Ejemplo semilla:

```text
https://www.jornada.com.mx/noticia/2020/01/12/cultura/el-tatuaje-en-mexico-prejuicio-clandestinidad-y-aceptacion-la-semanal-6148
```

Patrón observado:

```text
https://www.jornada.com.mx/noticia/YYYY/MM/DD/<seccion>/<slug>
```

Secciones útiles detectables desde el corpus semilla:

- cultura;
- sociedad;
- estados;
- capital;
- ciencia-y-tecnologia;
- mundo;
- deportes;
- columnas/opinión cuando el texto trate el tópico.

Estrategia:

1. Usar URLs semilla para identificar dominio y secciones.
2. Construir búsquedas por dominio:

   ```text
   (tatuaje OR tatuajes OR tattoo OR "arte corporal") (México OR Mexico)
   domain:jornada.com.mx
   ```

3. Ejecutar por año/mes para no saturar índices.
4. Procesar cada URL encontrada con extractor local.
5. Aplicar limpieza específica:
   - cortar menú inicial;
   - cortar desde `Últimas Noticias`;
   - cortar desde `Más de <sección>`;
   - cortar `Publicidad Comercial`;
   - cortar pie de página y copyright.

Notas:

- La Jornada suele entregar el cuerpo visible en HTML, por lo que no requiere API.
- El cuerpo puede venir seguido de bloques de navegación; si no se cortan, contaminan n-gramas y grafo.
- Las URLs semilla no son el corpus final: son guías para encontrar más notas del mismo medio.

## Foros y blogs públicos

No se deben raspar comentarios privados ni saltar sesión/API de Instagram,
TikTok, Facebook u otros espacios cerrados.

Fuentes públicas razonables, en orden metodológico recomendado:

- Medium;
- Substack;
- WordPress;
- Blogspot;
- Tumblr;
- comunidades temáticas abiertas como Tattoo.com, Tattoodo o Tattooing101;
- Quora público;
- StackExchange cuando el tópico tenga comunidad pertinente;
- Hacker News o Dev.to sólo para tópicos tecnológicos;
- Reddit público/RSS como fuente tardía y limitada, no como única vía.

Estas fuentes se reportan como señales conversacionales públicas. No equivalen
a un archivo completo de comentarios sociales.

## Gobierno e instituciones

Esta capa debe recolectarse separada de noticias y foros. Sirve para ubicar el
marco normativo o institucional que rodea el tópico: alertas sanitarias,
regulaciones, comunicados, documentos públicos y debates legislativos.

Para el caso tatuaje, las rutas institucionales más útiles son:

- COFEPRIS y Secretaría de Salud para tintas, riesgos sanitarios, infección,
  alergias y maquillaje permanente;
- DOF, Cámara de Diputados y Senado para normas, iniciativas y regulación;
- gob.mx como índice federal general;
- OPS/OMS para salud pública comparada;
- UNESCO si el tópico se desplaza hacia cultura, cuerpo, identidad o patrimonio.

No debe interpretarse como “voz de la gente”. Debe analizarse como capa de
autoridad institucional que puede influir en prensa, conversación pública e
investigación.
