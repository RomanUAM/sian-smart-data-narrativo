#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Iterable


def canonical_domain(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if value.startswith(("http://", "https://")) else "https://" + value)
    domain = (parsed.netloc or parsed.path).lower().strip("/")
    return domain.removeprefix("www.")


NEWS_SOURCE_PROFILES: list[dict] = [
    {
        "medium": "La Jornada",
        "domain": "jornada.com.mx",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.jornada.com.mx/noticia/YYYY/MM/DD/SECCION/SLUG"],
        "sections": ["cultura", "sociedad", "estados", "capital", "ciencia", "politica"],
        "tail_cut_markers": ["más de cultura", "más de sociedad", "más de estados", "más de capital", "la jornada de oriente"],
        "notes": "Medio mexicano con URLs fechadas; útil como fuente semilla y búsqueda por dominio.",
    },
    {
        "medium": "Milenio",
        "domain": "milenio.com",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.milenio.com/SECCION/SLUG"],
        "sections": ["cultura", "politica", "estados", "virales", "estilo"],
        "tail_cut_markers": ["últimas noticias", "te recomendamos", "más noticias", "lo más visto"],
        "notes": "Medio mexicano generalista; suele requerir poda de recomendaciones.",
    },
    {
        "medium": "El Universal",
        "domain": "eluniversal.com.mx",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.eluniversal.com.mx/SECCION/SLUG"],
        "sections": ["cultura", "nacion", "metropoli", "estados", "espectaculos"],
        "tail_cut_markers": ["únete a nuestro canal", "recibe nuestro newsletter", "más leídas", "también lee"],
        "notes": "Medio mexicano de alta cobertura; limpiar módulos de recomendación.",
    },
    {
        "medium": "Aristegui Noticias",
        "domain": "aristeguinoticias.com",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://aristeguinoticias.com/DDMM/SECCION/SLUG"],
        "sections": ["mexico", "mundo", "cultura", "sociedad"],
        "tail_cut_markers": ["también te puede interesar", "lo más destacado", "comentarios"],
        "notes": "Medio mexicano; útil para narrativa pública y controversias.",
    },
    {
        "medium": "NMAS",
        "domain": "nmas.com.mx",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.nmas.com.mx/SECCION/SLUG"],
        "sections": ["nmas-local", "nacional", "entretenimiento", "ciencia"],
        "tail_cut_markers": ["síguenos en", "más noticias", "últimas noticias", "publicidad"],
        "notes": "Fuente televisiva/digital mexicana; puede producir textos breves, por eso no debe descartarse sólo por longitud.",
    },
    {
        "medium": "Proceso",
        "domain": "proceso.com.mx",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.proceso.com.mx/SECCION/YYYY/MM/DD/SLUG"],
        "sections": ["cultura", "nacional", "internacional", "reportajes"],
        "tail_cut_markers": ["suscríbete", "newsletter", "también te puede interesar"],
        "notes": "Cobertura periodística robusta, pero parte del contenido puede ser parcial.",
    },
    {
        "medium": "Animal Político",
        "domain": "animalpolitico.com",
        "country": "MX",
        "region": "Mexico",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://animalpolitico.com/SECCION/SLUG"],
        "sections": ["sociedad", "genero-y-diversidad", "verificacion", "cultura"],
        "tail_cut_markers": ["apóyanos", "lo último", "también puedes leer"],
        "notes": "Buena fuente para discusión social y verificación.",
    },
    {
        "medium": "BBC Mundo",
        "domain": "bbc.com",
        "country": "GB",
        "region": "Global",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.bbc.com/mundo/SLUG"],
        "sections": ["mundo", "ciencia", "cultura", "noticias"],
        "tail_cut_markers": ["puedes recibir notificaciones", "síguenos en", "lee también"],
        "notes": "Medio británico con edición en español; útil para comparar narrativas globales.",
    },
    {
        "medium": "The Guardian",
        "domain": "theguardian.com",
        "country": "GB",
        "region": "United Kingdom",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.theguardian.com/SECTION/YYYY/MM/DD/SLUG"],
        "sections": ["society", "culture", "world", "technology", "lifeandstyle"],
        "tail_cut_markers": ["most viewed", "more on this story", "sign up to", "support the guardian"],
        "notes": "Medio británico abierto; útil para contrapunto anglófono.",
    },
    {
        "medium": "BBC News",
        "domain": "bbc.co.uk",
        "country": "GB",
        "region": "United Kingdom",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.bbc.co.uk/news/SLUG"],
        "sections": ["news", "culture", "technology", "health"],
        "tail_cut_markers": ["more on this story", "related topics", "follow bbc"],
        "notes": "Fuente británica internacional, frecuentemente indexada por GDELT/Google News.",
    },
    {
        "medium": "Reuters",
        "domain": "reuters.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.reuters.com/SECTION/SLUG-DATE/"],
        "sections": ["world", "business", "technology", "lifestyle"],
        "tail_cut_markers": ["our standards", "read next", "editing by"],
        "notes": "Agencia internacional; muchas páginas son extractables, otras pueden quedar parciales.",
    },
    {
        "medium": "Associated Press",
        "domain": "apnews.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://apnews.com/article/SLUG"],
        "sections": ["world-news", "entertainment", "health", "science"],
        "tail_cut_markers": ["related coverage", "follow", "advertisement"],
        "notes": "Agencia estadounidense abierta; útil para cobertura factual.",
    },
    {
        "medium": "CNN",
        "domain": "cnn.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.cnn.com/YYYY/MM/DD/SECTION/SLUG"],
        "sections": ["world", "health", "style", "culture"],
        "tail_cut_markers": ["more from cnn", "sign up", "related article"],
        "notes": "Medio estadounidense; limpiar promos y videos embebidos.",
    },
    {
        "medium": "NPR",
        "domain": "npr.org",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.npr.org/YYYY/MM/DD/ID/SLUG"],
        "sections": ["culture", "health", "science", "world"],
        "tail_cut_markers": ["copyright", "transcript", "support npr"],
        "notes": "Fuente estadounidense con textos largos y transcripciones.",
    },
    {
        "medium": "The New York Times",
        "domain": "nytimes.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "paywall",
        "source_type": "news",
        "url_patterns": ["https://www.nytimes.com/YYYY/MM/DD/SECTION/SLUG.html"],
        "sections": ["world", "style", "health", "arts"],
        "tail_cut_markers": ["subscribe", "advertisement", "more in"],
        "notes": "Usar como índice/metadato salvo que haya acceso autorizado; no garantiza texto completo.",
    },
    {
        "medium": "The Washington Post",
        "domain": "washingtonpost.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "paywall",
        "source_type": "news",
        "url_patterns": ["https://www.washingtonpost.com/SECTION/YYYY/MM/DD/SLUG/"],
        "sections": ["world", "lifestyle", "health", "technology", "opinions"],
        "tail_cut_markers": ["subscribe", "advertisement", "more from", "sign in"],
        "notes": "Fuente estadounidense de referencia; usar como índice/metadato si no hay acceso completo.",
    },
    {
        "medium": "Los Angeles Times",
        "domain": "latimes.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.latimes.com/SECTION/story/YYYY-MM-DD/SLUG"],
        "sections": ["california", "world-nation", "lifestyle", "entertainment", "science"],
        "tail_cut_markers": ["advertisement", "more to read", "subscriber exclusive"],
        "notes": "Medio estadounidense útil para cultura, sociedad y migración.",
    },
    {
        "medium": "Vox",
        "domain": "vox.com",
        "country": "US",
        "region": "United States",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.vox.com/SECTION/YYYY/MM/DD/SLUG"],
        "sections": ["culture", "policy", "science", "technology", "world"],
        "tail_cut_markers": ["more from vox", "sign up", "advertisement"],
        "notes": "Medio explicativo útil para marcos narrativos culturales y políticos.",
    },
    {
        "medium": "The Independent",
        "domain": "independent.co.uk",
        "country": "GB",
        "region": "United Kingdom",
        "language": "English",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.independent.co.uk/SECTION/SLUG.html"],
        "sections": ["news", "life-style", "arts-entertainment", "tech"],
        "tail_cut_markers": ["recommended", "more about", "join our commenting forum"],
        "notes": "Medio británico generalista; puede requerir limpieza fuerte de recomendaciones.",
    },
    {
        "medium": "Financial Times",
        "domain": "ft.com",
        "country": "GB",
        "region": "United Kingdom",
        "language": "English",
        "access": "paywall",
        "source_type": "news",
        "url_patterns": ["https://www.ft.com/content/ID"],
        "sections": ["world", "companies", "technology", "opinion"],
        "tail_cut_markers": ["subscribe", "sign in", "copyright"],
        "notes": "Útil como índice de prensa económica; no asumir texto completo sin acceso.",
    },
    {
        "medium": "El País",
        "domain": "elpais.com",
        "country": "ES",
        "region": "Europe",
        "language": "Spanish",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://elpais.com/SECCION/YYYY-MM-DD/SLUG.html"],
        "sections": ["sociedad", "cultura", "tecnologia", "internacional", "mexico"],
        "tail_cut_markers": ["suscríbete", "lo más visto", "newsletter", "más información"],
        "notes": "Medio español con cobertura iberoamericana; útil para contraste transnacional.",
    },
    {
        "medium": "Le Monde",
        "domain": "lemonde.fr",
        "country": "FR",
        "region": "Europe",
        "language": "French",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.lemonde.fr/SECTION/article/YYYY/MM/DD/SLUG_ID.html"],
        "sections": ["societe", "culture", "international", "sciences", "pixels"],
        "tail_cut_markers": ["lire aussi", "les plus lus", "abonnez-vous", "publicité"],
        "notes": "Medio francés de referencia; útil si el estudio compara circulación europea.",
    },
    {
        "medium": "Deutsche Welle",
        "domain": "dw.com",
        "country": "DE",
        "region": "Europe",
        "language": "Multilingual",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.dw.com/LANGUAGE/SLUG/a-ID"],
        "sections": ["world", "culture", "science", "technology", "latin-america"],
        "tail_cut_markers": ["related topics", "more stories", "skip next section", "advertisement"],
        "notes": "Medio público alemán multilingüe, útil para perspectiva internacional abierta.",
    },
    {
        "medium": "France 24",
        "domain": "france24.com",
        "country": "FR",
        "region": "Europe",
        "language": "Multilingual",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.france24.com/LANGUAGE/SECTION/YYYYMMDD-SLUG"],
        "sections": ["world", "culture", "science", "americas", "france"],
        "tail_cut_markers": ["also on france 24", "most read", "advertising"],
        "notes": "Medio internacional abierto con versiones en varios idiomas.",
    },
    {
        "medium": "Al Jazeera",
        "domain": "aljazeera.com",
        "country": "QA",
        "region": "Global",
        "language": "English",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.aljazeera.com/SECTION/YYYY/MM/DD/SLUG"],
        "sections": ["news", "features", "opinion", "economy", "culture"],
        "tail_cut_markers": ["related", "most read", "advertisement"],
        "notes": "Medio global abierto; útil para contrastar marcos no occidentales.",
    },
    {
        "medium": "Folha de S.Paulo",
        "domain": "folha.uol.com.br",
        "country": "BR",
        "region": "Brazil",
        "language": "Portuguese",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www1.folha.uol.com.br/SECAO/YYYY/MM/SLUG.shtml"],
        "sections": ["cotidiano", "cultura", "mundo", "saude", "tec"],
        "tail_cut_markers": ["mais lidas", "newsletter", "publicidade", "assine"],
        "notes": "Medio brasileño; útil si el tópico requiere comparación lusófona.",
    },
    {
        "medium": "G1 Globo",
        "domain": "g1.globo.com",
        "country": "BR",
        "region": "Brazil",
        "language": "Portuguese",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://g1.globo.com/SECAO/noticia/YYYY/MM/DD/SLUG.ghtml"],
        "sections": ["brasil", "mundo", "saude", "ciencia", "pop-arte"],
        "tail_cut_markers": ["veja também", "mais lidas", "publicidade", "siga o g1"],
        "notes": "Portal brasileño generalista con patrón fechado estable.",
    },
    {
        "medium": "Agência Brasil",
        "domain": "agenciabrasil.ebc.com.br",
        "country": "BR",
        "region": "Brazil",
        "language": "Portuguese",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://agenciabrasil.ebc.com.br/SECAO/noticia/YYYY-MM/SLUG"],
        "sections": ["geral", "direitos-humanos", "saude", "cultura"],
        "tail_cut_markers": ["compartilhe", "mais recentes", "tags"],
        "notes": "Agencia pública brasileña; buen contrapeso regional.",
    },
    {
        "medium": "Estadão",
        "domain": "estadao.com.br",
        "country": "BR",
        "region": "Brazil",
        "language": "Portuguese",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.estadao.com.br/SECAO/SLUG/"],
        "sections": ["brasil", "cultura", "saude", "internacional"],
        "tail_cut_markers": ["mais lidas", "assine", "publicidade"],
        "notes": "Medio brasileño de referencia, a veces parcial.",
    },
    {
        "medium": "O Globo",
        "domain": "oglobo.globo.com",
        "country": "BR",
        "region": "Brazil",
        "language": "Portuguese",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://oglobo.globo.com/SECAO/SLUG"],
        "sections": ["brasil", "mundo", "cultura", "saude", "tecnologia"],
        "tail_cut_markers": ["mais lidas", "publicidade", "assine", "veja também"],
        "notes": "Medio brasileño generalista; útil para corpus lusófono, aunque puede ser parcial.",
    },
    {
        "medium": "UOL",
        "domain": "uol.com.br",
        "country": "BR",
        "region": "Brazil",
        "language": "Portuguese",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.uol.com.br/SECAO/SLUG"],
        "sections": ["noticias", "universa", "vivabem", "tilt", "cultura"],
        "tail_cut_markers": ["mais lidas", "publicidade", "veja também", "assine"],
        "notes": "Portal brasileño amplio; conviene filtrar por sección y limpiar módulos.",
    },
    {
        "medium": "Página/12",
        "domain": "pagina12.com.ar",
        "country": "AR",
        "region": "Latin America",
        "language": "Spanish",
        "access": "open",
        "source_type": "news",
        "url_patterns": ["https://www.pagina12.com.ar/ID-SLUG"],
        "sections": ["sociedad", "cultura", "el-mundo", "ciencia"],
        "tail_cut_markers": ["leer más", "también puede interesarte", "últimas noticias"],
        "notes": "Medio argentino útil para ampliar corpus latinoamericano.",
    },
    {
        "medium": "El Tiempo",
        "domain": "eltiempo.com",
        "country": "CO",
        "region": "Latin America",
        "language": "Spanish",
        "access": "partial",
        "source_type": "news",
        "url_patterns": ["https://www.eltiempo.com/SECCION/SLUG"],
        "sections": ["cultura", "vida", "salud", "mundo"],
        "tail_cut_markers": ["más noticias", "síganos", "boletines"],
        "notes": "Medio colombiano; útil para ampliar región hispanoamericana.",
    },
]

