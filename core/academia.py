# ==============================================================================
#  «Aprende a Monetizar» — Copyright © 2026 CanalFantasmaYT. All rights reserved.
#  Todos los derechos reservados. Este archivo NO está bajo la licencia MIT.
#  This file is NOT under the MIT License. See METHODOLOGY_LICENSE.md.
# ==============================================================================
"""Conocimiento de Aprende a Monetizar, resumido para NichosForge Pro.

Lo usan: Nichi (como contexto de la IA y en modo guía), el buscador aleatorio de canales automatizados,
la detección de canal automatizado / audiencia y la sección Aprende a Monetizar del panel.
"""
import random

SECCIONES = [
    {"id": "base", "icono": "🎯", "titulo": "La idea base", "puntos": [
        "Los suscriptores casi no importan: más VISITAS = más ingresos.",
        "Bola de nieve: más videos = más posibilidades de ganar. Lo pequeño de cada día se vuelve grande en meses.",
        "Secreto #1 · Tickets de lotería: más videos = más probabilidad de viralizar. Meta: 1 video diario. Regla 80/20.",
        "Secreto #2 · Formatos simples y replicables con edición simple (casos: historias para adultos mayores, banco de videos stock, historias de terror).",
        "Automatización en una frase: copia lo que funciona. «La creatividad no existe, no hay que inventar la rueda» (Roba como un artista, Austin Kleon).",
        "Lo que ya funcionó en YouTube es altamente probable que siga funcionando.",
    ]},
    {"id": "algoritmo", "icono": "⚙️", "titulo": "Cómo funciona el algoritmo", "puntos": [
        "Pilar 1 · Comportamiento del usuario: qué vio, cuánto tiempo, sus interacciones, patrones de consumo, frecuencia con un canal, ubicación, idioma y tendencias locales.",
        "Pilar 2 · Métricas del video: CTR (clics tras ver miniatura y título), tiempo de visualización, porcentaje de retención e interacciones.",
        "Pilar 3 · Engagement: comentarios, compartidos y likes. Un video muy interactuado es visto como interesante y se empuja más.",
        "Secciones de tráfico: Inicio (más del 70 % de las visitas; ganas con miniatura + título), Sugeridos, Búsqueda (SEO), Tendencias y Shorts (algoritmo distinto).",
    ]},
    {"id": "capas", "icono": "🧱", "titulo": "Sistema modular: las 5 capas", "puntos": [
        "Capa 1 · Núcleo (nicho): la más importante y la que más tiempo exige. Un nicho de alto impacto perdona errores en todo lo demás.",
        "Capa 2 · Radar (análisis de mercado): dice si el nicho está saturado, si aún es rentable o si ya va en declive. Sin radar caminas a ciegas.",
        "Capa 3 · Big Bang Content: calendario estratégico de ideas para explotar los canales.",
        "Capa 4 · Atracción: títulos y miniaturas (el packing). Es la carta de presentación para ganar el clic.",
        "Capa 5 · Arquitectura: sistemas de delegación, ejecución y orden para manejar varios canales a la vez, 24/7.",
        "Las capas son independientes pero conectadas: si una falla, la siguiente rinde a la mitad.",
    ]},
    {"id": "tipos", "icono": "🤖", "titulo": "Tipos de canal y canal automatizado", "puntos": [
        "Marca personal: una persona siempre a cámara y en las miniaturas; el branding gira en torno a ella; calidad sobre cantidad; pocos videos.",
        "Marca empresarial / ecosistema: varias personas, branding corporativo, promueve un producto o servicio.",
        "Canal AUTOMATIZADO (sin rostro): nadie aparece a cámara; narración, stock, IA, animaciones o contenido de terceros; volumen de videos alto; miniaturas sin un rostro propio (pueden salir rostros del tema); branding global; mucho clickbait visual y verbal.",
        "El canal automatizado está pensado para escalar, delegar y automatizar.",
        "Error de principiante: analizar el tipo de canal equivocado. Para replicar, estudia canales automatizados.",
    ]},
    {"id": "nicho", "icono": "🪆", "titulo": "Nicho, subnicho y micronicho", "puntos": [
        "Nicho = grupo general (Comida, Fútbol). Subnicho = grupo específico (Postres, Errores del fútbol). Micronicho = aún más específico (Pasteles, Errores de Messi).",
        "Entre más específico, mayor posibilidad de éxito.",
        "Claridad de nicho: un canal con claridad trata siempre el mismo tema, formato y estilo visual.",
    ]},
    {"id": "mercado", "icono": "📡", "titulo": "Análisis de mercado y referentes", "puntos": [
        "Oferta = competidores: canales del mismo nicho en tu idioma (español). Dicen qué tan saturado está el mercado.",
        "Referentes = fuente de ideas validadas: normalmente canales en INGLÉS; de ellos se replica la mayor cantidad de contenido.",
        "Demanda = volumen de visitas del nicho.",
        "Criterios de referente: mínimo 5 canales, creados hace máximo 1 año, con 1 millón de visitas en un mes.",
        "El mercado inglés va años adelante: lo que ya no rinde allá puede no haber llegado aún al mercado latino.",
        "Análisis de rentabilidad: si el volumen de visitas da para ingresos que valgan la pena, entra; si no, no.",
    ]},
    {"id": "techos", "icono": "📏", "titulo": "Techos y pisos", "puntos": [
        "Techo: el video con más visitas del canal (su pico). Solo cuenta si está dentro del nicho que quieres replicar.",
        "Piso: el promedio de los videos con menos visitas. Muestra qué tan estable es el canal en su peor momento.",
        "Se usan cuando un canal tiene pocas visitas al mes pero el nicho parece bueno: puede ser que le falte estrategia, tenga errores o pocos videos.",
    ]},
    {"id": "contenido", "icono": "🌲", "titulo": "Evergreen, trendy y mixto", "puntos": [
        "Evergreen: crecimiento progresivo; las visitas se reparten y siguen llegando con el tiempo.",
        "Trendy: depende de la popularidad del tema; picos virales que luego caen.",
        "Mixto: combinación de los dos métodos.",
    ]},
    {"id": "dinero", "icono": "💵", "titulo": "RPM, CPM y cómo subirlo", "puntos": [
        "RPM = dólares que recibes por cada 1.000 visitas. CPM = dólares que paga el anunciante a YouTube por cada 1.000 impresiones.",
        "Ejemplo: CPM $10 → RPM aprox. $5.",
        "Sube el RPM con: buena retención (ver 5 de 10 min = 50 %), videos de más de 8 minutos (más anuncios en medio), audiencia de EE. UU., Canadá y Europa, temas relevantes para la audiencia y audiencias mayores (más poder adquisitivo).",
        "Diversificación: entre más canales, más ganancias. Escalar = tener varios canales.",
        "Requisitos para monetizar: cumplir las normas, 1.000 suscriptores y 4.000 horas de visualización. Luego se crea y vincula Google AdSense.",
        "Meta mensual de la academia: $10K USD.",
    ]},
    {"id": "fases", "icono": "🪜", "titulo": "Las 4 fases de la automatización ninja", "puntos": [
        "Fase 1 · Sin dinero: guiones con IA, tú haces miniaturas, tú narras y aprendes edición básica.",
        "Fase 2 · Primeros ingresos: guiones con IA, tú haces miniaturas, voz con IA y sigues editando.",
        "Fase 3 · Canal rentable: guiones con IA, sigues con miniaturas y delegas la edición.",
        "Fase 4 · Automatización total: contratas escritor, diseñador de miniaturas y editor profesional.",
        "Mayor capital = mayor escalabilidad.",
    ]},
    {"id": "audiencias", "icono": "👥", "titulo": "Audiencias", "puntos": [
        "A mayor edad, menos edición; a menor edad, más edición.",
        "Adultos mayores (40-45+): edición sencilla y barata, miniaturas directas con texto grande, alta retención, títulos llamativos funcionan muy bien, RPM alto. Packing con títulos largos o semi largos y miniaturas sencillas con mucho texto; comentarios de personas mayores.",
        "Riesgo con mayores: nichos que se saturan rápido; hay que buscar ángulos originales y la investigación toma más tiempo.",
        "Jóvenes (12-30): barreras de entrada altas, fidelidad al creador, pero costos de edición altos (cortes cada 5-7 s), detectan contenido forzado, menor poder adquisitivo y RPM bajo. Títulos y miniaturas minimalistas, ediciones dopamínicas.",
    ]},
    {"id": "evitar", "icono": "⛔", "titulo": "Nichos a evitar y políticas", "puntos": [
        "No monetizables al iniciar: música, recopilaciones, películas o series, alta violencia, temas de adultos y contenido sin valor.",
        "Cuidado con: lenguaje vulgar, drogas o alcohol, violencia gráfica, política partidista o extremista, desinformación médica, guerras o problemas actuales.",
        "Regla 1: contenido apto para anunciantes. Regla 2: requisitos de elegibilidad. Regla 3: ley COPPA (contenido para niños = anuncios limitados).",
        "Derechos de autor: las infracciones traen sanciones; nunca subas contenido ajeno sin transformarlo.",
    ]},
    {"id": "estrategia", "icono": "🥷", "titulo": "Estrategia ninja de búsqueda de nicho", "puntos": [
        "Crea un perfil (cuenta) de nichos para inglés y otro para español.",
        "Entrena el algoritmo para que te muestre canales automatizados: abre los links de nichos, abre al menos 3 videos populares o recientes y mira mínimo 10 segundos de cada uno. Hazlo a diario.",
        "Los mejores canales están en inglés: busca nichos en inglés.",
        "Haz un embudo de nichos (Notion o Excel) y fíltralos hasta quedarte con los más potentes.",
        "vidIQ sirve para palabras clave y temas generales; para nichos, haz análisis manual.",
        "Las etiquetas del canal y de los videos deben estar relacionadas con tu nicho y tener relevancia según canales que ya funcionaron.",
    ]},
    {"id": "pasos", "icono": "🔟", "titulo": "La metodología ninja en 10 pasos", "puntos": [
        "1. Encuentra 5 a 10 canales ganadores: máximo 1 año, más de 1M de visitas al mes, de preferencia en inglés.",
        "2. Filtra sus videos más virales (pestaña Populares).",
        "3. Extrae los guiones de los videos (ej. AssemblyAI) con su título original: saca 15.",
        "4. Modifica los guiones: con IA (ideal), con un profesional que parafrasee o con un guionista que parta de la referencia.",
        "5. Repite x15: siempre ten 15 videos adelantados.",
        "6. Graba el audio: tu celular/micrófono, voz con IA o un locutor profesional.",
        "7. Edita el video: al inicio la simplicidad siempre gana.",
        "8. Termina un banco de 15 videos (escritos, grabados y editados).",
        "9. Abre el canal de YouTube (un Gmail por canal; nombre, logo, banner y descripción relacionados al nicho).",
        "10. Publica y edita tu primer video viral.",
    ]},
    {"id": "titulos", "icono": "✍️", "titulo": "Títulos", "puntos": [
        "Prueba la connotación negativa.",
        "Método 1 · Pregunta: YouTube es un buscador, titula como lo que la gente busca.",
        "Método 2 · Piezas de Lego (usa 2 o más): listas, audiencia específica, deseo, periodo de tiempo, curiosidad, autoridad, negatividad; extras: meter presión y comparar.",
        "Método 3 · Roba como un artista: copia el título en inglés, tradúcelo y mejóralo. Recomendado los primeros 3-6 meses.",
        "SEO: investiga lo que la gente busca y haz videos que resuelvan un problema; las palabras clave en descripción y etiquetas funcionan como segundos títulos.",
        "Viralidad: títulos de alto impacto con palabras de curiosidad (truco, fórmula, la receta, el secreto).",
    ]},
    {"id": "miniaturas", "icono": "🖼️", "titulo": "Miniaturas", "puntos": [
        "Todas con el mismo estilo. Eficaz, sencilla y que comunique bien el mensaje.",
        "13 tipos: números grandes, shock/temor, expresión facial, frases, preguntas, respuestas, autoridad, contraste extremo, frase + foto, tiempo, comparación, transformación y curiosidad/censura.",
        "Elementos: imagen principal en 1/3 de la miniatura, imagen secundaria para llamar la atención, elementos fosforescentes y gráficos que causen intriga, curiosidad o morbo.",
    ]},
    {"id": "metricas", "icono": "📈", "titulo": "Métricas y retención", "puntos": [
        "CTR ideal 7-10 %; mejor si supera el 10 %.",
        "Retención (AVD) ideal: al menos 40-50 %.",
        "Solo cambia la miniatura cuando la retención ya está en al menos 40 %.",
        "A menor edad de la audiencia, más estimulación visual; con audiencias mayores, cambios cada 10-12 segundos bastan.",
        "Edición muy buena en los primeros 30 segundos.",
        "Guion viral de storytelling y guion de resolución de problema: 8 pasos cada uno; usa conectores de causalidad.",
    ]},
    {"id": "publicar", "icono": "🚀", "titulo": "Crear y publicar", "puntos": [
        "Publicación: título, miniatura, descripción (primeros 3 párrafos del guion, con SEO) y «inspirado por» los títulos de referencia.",
        "Programa la hora para que todas las audiencias del mundo estén despiertas.",
        "Herramientas: AssemblyAI (transcribir), texto a voz, Bing/Copilot o PicLumen (imágenes), CapCut (edición), Canva (banner).",
    ]},
]


