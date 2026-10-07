\section{Actualización: evidencia disponible y requisitos de análisis (6 de octubre de 2026)}
Esta actualización prevalece sobre supuestos anteriores de disponibilidad completa.
Autoría, fecha y fuente se buscan, pero su recuperación no está garantizada.
Cada campo conserva valor, evidencia, método y estado: explícito, inferido,
buscado y no encontrado, no evaluable, no aplica o contradictorio.
Se conservan candidatos contradictorios sin elegir arbitrariamente.

Publicación, actualización y consulta son fechas distintas. La precisión puede
ser año, mes o día; no se completa información ausente. El año de búsqueda se
conserva como \texttt{search\_year}; \texttt{year} sólo refleja publicación
explícita utilizable. Una fecha de detección de índice no es publicación.
Un enlace PDF no acredita recuperación de texto completo.

Un documento sin autor o fecha puede aportar al análisis temático. Cada análisis
presenta documentos utilizables, total, motivos de exclusión y cobertura por tipo
de fuente. La cobertura no garantiza representatividad o suficiencia estadística.
Los registros antiguos de fecha ambigua necesitan revisión humana para entrar
en comparaciones temporales. El dominio de una URL no equivale a firma personal,
editor identificado o ubicación del acontecimiento.

\subsection{Representaciones matemáticas y revisión}
La matriz documento--concepto usa 1 para presencia revisada, 0 sólo para ausencia
tras revisión explícita del concepto y valor faltante para lo no evaluado.
La proporción fuente--concepto usa como denominador los documentos efectivamente
revisados para ese concepto. La red actor--concepto--postura conserva apoyo,
rechazo y ambivalencia por separado; requiere cita literal y atribución revisada.
Las relaciones dirigidas conservan tipo, documento y fragmento. Una causalidad
atribuida por el texto no constituye un efecto causal demostrado.
Los conteos temporales se calculan sobre la intersección revisada y fechada,
con cobertura explícita. No equivalen a cambio en la opinión poblacional.

Los módulos heurísticos anteriores generan candidatos exploratorios.
El módulo \texttt{evidence\_model.py} verifica estados y citas, pero no sustituye
juicio disciplinar. Las revisiones entran mediante JSON y se conservan al
exportar el corpus. No se infiere recepción a partir del mensaje original.
Las observaciones pueden depender de una misma institución o acontecimiento;
no se implementan pruebas inferenciales ni difusión con estos conteos.

\subsection{Pseudocódigo de operación}
\begin{enumerate}
\item Recuperar contenido y procedencia; buscar metadatos etiquetados cuando sea posible.
\item Conservar valor, evidencia y estado de cada campo; preservar conflictos y precisión.
\item Separar publicación, actualización, consulta y año de búsqueda.
\item Comprobar requisitos por análisis; registrar inclusión o motivo de exclusión.
\item Validar citas literales y atribuciones en las revisiones recibidas.
\item Construir matrices con valores faltantes distintos de cero; conservar signos de postura.
\item Exportar cobertura, matrices, relaciones y limitaciones del subconjunto utilizado.
\end{enumerate}
La política completa, ejemplos y comandos reproducibles están en
\texttt{EVIDENCIA\_Y\_MODELOS.md}. Los informes históricos no se convierten en
nuevas mediciones por actualizar el software.

\subsection{Contrato integral de corpus}
La identidad y fusión se centralizan en \texttt{corpus\_contract.py}, compartido por
la interfaz y los comandos. Se conservan parámetros identificadores de URL,
procedencias, variantes textuales y conflictos. La similitud de títulos no basta
para fusionar trabajos distintos. Las señales de silencio indican no detección en
fragmentos recuperados; no acreditan que una fuente ignore un tema. Las fechas
anuales no permiten ordenar publicaciones dentro del año. El exportador relacional
conserva tablas vacías cuando no existen interpretaciones revisadas. Véase
\texttt{AUDITORIA\_INTEGRAL\_2026-10-06.md} para pruebas y límites del piloto.

\subsection{Registros y etapas v2}
Documento, versión y recuperación tienen identificadores separados. La selección
requiere motivo, evidencia y revisor; los cambios invalidan interpretaciones
previas. Se distinguen títulos, resúmenes y fragmentos. Descubrimiento,
recuperación, extracción, selección, revisión y análisis tienen puntos de control
para reanudación. El ejecutor de corpus guardados organiza la evidencia existente,
sin simular nuevas descargas. Caché, reintentos limitados y registro transaccional
complementan la escritura atómica. La especificación y pseudocódigo están en
\texttt{ARQUITECTURA\_REGISTROS\_V2.md}.