FORUM_SOURCE_PROFILES: list[dict] = [
    {"medium": "Medium", "domain": "medium.com", "country": "Global", "region": "Blogs", "language": "Multilingual", "access": "partial", "source_type": "forum", "notes": "Blogs/ensayos personales; útil como conversación pública no noticiosa."},
    {"medium": "Substack", "domain": "substack.com", "country": "Global", "region": "Blogs", "language": "Multilingual", "access": "partial", "source_type": "forum", "notes": "Newsletters públicas; no tratar como prensa ni artículo académico."},
    {"medium": "WordPress", "domain": "wordpress.com", "country": "Global", "region": "Blogs", "language": "Multilingual", "access": "open", "source_type": "forum", "notes": "Blogs públicos; buena fuente conversacional cuando los foros centralizados bloquean."},
    {"medium": "Blogspot", "domain": "blogspot.com", "country": "Global", "region": "Blogs", "language": "Multilingual", "access": "open", "source_type": "forum", "notes": "Blogs públicos; útil para memoria, experiencia y opinión personal."},
    {"medium": "Tumblr", "domain": "tumblr.com", "country": "Global", "region": "Blogs", "language": "Multilingual", "access": "public_html", "source_type": "forum", "notes": "Microblogs públicos; usar sólo páginas visibles sin sesión."},
    {"medium": "Tattoo.com", "domain": "tattoo.com", "country": "Global", "region": "Tattoo communities", "language": "English", "access": "open", "source_type": "forum", "notes": "Comunidad/portal especializado; clasificar como conversación sectorial si no es nota periodística."},
    {"medium": "Tattoodo", "domain": "tattoodo.com", "country": "Global", "region": "Tattoo communities", "language": "English", "access": "open", "source_type": "forum", "notes": "Portal especializado con textos de cultura visual/tatuaje."},
    {"medium": "Tattooing 101", "domain": "tattooing101.com", "country": "Global", "region": "Tattoo communities", "language": "English", "access": "open", "source_type": "forum", "notes": "Comunidad/formación sectorial; útil para práctica profesional abierta."},
    {"medium": "Tattooers", "domain": "tattooers.net", "country": "Global", "region": "Tattoo communities", "language": "English", "access": "open", "source_type": "forum", "notes": "Directorio/comunidad; usar como señal sectorial si hay texto narrativo."},
    {"medium": "Quora", "domain": "quora.com", "country": "Global", "region": "Public forums", "language": "Multilingual", "access": "partial", "source_type": "forum", "notes": "Muchas páginas son parciales; usar sólo si el texto visible es suficiente."},
    {"medium": "StackExchange", "domain": "stackexchange.com", "country": "Global", "region": "Q&A communities", "language": "Multilingual", "access": "open_api_or_html", "source_type": "forum", "notes": "Sólo aplica a tópicos con comunidades relevantes; no forzar si no hay tema."},
    {"medium": "Dev.to", "domain": "dev.to", "country": "Global", "region": "Professional community", "language": "Multilingual", "access": "open", "source_type": "forum", "notes": "Útil para tópicos tecnológicos; para tatuaje sólo si hay narrativas pertinentes."},
    {
        "medium": "Reddit",
        "domain": "reddit.com",
        "country": "Global",
        "region": "Public forums",
        "language": "Multilingual",
        "access": "open_rss_or_public_html",
        "source_type": "forum",
        "notes": "Usar sólo páginas/RSS públicos; fuente opcional y tardía porque suele limitar con 429. No automatizar sesión ni contenido privado.",
    },
    {"medium": "Old Reddit", "domain": "old.reddit.com", "country": "Global", "region": "Public forums", "language": "Multilingual", "access": "public_html", "source_type": "forum", "notes": "Interfaz pública más estable para páginas indexadas."},
]