def conocimiento_texto() -> str:
    """Todo el conocimiento en texto plano, para el contexto de la IA."""
    partes = []
    for s in SECCIONES:
        partes.append(f"## {s['titulo']}\n" + "\n".join(f"- {p}" for p in s["puntos"]))
    return "\n\n".join(partes)


# ---------- preguntas sugeridas para Nichi (rotan) ----------
PREGUNTAS = [
    "¿Qué es un canal automatizado?", "¿Cómo sé si un canal es sin rostro?", "¿Qué es un referente?",
    "¿Cuántos referentes necesito para validar un nicho?", "¿Qué diferencia hay entre nicho, subnicho y micronicho?",
    "¿Qué es el techo y el piso de un canal?", "¿Qué es el RPM?", "¿Cómo subo mi RPM?", "¿Por qué los videos de 8 minutos pagan más?",
    "¿Qué nichos debo evitar al iniciar?", "¿Qué son las 5 capas del sistema modular?", "¿Cuál es la capa más importante?",
    "¿Qué es evergreen y trendy?", "¿Conviene una audiencia mayor o joven?", "¿Cómo identifico la audiencia de un canal?",
    "¿Cuáles son las 4 fases de la automatización?", "¿Qué hago si no tengo dinero para invertir?", "Explícame los 10 pasos de la metodología",
    "¿Cómo entreno mi cuenta de nichos?", "¿Por qué buscar referentes en inglés?", "¿Qué es el método Piezas de Lego para títulos?",
    "¿Cómo hago títulos virales?", "¿Qué tipos de miniaturas funcionan?", "¿Cuál es un buen CTR?", "¿Qué retención debo buscar?",
    "¿Cuándo cambio una miniatura?", "¿Cuántos videos debo tener adelantados?", "¿Cada cuánto debo publicar?",
    "¿Qué requisitos pide YouTube para monetizar?", "¿Qué es la ley COPPA?", "¿Cómo funciona el algoritmo de YouTube?",
    "¿De dónde vienen la mayoría de las visitas?", "¿Qué es el análisis de mercado?", "¿Qué es oferta y demanda en YouTube?",
    "¿Cómo copio lo que funciona sin copiar?", "¿Qué herramientas uso para los guiones?", "¿Qué es un outlier?",
    "¿Cómo uso el buscador aleatorio?", "¿Qué significa el color de Nichi?", "¿Qué nicho me recomiendas con mis datos?",
    "¿Cuál canal replicar primero?", "¿Cómo escalo a varios canales?", "¿Cuál es la meta mensual de la academia?",
]

