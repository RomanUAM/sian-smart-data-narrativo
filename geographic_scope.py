"""Territorial discovery terms; matches remain geographic signals for review."""
import unicodedata

MEXICO_ENTITIES = (
    'Aguascalientes', 'Baja California', 'Baja California Sur', 'Campeche',
    'Chiapas', 'Chihuahua', 'Ciudad de México', 'Coahuila', 'Colima', 'Durango',
    'Guanajuato', 'Guerrero', 'Hidalgo', 'Jalisco', 'Estado de México',
    'Michoacán', 'Morelos', 'Nayarit', 'Nuevo León', 'Oaxaca', 'Puebla',
    'Querétaro', 'Quintana Roo', 'San Luis Potosí', 'Sinaloa', 'Sonora',
    'Tabasco', 'Tamaulipas', 'Tlaxcala', 'Veracruz', 'Yucatán', 'Zacatecas',
)
AMBIGUOUS_MEXICO_NAMES = {'chihuahua', 'durango', 'guerrero', 'hidalgo', 'morelos', 'sonora', 'tabasco'}
MEXICO_ALIASES = ('Mexico', 'México', 'Mexican', 'mexicano', 'mexicana', 'mexicanos', 'mexicanas', 'CDMX', 'Edomex', 'Distrito Federal')


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).lower() if not unicodedata.combining(c)).strip()


def scope_terms(scope, terms=None):
    # Only national Mexico expands. Custom regional frames remain user-defined.
    values = list(terms or [])
    if normalized(scope) in {'mexico', 'mx'}:
        values = [*MEXICO_ALIASES, *MEXICO_ENTITIES, *values]
    seen, result = set(), []
    for value in values:
        key = normalized(value)
        if key and key not in seen:
            seen.add(key); result.append(str(value).strip())
    return result
