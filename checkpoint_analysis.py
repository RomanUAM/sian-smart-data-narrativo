"""Descriptive readiness report from one consistent saved snapshot."""
from collections import Counter
import datetime as dt


def analyze(rows, coverage):
    usable = [r for r in rows if (r.get('text_clean') or r.get('pdf_text_clean') or '').strip()]
    selected = sum(r['selected'] for r in coverage.get('annual', []))
    sources = Counter(r.get('source_type') or 'unknown' for r in usable)
    return {
        'generated_at': dt.datetime.now(dt.UTC).isoformat(),
        'records_retained': len(rows), 'records_with_text': len(usable),
        'records_selected': selected, 'annual': coverage.get('annual', []),
        'source_types_with_text': dict(sources),
        'uses': [
            {'use': 'Exploración temática y lectura cualitativa', 'available': bool(usable),
             'condition': 'Revisar texto, procedencia y pertinencia; no equivale a opinión pública.'},
            {'use': 'Comparación entre tipos de fuente', 'available': len(sources) >= 2,
             'condition': 'Comparar tamaños y sesgos; disponer de dos tipos no garantiza balance.'},
            {'use': 'Descripción temporal de la muestra seleccionada', 'available': selected > 0,
             'condition': 'Usar sólo fechas verificadas; reportar vacíos y periodo actual incompleto.'},
            {'use': 'Redes de actores, conceptos y posturas', 'available': bool(usable),
             'condition': 'El texto permite iniciar extracción; relaciones y posturas requieren revisión humana.'},
        ],
        'limits': ['La cuota anual es una meta, no una garantía ni prueba de representatividad.',
                   'Este reporte describe disponibilidad; no estima causalidad ni valida narrativas automáticamente.'],
    }


def markdown(report):
    lines = ['# Avance y usos posibles', '', f"Actualizado: {report['generated_at']}", '',
             f"Registros conservados: {report['records_retained']}; con texto: {report['records_with_text']}; seleccionados: {report['records_selected']}.", '',
             '| Año | Meta | Seleccionados | Faltan |', '|---|---:|---:|---:|']
    lines += [f"| {r['year']} | {r['target']} | {r['selected']} | {r['gap']} |" for r in report['annual']]
    lines += ['', '## Usos posibles', '']
    lines += [f"- {u['use']}: {'hay insumos para iniciar' if u['available'] else 'faltan insumos'}. {u['condition']}" for u in report['uses']]
    lines += ['', '## Límites', ''] + ['- ' + x for x in report['limits']]
    return '\n'.join(lines) + '\n'