# ---------- consejos que Nichi suelta solo ----------
TIPS = [
    "Secreto #1: más videos = más tickets de lotería. La meta es 1 video diario.",
    "Un nicho de alto impacto perdona errores en todo lo demás: dedícale más tiempo al núcleo.",
    "Referente válido: máximo 1 año, ~1M de visitas al mes y en inglés. Necesitas 5.",
    "Entre más específico el nicho, mayor posibilidad de éxito (Fútbol → Errores del fútbol → Errores de Messi).",
    "Videos de más de 8 minutos permiten más anuncios en medio: más RPM.",
    "Audiencias mayores = edición sencilla, alta retención y RPM alto.",
    "A menor edad de la audiencia, más edición; a mayor edad, menos.",
    "Siempre ten 15 videos adelantados.",
    "Roba como un artista: copia el título en inglés, tradúcelo y mejóralo los primeros 3-6 meses.",
    "CTR ideal: 7-10 %. Retención ideal: 40-50 % o más.",
    "Solo cambia una miniatura cuando la retención ya pasa del 40 %.",
    "Los primeros 30 segundos del video necesitan la mejor edición.",
    "Más del 70 % de las visitas viene de la página de Inicio: ahí gana la miniatura + título.",
    "Evita al iniciar: música, recopilaciones, películas, violencia, temas de adultos y contenido sin valor.",
    "Entrena tu cuenta de nichos a diario: abre 3 videos por canal y mira al menos 10 segundos de cada uno.",
    "Diversifica: entre más canales, más ganancias.",
    "Los canales automatizados no muestran a nadie a cámara y suben mucho volumen.",
]