DEFAULT_FORUM_DOMAINS = [profile["domain"] for profile in FORUM_SOURCE_PROFILES]

INSTITUTIONAL_SOURCE_PROFILES: list[dict] = [
    {"medium": "Gobierno de México", "domain": "gob.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["salud", "cultura", "economia", "segob"], "notes": "Capa institucional: comunicados, lineamientos y páginas públicas del gobierno federal."},
    {"medium": "Secretaría de Salud", "domain": "salud.gob.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["comunicados", "acciones", "documentos"], "notes": "Útil para regulación sanitaria, riesgos, tintas, infección y salud pública."},
    {"medium": "COFEPRIS", "domain": "cofepris.gob.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["alertas", "comunicados", "acciones"], "notes": "Regulación y alertas sanitarias; importante para tatuajes/tintas/maquillaje permanente."},
    {"medium": "Diario Oficial de la Federación", "domain": "dof.gob.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["normas", "acuerdos"], "notes": "Normatividad; no es conversación social, pero fija marcos institucionales."},
    {"medium": "INEGI", "domain": "inegi.org.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["comunicados", "datos", "programas"], "notes": "Datos públicos; útil para contexto sociodemográfico si aplica."},
    {"medium": "Cámara de Diputados", "domain": "diputados.gob.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["leyes", "boletines", "gaceta"], "notes": "Debate legislativo y normativo."},
    {"medium": "Senado de la República", "domain": "senado.gob.mx", "country": "MX", "region": "Mexico", "language": "Spanish", "access": "open", "source_type": "institutional_report", "sections": ["comunicacion", "gaceta"], "notes": "Debate legislativo y comunicados."},
    {"medium": "WHO", "domain": "who.int", "country": "Global", "region": "Global", "language": "Multilingual", "access": "open", "source_type": "institutional_report", "sections": ["health topics", "news", "publications"], "notes": "Organismo internacional; capa institucional global."},
    {"medium": "PAHO", "domain": "paho.org", "country": "Global", "region": "Latin America", "language": "Multilingual", "access": "open", "source_type": "institutional_report", "sections": ["documents", "news"], "notes": "Organismo regional de salud para América Latina."},
    {"medium": "UNESCO", "domain": "unesco.org", "country": "Global", "region": "Global", "language": "Multilingual", "access": "open", "source_type": "institutional_report", "sections": ["culture", "news", "reports"], "notes": "Cultura, patrimonio y políticas culturales."},
]

COMMON_NEWS_TAIL_CUT_MARKERS = [
    "related posts",
    "related articles",
    "more stories",
    "more from",
    "recommended articles",
    "about the author",
    "author bio",
    "ultimas noticias",
    "últimas noticias",
    "mas de cultura",
    "más de cultura",
    "mas de sociedad",
    "más de sociedad",
    "mas de estados",
    "más de estados",
    "mas de capital",
    "más de capital",
    "mas de ciencia",
    "más de ciencia",
    "mas de opinion",
    "más de opinión",
    "publicidad comercial",
    "quienes somos",
    "¿quiénes somos",
    "copyright",
    "todos los derechos reservados",
    "advertisement",
    "newsletter",
    "subscribe",
    "suscríbete",
    "lo más visto",
    "más leídas",
]


def source_tail_cut_markers(url_or_domain: str) -> list[str]:
    domain = canonical_domain(url_or_domain)
    markers: list[str] = []
    for profile in NEWS_SOURCE_PROFILES:
        if domain.endswith(profile["domain"]):
            markers.extend(profile.get("tail_cut_markers", []))
    return list(dict.fromkeys(markers))


def source_access_policy(url_or_domain: str) -> dict:
    """Return the configured access policy for a public source domain.

    The spider uses this as a conservative guardrail: sources marked as
    ``partial`` or ``paywall`` can still contribute metadata, but their visible
    text should not be treated as a full article unless the user adds a separate
    authorized-access workflow.
    """
    domain = canonical_domain(url_or_domain)
    if not domain:
        return {"access": "unknown", "source_type": "", "medium": "", "domain": "", "country": "", "region": ""}
    for profile in [*NEWS_SOURCE_PROFILES, *FORUM_SOURCE_PROFILES, *INSTITUTIONAL_SOURCE_PROFILES]:
        profile_domain = canonical_domain(profile.get("domain", ""))
        if profile_domain and domain.endswith(profile_domain):
            return {
                "access": str(profile.get("access") or "unknown"),
                "source_type": str(profile.get("source_type") or ""),
                "medium": str(profile.get("medium") or ""),
                "domain": profile_domain,
                "country": str(profile.get("country") or ""),
                "region": str(profile.get("region") or ""),
            }
    return {"access": "unknown", "source_type": "", "medium": "", "domain": domain, "country": "", "region": ""}


def profile_domains(
    regions: Iterable[str] | None = None,
    countries: Iterable[str] | None = None,
    languages: Iterable[str] | None = None,
    include_paywalled: bool = False,
    source_types: Iterable[str] | None = None,
) -> list[str]:
    region_set = {str(item).lower() for item in regions or [] if str(item).strip()}
    country_set = {str(item).upper() for item in countries or [] if str(item).strip()}
    language_set = {str(item).lower() for item in languages or [] if str(item).strip()}
    domains: list[str] = []
    source_type_set = {str(item).lower() for item in source_types or [] if str(item).strip()}
    for profile in [*NEWS_SOURCE_PROFILES, *INSTITUTIONAL_SOURCE_PROFILES]:
        if not include_paywalled and profile.get("access") == "paywall":
            continue
        if source_type_set and str(profile.get("source_type", "")).lower() not in source_type_set:
            continue
        if region_set and str(profile.get("region", "")).lower() not in region_set:
            continue
        if country_set and str(profile.get("country", "")).upper() not in country_set:
            continue
        if language_set and str(profile.get("language", "")).lower() not in language_set:
            continue
        domain = canonical_domain(profile["domain"])
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def source_profile_rows(domains: Iterable[str] | None = None, include_forums: bool = False) -> list[dict]:
    requested = {canonical_domain(domain) for domain in domains or [] if canonical_domain(domain)}
    profiles = [*NEWS_SOURCE_PROFILES, *INSTITUTIONAL_SOURCE_PROFILES, *(FORUM_SOURCE_PROFILES if include_forums else [])]
    rows = []
    for profile in profiles:
        domain = canonical_domain(profile["domain"])
        if requested and domain not in requested:
            continue
        rows.append(
            {
                "medium": profile.get("medium", ""),
                "domain": domain,
                "country": profile.get("country", ""),
                "region": profile.get("region", ""),
                "language": profile.get("language", ""),
                "access": profile.get("access", ""),
                "source_type": profile.get("source_type", ""),
                "url_patterns": "; ".join(profile.get("url_patterns", [])),
                "sections": ", ".join(profile.get("sections", [])),
                "notes": profile.get("notes", ""),
            }
        )
    return rows


def domains_from_seed_file(seed_file: str) -> list[str]:
    if not seed_file:
        return []
    path = Path(seed_file)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    domains: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        domain = canonical_domain(str(item.get("url") or ""))
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def source_strategy_rows_from_seed_file(
    seed_file: str,
    query: str,
    variants: list[str],
    geographic_terms: list[str],
) -> list[dict]:
    if not seed_file:
        return []
    path = Path(seed_file)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    grouped: dict[str, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        domain = canonical_domain(url)
        if not domain:
            continue
        parsed = urllib.parse.urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
        medium = str(item.get("medium") or item.get("medio") or domain)
        parts = [part for part in parsed.path.split("/") if part]
        section = ""
        if domain.endswith("jornada.com.mx") and len(parts) >= 5 and parts[0] == "noticia":
            section = parts[4]
            pattern = "https://www.jornada.com.mx/noticia/YYYY/MM/DD/SECCION/SLUG"
        elif len(parts) >= 1:
            section = parts[0]
            pattern = f"https://{domain}/<seccion>/<slug>"
        else:
            pattern = f"https://{domain}/<slug>"
        row = grouped.setdefault(
            domain,
            {
                "medium": medium,
                "domain": domain,
                "seed_urls": 0,
                "sections": Counter(),
                "years": Counter(),
                "url_pattern": pattern,
            },
        )
        row["seed_urls"] += 1
        if section:
            row["sections"][section] += 1
        date = str(item.get("date") or item.get("fecha") or item.get("published_date") or "")
        year = date[-4:] if len(date) >= 4 and date[-4:].isdigit() else date[:4] if date[:4].isdigit() else ""
        if year:
            row["years"][year] += 1

    def build_query(domain: str) -> str:
        terms = [query, *variants]
        unique_terms = []
        for term in terms:
            term = str(term).strip()
            if term and term.lower() not in {item.lower() for item in unique_terms}:
                unique_terms.append(term)
        topic = " OR ".join(f'"{term}"' if " " in term else term for term in unique_terms)
        geo = " OR ".join(f'"{term}"' if " " in term else term for term in geographic_terms if term)
        parts = [f"({topic})" if topic else ""]
        if geo:
            parts.append(f"({geo})")
        parts.append(f"(domain:{domain})")
        return " ".join(part for part in parts if part)

    rows = []
    for domain, row in sorted(grouped.items(), key=lambda pair: (-pair[1]["seed_urls"], pair[0])):
        rows.append(
            {
                "medium": row["medium"],
                "domain": domain,
                "seed_urls": row["seed_urls"],
                "dominant_sections": ", ".join(section for section, _ in row["sections"].most_common(6)),
                "years_seen": ", ".join(year for year, _ in sorted(row["years"].items())),
                "url_pattern": row["url_pattern"],
                "recommended_query": build_query(domain),
                "strategy": "1) extraer URLs semilla; 2) ampliar por domain:medio + variantes; 3) limpiar con perfil del medio; 4) fusionar JSON.",
            }
        )
    return rows
