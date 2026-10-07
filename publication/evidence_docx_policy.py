"""Keep generated Word documents consistent with the evidence policy."""


def append_evidence_policy(doc, english=False):
    title = "Available evidence and analysis requirements — October 6, 2026" if english else "Evidencia disponible y requisitos de análisis — 6 de octubre de 2026"
    if any(p.text == title for p in doc.paragraphs):
        return
    doc.add_page_break()
    doc.add_heading(title, level=1)
    paragraphs = [
        "Authorship, dates and outlets are sought, not guaranteed. Preserve value, evidence, method and state: explicit, inferred, searched but not found, not evaluable, not applicable or conflicting.",
        "Publication, update and consultation dates are distinct. Never fill missing date components or use search year as publication. A PDF link does not establish full-text retrieval.",
        "A document without an author or date remains available for analyses whose requirements it meets. Report eligible/total, exclusion reasons and coverage by source type. Coverage is not representativeness.",
        "Reviewed document–concept matrices distinguish presence (1), explicitly reviewed absence (0) and unknown (missing). Source proportions use concept-specific reviewed denominators. Support, rejection and ambivalence remain separate.",
        "Claims and relationships require reviewed interpretation and a verbatim quotation. Attributed causality is not a causal effect. Temporal counts use the intersection of reviewed and dated documents. Existing heuristic modules produce candidates, not validated social conclusions.",
        "Pseudocode: retrieve provenance and text; seek metadata; preserve states and conflicts; check requirements per analysis; validate quotations; construct descriptive matrices; export coverage and limitations. See EVIDENCIA_Y_MODELOS.md for the executable workflow.",
    ] if english else [
        "Autoría, fechas y fuente se buscan, pero no se garantiza recuperarlas. Cada campo conserva valor, evidencia, método y estado: explícito, inferido, buscado y no encontrado, no evaluable, no aplica o contradictorio.",
        "Publicación, actualización y consulta son fechas distintas. No se completan componentes ni se usa el año de búsqueda como publicación. Un enlace PDF no acredita texto completo recuperado.",
        "Un documento sin autor o fecha sigue disponible para los análisis cuyos requisitos cumpla. Se reportan utilizables/total, exclusiones y cobertura por tipo de fuente. La cobertura no es representatividad.",
        "La matriz documento–concepto distingue presencia revisada (1), ausencia explícitamente revisada (0) y dato desconocido (faltante). Las proporciones por fuente usan denominadores revisados para cada concepto. Apoyo, rechazo y ambivalencia permanecen separados.",
        "Afirmaciones y relaciones requieren interpretación revisada y cita literal. La causalidad atribuida no es un efecto causal demostrado. Los conteos temporales usan la intersección revisada y fechada. Los módulos heurísticos anteriores generan candidatos, no conclusiones sociales validadas.",
        "Pseudocódigo: recuperar procedencia y texto; buscar metadatos; conservar estados y conflictos; comprobar requisitos por análisis; validar citas; construir matrices descriptivas; exportar cobertura y limitaciones. El procedimiento ejecutable está en EVIDENCIA_Y_MODELOS.md.",
    ]
    paragraphs.append("Identity and evidence-preserving merging use the same shared corpus contract in the interface and command line tools. Similar titles and lexical non-detection do not establish document identity or intentional silence. See the integral audit for pilot limits." if english else "Identidad y fusión de evidencia usan el mismo contrato de corpus en interfaz y comandos. Títulos similares y falta de detección léxica no acreditan identidad documental ni silencio intencional. El informe de auditoría integral documenta los límites del piloto.")
    paragraphs.append("The v2 contract separates documents, versions and retrievals; supports resumable stages, bounded source retries, caching and transactional storage. Saved-corpus processing does not simulate new downloads or human review." if english else "El contrato v2 separa documentos, versiones y recuperaciones; incorpora etapas reanudables, reintentos limitados, caché y almacenamiento transaccional. El procesamiento de corpus guardados no simula nuevas descargas ni revisión humana. La especificación y pseudocódigo están en ARQUITECTURA_REGISTROS_V2.md.")
    for text in paragraphs:
        doc.add_paragraph(text)