# ---------- semillas del buscador aleatorio (nichos típicos de canales automatizados) ----------
SEMILLAS = {
    "Historias narradas": ["elderly revenge stories", "grandma stories narrated", "family drama stories", "inheritance betrayal story",
                           "karma stories narrated", "true life stories narrated", "nursing home stories", "retirement stories"],
    "Misterio y terror": ["scary stories narrated", "true horror stories", "unsolved mysteries documentary", "creepy encounters stories",
                          "paranormal stories", "lost civilizations mysteries", "abandoned places history"],
    "Historia y documentales": ["history documentary", "ancient civilizations documentary", "medieval history explained",
                                "world war 2 stories", "forgotten history", "roman empire explained", "history of everyday things"],
    "Dinero y lujo": ["old money documentary", "billionaire lifestyle documentary", "richest families history", "luxury brands history",
                      "how rich people spend money", "royal family secrets"],
    "Curiosidades y ciencia": ["space facts documentary", "deep ocean mysteries", "science explained simply", "engineering marvels",
                               "how things are made documentary", "strange facts explained"],
    "Animales y naturaleza": ["extinct animals documentary", "dangerous animals facts", "prehistoric creatures documentary",
                              "animal survival stories", "nature mysteries"],
    "Fe y mitología": ["bible stories explained", "mythology explained", "greek mythology stories", "biblical mysteries", "norse mythology stories"],
    "Autos y máquinas": ["truck culture", "car history documentary", "military aircraft explained", "trains history documentary",
                         "heavy machinery explained"],
    "Crimen y casos": ["true crime documentary", "heist stories explained", "cold cases solved", "scammers exposed story"],
    "Deportes": ["football stories documentary", "athletes who lost everything", "sports history moments", "boxing legends stories"],
    "Celebridades": ["celebrity downfall documentary", "old hollywood stories", "child stars then and now", "famous families history"],
}


