\section{Update: available evidence and analysis requirements (October 6, 2026)}
This update supersedes earlier assumptions of complete metadata availability.
Authorship, publication dates and outlets are sought but cannot be guaranteed.
Each field preserves its value, evidence, method and state: explicit, inferred,
searched but not found, not evaluable, not applicable or conflicting.
Conflicting candidates are retained rather than arbitrarily resolved.

Publication, update and consultation dates are distinct. Precision is year,
month or day; missing components are never filled. The legacy search year is
preserved as \texttt{search\_year}; \texttt{year} only represents usable explicit
publication evidence. Index observation dates are not publication dates.
A PDF link alone is not evidence of full-text retrieval.

Documents without authors or dates remain available for thematic exploration.
Each analysis reports eligible documents, corpus total, exclusion reasons and
coverage by source type. Coverage does not establish representativeness or
statistical sufficiency. Legacy ambiguous dates require human review for temporal
comparison. A URL domain is not an author, identified publisher or event location.

\subsection{Descriptive models and review}
The document--concept matrix uses 1 for reviewed presence, 0 only for absence
after explicit concept review, and missing values for unreviewed cases.
Source--concept proportions use concept-specific reviewed denominators.
Actor--concept--stance counts keep support, rejection and ambivalence separate,
requiring a verbatim quotation and reviewed speaker attribution.
Directed relationships retain their type, document and supporting quotation.
Causation asserted in a text is not an estimated causal effect.
Temporal counts cover the intersection of reviewed and explicitly dated
documents, with coverage reported. They do not estimate population attitudes.

Existing heuristic modules produce exploratory candidates.
\texttt{evidence\_model.py} checks metadata states and quotations, not disciplinary
truth. JSON reviews are preserved through corpus export. Reception must be
supported by response evidence, not inferred from a message alone.
Documents can depend on the same institution or event; inferential testing and
diffusion estimation are not implemented by these descriptive counts.

\subsection{Pseudocode}
\begin{enumerate}
\item Retrieve content and provenance; search labelled metadata when possible.
\item Preserve field values, evidence, states, conflicts and date precision.
\item Separate publication, update, consultation and search year.
\item Check requirements per analysis; record inclusion or exclusion reason.
\item Check verbatim quotations and attribution in submitted reviews.
\item Build matrices with missing values distinct from zero; preserve stance categories.
\item Export coverage, matrices, relations and limitations of the used subset.
\end{enumerate}
The complete policy and reproducible commands are in
\texttt{EVIDENCIA\_Y\_MODELOS.md}. Updating the software does not turn historical
reports into new measurements.

\subsection{Shared corpus contract}
Identity and evidence-preserving merging are centralized in
\texttt{corpus\_contract.py}, shared by the interface and command line tools.
Identifier URL parameters, retrieval provenance, text variants and conflicts are
retained. Similar titles do not establish document identity. Lexical non-detection
in recovered fragments does not prove intentional silence. Annual dates do not
establish within-year order. Relational exports retain empty reviewed-model tables
when evidence is insufficient. The integral audit documents pilot limits.

\subsection{Versioned records and stages}
Document, version and retrieval identities are separate. Reviewed selection
requires rationale, evidence and reviewer; changes invalidate prior reviews.
Titles, abstracts and fragments remain distinct. Six stages retain integrity
checked checkpoints for resumption. Saved-corpus processing organizes existing
evidence rather than simulating new retrievals. Query caching, bounded retries,
transactional storage and atomic writes support the versioned corpus contract.
