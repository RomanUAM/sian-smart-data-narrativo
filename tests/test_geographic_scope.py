import unittest
from geographic_scope import MEXICO_ENTITIES, scope_terms
from news_spider import passes_geographic_filter
from historical_sources import plan

class TerritoryTests(unittest.TestCase):
    def test_mexico_includes_all_entities_without_manual_terms(self):
        self.assertEqual(len(MEXICO_ENTITIES), 32)
        for entity in MEXICO_ENTITIES:
            accepted, reason = passes_geographic_filter('México', [], '', '', f'Expo de tatuaje en {entity}', '')
            self.assertTrue(accepted, (entity, reason))

    def test_mexican_publisher_does_not_make_foreign_subject_mexican(self):
        accepted, _ = passes_geographic_filter('México', [], 'https://www.medio.com.mx', 'Prensa mexicana', 'Tatuadores de Berlín', 'Exposición en Alemania', country='MX')
        self.assertFalse(accepted)

    def test_custom_scope_does_not_expand_to_country(self):
        self.assertEqual(scope_terms('Personalizado', ['Puebla']), ['Puebla'])
        accepted, _ = passes_geographic_filter('Personalizado', ['Puebla'], '', '', 'Tatuaje en Sonora', '')
        self.assertFalse(accepted)

    def test_aliases_custom_terms_and_plan_are_preserved(self):
        terms = scope_terms('Mexico', ['México', 'Tijuana'])
        self.assertIn('Tijuana', terms)
        self.assertIn('CDMX', terms)
        tasks = plan(dict(query='tatuaje', start_year=2020, end_year=2020, geographic_scope='México', geographic_terms=[], source_modes=['google_news_rss']))
        self.assertTrue(tasks)
        self.assertTrue(all('Tamaulipas' in task['geographic_terms'] for task in tasks))

    def test_ambiguous_names_need_place_context(self):
        for title in ['Tatuaje de un guerrero', 'Tatuaje de un perro chihuahua', 'La salsa Tabasco inspira tatuajes']:
            accepted, _ = passes_geographic_filter('México', [], '', '', title, '')
            self.assertFalse(accepted, title)
        accepted, _ = passes_geographic_filter('México', [], '', '', 'Tatuadores en Guerrero', '')
        self.assertTrue(accepted)