def semillas_aleatorias(n: int = 3, categoria: str = "", evitar: set | None = None) -> list:
    evitar = evitar or set()
    if categoria and categoria in SEMILLAS:
        pool = SEMILLAS[categoria]
    else:
        cats = list(SEMILLAS)
        random.shuffle(cats)
        pool = [random.choice(SEMILLAS[c]) for c in cats]  # una por categoría para variar
    candidatas = [s for s in pool if s not in evitar] or pool
    random.shuffle(candidatas)
    return candidatas[:n]


# ---------- respuestas sin IA (modo guía) ----------
REGLAS = [
    (("automatizado", "sin rostro", "faceless"), "tipos"),
    (("rostro",), "tipos"),
    (("referente", "inglés", "ingles"), "mercado"),
    (("oferta", "demanda", "mercado", "competencia", "competidor"), "mercado"),
    (("subnicho", "micronicho", "nicho"), "nicho"),
    (("techo", "piso"), "techos"),
    (("evergreen", "trendy", "mixto"), "contenido"),
    (("rpm", "cpm", "dinero", "ganar", "monetiz", "adsense", "requisit", "meta", "escalar", "varios canales"), "dinero"),
    (("fase", "sin dinero", "invertir", "contratar", "delegar"), "fases"),
    (("audiencia", "mayores", "jóvenes", "jovenes", "edad"), "audiencias"),
    (("evitar", "prohib", "política", "politica", "coppa", "derechos", "copyright", "norma"), "evitar"),
    (("entrenar", "cuenta de nichos", "notion", "embudo", "vidiq", "etiqueta"), "estrategia"),
    (("paso", "metodolog", "guion", "guiones", "adelantad", "banco"), "pasos"),
    (("título", "titulo", "lego", "clickbait", "seo"), "titulos"),
    (("miniatura", "thumbnail"), "miniaturas"),
    (("ctr", "retención", "retencion", "avd", "métrica", "metrica"), "metricas"),
    (("algoritmo", "inicio", "home", "recomienda", "sugeridos"), "algoritmo"),
    (("capa", "núcleo", "nucleo", "radar", "big bang", "packing", "arquitectura"), "capas"),
    (("publicar", "crear canal", "gmail", "logo", "banner", "herramienta"), "publicar"),
    (("lotería", "loteria", "volumen", "diario", "cada cuánto", "frecuencia"), "base"),
]


def responder_guia(q: str) -> str | None:
    ql = q.lower()
    for claves, sid in REGLAS:
        if any(c in ql for c in claves):
            s = next(x for x in SECCIONES if x["id"] == sid)
            puntos = s["puntos"][:10]
            return f"{s['icono']} {s['titulo']}:\n" + "\n".join(f"• {p}" for p in puntos)
    return None
