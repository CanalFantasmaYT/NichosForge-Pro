"""Asigna un nicho a cada video o canal.

1. Reglas: palabras clave de nichos típicos de canales automatizados (en inglés y español).
2. Lo aprendido: nichos que creó la IA o que tú asignaste a mano (datos/nichos_aprendidos.json).
3. IA (opcional): clasifica lo que quedó "Sin clasificar", inventa nombres de nichos nuevos y guarda sus
   palabras clave para que la próxima vez las reglas los reconozcan solas.
"""
import re
from collections import Counter

from . import llm
from .config import DATOS
from .utils import log, read_json, write_json

APRENDIDOS = DATOS / "nichos_aprendidos.json"
SIN = "Sin clasificar"

# Cada nicho: términos FUERTES (específicos, peso 3) y DÉBILES (genéricos, peso 1), en inglés y español.
# Se buscan como palabras completas (con plural), sin importar tildes ni mayúsculas.
TAX = {
    "Old money y lujo": {"f": ["principe", "principes", "princesa", "monaco", "windsor", "habsburg", "bourbon", "borbon", "duke", "duque", "duchess", "duquesa", "private jet", "jet privado", "private island", "isla privada", "butler", "mayordomo", "caviar", "royalty", "royal*", "monarch*", "monarqu*", "reina", "aristocra*", "millonari*", "billonari*", "magnate*", "tycoon*", "old money", "billionaire", "millionaire", "richest", "wealthiest", "dynasty", "heir", "heiress", "heirs", "aristocrat",
                               "aristocracy", "royal family", "royals", "the queen", "the king", "prince", "princess", "tsar", "rockefeller", "rothschild",
                               "vanderbilt", "rich people", "fortune", "fortunes", "luxury", "superyacht", "yacht", "mansion", "mansiones", "realeza",
                               "millonario", "multimillonario", "mas rica", "mas rico", "mas ricos", "herederos", "heredero", "fortuna", "lujo", "dinastia", "nobleza"],
                         "d": ["rich", "wealth", "elite", "expensive", "rico", "ricos", "riqueza", "palace", "palacio"]},
    "Historias de venganza y drama familiar": {"f": ["cunada", "cunado", "sister in law", "brother in law", "ex husband", "ex wife", "exmarido", "exesposa", "boyfriend", "girlfriend", "novio", "novia", "arruinar", "ruined my", "sabotage", "sabotaje", "gold digger", "interesada", "venga*", "traicion*", "humill*", "engan* a su", "cheat*", "betray*", "entitled*", "mother in law", "mother-in-law", "suegra", "suegro", "entitled", "karma", "revenge", "venganza", "cheated",
                               "cheating", "infiel", "affair", "divorce", "divorcio", "stepmom", "stepmother", "madrastra", "inheritance", "herencia",
                               "betrayed", "traicion", "humiliated", "humillo", "humillada", "humillado"],
                         "d": ["husband", "wife", "esposo", "esposa", "sister", "brother", "hermana", "hermano", "wedding", "boda", "family", "familia", "fiance"]},
    "Historias para adultos mayores": {"f": ["abuel*", "ancian*", "jubilad*", "grandparent*", "veteran*", "old couple", "pareja de ancianos", "grandma", "grandpa", "grandmother", "grandfather", "elderly", "old man", "old woman", "old lady", "senior citizen",
                               "retired", "retiree", "nursing home", "abuela", "abuelo", "abuelita", "abuelito", "anciano", "anciana", "jubilado", "jubilada", "asilo",
                               "grandson", "granddaughter", "nieto", "nieta"],
                         "d": ["years later", "anos despues", "pension"]},
    "Historias de Reddit narradas": {"f": ["r/", "maliciouscompliance", "entitledparents", "subreddit", "redditor*", "reddit", "aita", "am i the", "tifu", "prorevenge", "pro revenge", "malicious compliance", "nuclear revenge",
                               "petty revenge", "entitled parents", "r/"], "d": ["storytime"]},
    "Terror y paranormal": {"f": ["leyendas urbanas", "urban legend", "urban legends", "haunted hotel", "hotel embrujado", "terror*", "horrif*", "paranormal*", "embruj*", "espeluznant*", "escalofriant*", "relatos de terror", "horror", "scary", "creepy", "haunted", "haunting", "paranormal", "ghost", "ghosts", "demon", "demonic", "possessed", "skinwalker",
                               "cryptid", "terror", "miedo", "fantasma", "fantasmas", "embrujada", "embrujado", "aterrador", "aterradora", "disturbing", "nightmare",
                               "pesadilla", "encounter", "encounters", "deep woods", "campers"], "d": ["dark", "strange", "oscuro"]},
    "Misterios sin resolver": {"f": ["casos sin resolver", "cold case", "caso sin resolver", "nunca resuelto", "never solved", "lighthouse keepers", "misterio*", "mysterious*", "desapareci*", "enigm*", "unexplain*", "unsolved", "mystery", "mysteries", "vanished", "disappeared", "disappearance", "missing", "unexplained", "without a trace",
                               "misterio", "misterios", "desaparicion", "desaparecio", "desaparecidos", "sin resolver", "inexplicable", "enigma", "dyatlov", "bermuda"],
                         "d": ["what really happened", "strange", "secret"]},
    "Crimen real": {"f": ["asesin*", "secuestr*", "criminal*", "homicid*", "detective*", "investigad*", "murder*", "killer", "serial killer", "murder", "murderer", "homicide", "detective", "detectives", "fbi", "prison", "prisoner", "inmate", "inmates",
                               "cartel", "mafia", "gangster", "heist", "robbery", "kidnapping", "true crime", "asesino", "asesinato", "crimen", "carcel", "preso",
                               "secuestro", "narco", "atraco", "caso", "convicted"], "d": ["police", "policia", "caught", "case"]},
    "Estafas y fraudes": {"f": ["conned", "con man", "conman", "swindle", "swindler", "embezzle*", "desfalco", "lavado de dinero", "money laundering", "forgery", "falsific*", "counterfeit", "impostor", "impostora", "fake doctor", "identidad falsa", "catfish*", "out of millions", "estaf*", "fraud*", "scam*", "enga*o masivo", "swindl*", "scam", "scams", "scammer", "scammed", "fraud", "fraudster", "ponzi", "con artist", "conman", "fake heiress", "pyramid scheme",
                               "estafa", "estafador", "fraude", "piramidal", "insurance money", "faked his own death", "faked her own death"], "d": ["fake", "falso"]},
    "Historia antigua y medieval": {"f": ["bizantin*", "byzantin*", "mesopotami*", "babilon*", "persian*", "griego*", "greek empire", "samurai*", "ottoman*", "otoman*", "faraon*", "ancient", "medieval", "middle ages", "roman", "romans", "rome", "egypt", "egyptian", "pharaoh", "pyramid", "pyramids",
                               "viking", "vikings", "empire", "knight", "knights", "castle life", "sparta", "spartan", "aztec", "maya", "mayan", "inca", "civilization",
                               "antigua", "antiguo", "romano", "romanos", "imperio", "egipto", "faraon", "piramides", "vikingo", "vikingos", "caballeros", "civilizacion",
                               "edad media", "medievales"], "d": ["history", "historia", "historical", "life was like"]},
    "Guerras e historia moderna": {"f": ["guerra*", "batalla*", "bunker*", "nazi*", "sovietic*", "invasion*", "civil war", "guerra civil", "ww1", "ww2", "wwii", "world war", "hitler", "nazi", "nazis", "stalingrad", "normandy", "d-day", "cold war", "soviet",
                               "soldier", "soldiers", "battle", "battles", "war", "warfare", "trench", "spy", "guerra", "segunda guerra", "primera guerra", "batalla",
                               "soldados", "soldado", "normandia", "desembarco", "tsar", "zar", "revolution", "revolucion"], "d": ["army", "ejercito", "general"]},
    "Militar y aviación": {"f": ["portaaviones", "destructor", "fragata", "acorazado", "battleship", "cruiser", "helicopter", "helicoptero", "apache", "black hawk", "abrams", "sniper", "francotirador", "special forces", "fuerzas especiales", "navy seals", "marines", "pentagon", "pentagono", "nuclear weapon", "arma nuclear", "armas nucleares", "icbm", "warhead", "ojiva", "militar*", "air force", "fuerza aerea", "fighter*", "warship*", "destroyer*", "bomber*", "armament*", "armamento*", "military", "fighter jet", "fighter jets", "f-22", "f-35", "f-16", "raptor", "aircraft carrier", "aircraft carriers", "submarine",
                               "submarino", "warship", "navy", "missile", "missiles", "misil", "hipersonico", "hypersonic", "tank", "tanks", "tanque", "stealth",
                               "bomber", "drone", "drones", "armada", "militar", "avion de combate"], "d": ["army", "aircraft", "jet", "jets"]},
    "Negocios y marcas": {"f": ["historia de ferrari", "history of ferrari", "brand", "brands", "company", "companies", "bankrupt", "bankruptcy", "went broke", "ceo", "startup", "business", "billion dollar",
                               "rise and fall", "marca", "marcas", "empresa", "empresas", "quiebra", "negocio", "kodak", "blockbuster", "nike", "wework", "mcdonald",
                               "walmart", "amazon", "apple", "tesla", "industry", "industria", "coca-cola", "coca cola", "pepsi", "disney", "netflix", "google", "microsoft", "samsung", "sony", "nintendo", "toyota", "ford", "ferrari", "lamborghini",
 "rolex", "gucci", "louis vuitton", "starbucks", "ikea", "lego", "toys r us", "sears", "nokia", "blackberry", "uber", "airbnb", "facebook", "meta", "twitter",
 "brand*", "compan*", "empresa*", "negocio*", "corporation", "corporacion", "monopoly", "monopolio", "took over the world", "conquisto el mundo", "garaje", "garage"], "d": ["became", "built", "market", "dollar", "billion", "empire", "imperio"]},
    "Celebridades y Hollywood": {"f": ["the cast", "el reparto", "movie", "movies", "pelicula", "peliculas", "sitcom", "tv show", "serie de tv", "director de cine", "rapper", "rapero", "pop star", "popstar", "musician", "musico", "influencer", "youtuber", "paparazzi", "escandalo", "scandal", "the simpsons", "breaking bad", "harry potter", "marvel", "friends cast", "cast of", "hollywood", "celebrity", "celebrities", "actor", "actors", "actress", "actresses", "child star", "child stars", "famous",
                               "famosos", "famosas", "famoso", "celebridad", "celebridades", "elvis", "michael jackson", "marilyn", "singer", "singers", "cantante",
                               "red carpet", "oscar"], "d": ["star", "stars", "estrella"]},
    "Deportes y leyendas": {"f": ["goalkeeper", "portero", "arquero", "striker", "delantero", "midfielder", "goals", "goles", "penalty", "penalti", "fichaje", "transfer window", "partido de futbol", "league", "liga", "coach", "entrenador", "stadium", "estadio", "aficionados", "hinchas", "referee", "arbitro", "quarterback", "touchdown", "slam dunk", "knockout", "nocaut", "champion", "campeon", "medal", "medalla", "marathon", "maraton", "cyclist", "ciclista", "tour de france", "cristiano", "neymar", "mbappe", "pele", "maradona", "kobe", "lebron", "tyson", "muhammad ali", "federer", "nadal", "scored", "anoto", "boxeo", "boxing*", "futbol*", "basketball", "baloncesto", "baseball", "beisbol", "hockey", "wrestl*", "lucha libre", "tenis", "atleta*", "olimpi*", "football", "footballer", "footballers", "soccer", "nba", "nfl", "mlb", "boxing", "boxer", "boxers", "boxeador", "boxeadores",
                               "ufc", "athlete", "athletes", "olympic", "olympics", "messi", "ronaldo", "jordan", "futbol", "futbolista", "futbolistas", "deporte",
                               "deportes", "mundial", "world cup", "champions", "tennis", "golf", "f1", "formula 1"], "d": ["legend", "legends", "leyenda", "leyendas", "team", "equipo"]},
    "Autos, camiones y máquinas": {"f": ["semi truck", "semi trucks", "hoods", "coche*", "camion*", "automovil*", "vehicul*", "maquinaria*", "clasic* cars", "classic cars", "coches clasicos", "autos clasicos", "truck", "trucks", "trucker", "tractor", "tractors", "car", "cars", "engine", "engines", "motor", "motores", "vehicle",
                               "vehicles", "supercar", "motorcycle", "camion", "camiones", "auto", "autos", "coche", "coches", "carro", "carros", "excavator", "bulldozer",
                               "locomotive", "train", "trains", "tren", "trenes", "maquinaria", "machine", "machines"], "d": ["horsepower", "powerful", "potente"]},
    "Ciencia y espacio": {"f": ["moon", "luna", "comet", "cometa", "meteor", "meteorito", "supernova", "nebula", "nebulosa", "eclipse", "telescope", "telescopio", "jupiter", "saturn", "saturno", "pluto", "pluton", "neptune", "neptuno", "orbit", "orbita", "gravity", "gravedad", "light year", "ano luz", "big bang", "dark matter", "materia oscura", "alien", "aliens", "extraterrestre", "ufo", "ovni", "wormhole", "agujero de gusano", "time travel", "viaje en el tiempo", "observable universe", "universo observable", "astronom*", "cosmo*", "astronaut*", "planeta*", "galax*", "cientific*", "experiment*", "diamonds planet", "space", "universe", "planet", "planets", "galaxy", "black hole", "agujero negro", "nasa", "james webb", "solar system", "sistema solar",
                               "asteroid", "asteroide", "astronaut", "astronauta", "mars", "marte", "moon", "luna", "universo", "planeta", "planetas", "galaxia",
                               "quantum", "cuantica", "physics", "fisica", "science", "ciencia", "scientists", "cientificos"], "d": ["star", "stars", "estrellas"]},
    "Animales y naturaleza": {"f": ["spider", "arana", "octopus", "pulpo", "squid", "calamar", "jellyfish", "medusa", "crocodile", "cocodrilo", "alligator", "caiman", "tiger", "tigre", "elephant", "elefante", "gorilla", "gorila", "monkey", "chimpanzee", "bear", "oso", "wolf", "wolves", "lobo", "eagle", "aguila", "owl", "buho", "parrot", "loro", "penguin", "pinguino", "dolphin", "delfin", "orca", "walrus", "morsa", "hippo", "hipopotamo", "rhino", "rinoceronte", "giraffe", "jirafa", "zebra", "cebra", "scorpion", "escorpion", "alacran", "frog", "rana", "lizard", "lagarto", "turtle", "tortuga", "python", "piton", "anaconda", "cobra", "viper", "vibora", "venomous", "venenoso", "venenosa", "t-rex", "mammoth", "mamut", "fish", "peces", "pajaro", "predator", "puppy", "cachorro", "kitten", "gatito", "wild animals", "animales salvajes", "zoo", "safari", "coral reef", "arrecife", "animal*", "criatura*", "depredador*", "mamifer*", "reptil*", "aves", "birds", "oceano*", "deep sea", "mar profundo", "animal", "animals", "animales", "shark", "sharks", "tiburon", "tiburones", "snake", "snakes", "serpiente", "predator", "predators",
                               "wildlife", "species", "especie", "especies", "creature", "creatures", "criaturas", "dinosaur", "dinosaurs", "dinosaurio", "extinct",
                               "extinto", "extintos", "prehistoric", "prehistorico", "amazon rainforest", "ocean", "oceano", "mariana trench", "fosa de las marianas",
                               "gatos", "perros", "cats", "dogs", "lion", "lions", "leon", "whale", "ballena", "insect", "insects", "jungle", "selva", "nature", "naturaleza"],
                         "d": ["wild", "salvaje", "amazon"]},
    "Supervivencia y aventura": {"f": ["sobreviv*", "surviv*", "perdido en", "perdida en", "lost in the", "atrapado*", "trapped", "naufrag*", "rescat*", "survived", "survival", "survive", "survivor", "sobrevivio", "supervivencia", "sobrevivir", "stranded", "lost at sea",
                               "castaway", "naufrago", "wilderness", "expedition", "expedicion", "rescue", "rescate", "andes", "arctic", "artico", "everest"],
                         "d": ["lost", "perdido", "days", "dias"]},
    "Mitología y religión": {"f": ["mitolog*", "biblic*", "angel*", "dios*", "religio*", "greek gods", "dioses griegos", "egyptian gods", "dioses egipcios", "profet*", "mythology", "myth", "myths", "mitologia", "mito", "mitos", "zeus", "odin", "thor", "loki", "hades", "olympus", "norse", "nordicos",
                               "gods", "dioses", "god", "dios", "bible", "biblical", "biblia", "biblico", "jesus", "angel", "angels", "angeles", "prophecy", "profecia",
                               "end times", "apocalypse", "apocalipsis", "religion", "church", "iglesia", "demons"], "d": ["legend", "leyenda", "heaven", "cielo"]},
    "Ingeniería y megaproyectos": {"f": ["ingenier*", "megaproy*", "megaproject*", "tunel*", "construy*", "construcci*", "insane new", "skyscraper*", "engineering", "ingenieria", "megaproject", "megaproyecto", "bridge", "bridges", "puente", "skyscraper", "rascacielos",
                               "tunnel", "tunel", "dam", "presa", "canal de panama", "panama canal", "construction", "construccion", "built", "construyo", "construido",
                               "largest", "tallest"], "d": ["build", "project", "proyecto", "billion"]},
    "Geografía y países": {"f": ["nobody lives", "nadie vive", "no longer exist", "ya no existen", "middle of australia", "country", "countries", "pais", "paises", "border", "borders", "frontera", "fronteras", "geography", "geografia", "map", "maps", "mapa",
                               "island", "islands", "isla", "islas", "russia", "rusia", "japan", "japon", "china", "india", "africa", "forbidden to visit", "city", "cities",
                               "ciudad", "ciudades", "immigrants", "inmigrantes", "population", "poblacion", "usa", "america", "canada", "mexico", "brazil", "brasil", "argentina", "colombia", "peru", "chile", "venezuela", "cuba", "spain", "espana", "france", "francia",
 "germany", "alemania", "italy", "italia", "england", "inglaterra", "uk", "ireland", "scotland", "norway", "noruega", "sweden", "suecia", "switzerland", "suiza",
 "north korea", "corea del norte", "south korea", "korea", "corea", "vietnam", "thailand", "indonesia", "philippines", "australia", "new zealand", "egypt today",
 "saudi arabia", "arabia saudita", "dubai", "qatar", "iran", "israel", "turkey", "turquia", "greenland", "groenlandia", "antarctica", "antartida", "siberia",
 "alaska", "texas", "california", "empty", "vacio", "smallest country", "pais mas pequeno", "capital", "capitals", "state", "states", "estados"], "d": ["world", "mundo", "so big", "tan grande"]},
    "Psicología y estoicismo": {"f": ["never get angry", "nunca se enojan", "people who", "personas que", "manipul*", "psicolog*", "psycholog*", "estoic*", "stoic*", "overthinking", "pensar demasiado", "narcis*", "ansiedad", "anxiety", "senales de que", "signs someone", "stoic", "stoicism", "estoico", "estoicismo", "marcus aurelius", "marco aurelio", "seneca", "psychology", "psicologia",
                               "manipulative", "manipuladoras", "manipulacion", "dark psychology", "psicologia oscura", "mindset", "habits", "habitos", "discipline",
                               "disciplina", "motivation", "motivacion", "mind", "mente", "narcissist", "narcisista"], "d": ["life", "vida", "control"]},
    "Desastres y accidentes": {"f": ["dam broke", "rompio la presa", "flood", "inundacion", "wildfire", "incendio", "blackout", "apagon", "shipwreck", "derailment", "descarrilamiento", "stampede", "estampida", "desastr*", "tragedi*", "huracan*", "terremot*", "accident*", "catastro*", "derrumb*", "chernobyl*", "disaster", "disasters", "desastre", "crash", "crashes", "plane crash", "accident", "accidente", "titanic", "sinking", "naufragio",
                               "earthquake", "terremoto", "tsunami", "explosion", "eruption", "volcano", "volcan", "hurricane", "huracan", "chernobyl", "tragedy",
                               "tragedia", "collapse", "derrumbe", "minute by minute"], "d": ["worst", "peor", "deadliest"]},
    "Lugares abandonados y arquitectura": {"f": ["abandon*", "theme park", "parque de diversiones", "ruina*", "explore*", "explor*", "abandoned", "abandonado", "abandonada", "abandonados", "ruins", "ruinas", "castle", "castles", "castillo",
                               "castillos", "architecture", "arquitectura", "tiny house", "house tour", "exploring", "explorando", "ghost town", "pueblo fantasma"],
                         "d": ["inside", "dentro", "beautiful", "hermoso"]},
    "Tecnología e IA": {"f": ["tecnolog*", "technolog*", "inteligencia artificial", "algoritm*", "algorithm*", "hack*", "ciberat*", "cyber*", "learned to lie", "artificial intelligence", "inteligencia artificial", "ai", "ia", "robot", "robots", "chatgpt", "openai", "technology", "tecnologia",
                               "tech", "gadget", "gadgets", "iphone", "smartphone", "computer", "computadora", "software", "hackers", "hacker", "chip", "chips"],
                         "d": ["future", "futuro", "jobs", "empleos"]},
    "Comida y cocina": {"f": ["cocin*", "receta*", "aliment*", "restaurant*", "most expensive pizza", "food", "foods", "recipe", "recipes", "receta", "recetas", "cooking", "cocina", "dish", "dishes", "platillo", "restaurant",
                               "restaurante", "chef", "fries", "papas fritas", "burger", "pizza", "eat", "eating", "comida", "comer", "taste", "sabor", "candy", "dulces"],
                         "d": ["delicious", "delicioso"]},
    "Salud y cuerpo humano": {"f": ["salud*", "enfermedad*", "cerebr*", "brain*", "insomni*", "sueno", "dont sleep", "don't sleep", "no duermes", "cancer*", "your body", "tu cuerpo", "human body", "cuerpo humano", "brain", "cerebro", "health", "salud", "sugar", "azucar", "sleep",
                               "dormir", "disease", "enfermedad", "doctor", "doctors", "medico", "longevity", "longevidad", "heart", "corazon", "vitamin", "vitamina"],
                         "d": ["stop eating", "deja de", "what happens"]},
    "Curiosidades y datos": {"f": ["curios*", "facts about", "datos sobre", "that will scare you", "que te asustaran", "facts", "fact", "datos curiosos", "curiosidades", "didn't know", "didnt know", "no sabias", "things you", "cosas que",
                               "strange things", "weird things", "cosas extranas", "everyday objects", "explained", "explicado"], "d": ["why", "por que", "how", "como"]},
}
# Reglas de desempate: si aparecen ambos, gana el segundo (más específico)
PREFERENCIAS = [("Old money y lujo", "Lugares abandonados y arquitectura", ["abandoned", "abandonado", "abandonada"]),
                ("Historias de venganza y drama familiar", "Historias de Reddit narradas", ["reddit", "aita", "r/", "prorevenge", "am i the", "tifu"]),
                ("Militar y aviación", "Desastres y accidentes", ["crash", "accident", "accidente", "disaster"]),
                ("Curiosidades y datos", "Animales y naturaleza", ["gatos", "perros", "cats", "dogs", "animal", "animales"]),
                ("Curiosidades y datos", "Geografía y países", ["border", "borders", "fronteras", "country", "countries", "paises", "island"]),
                ("Negocios y marcas", "Old money y lujo", ["family", "familia", "dynasty", "heir", "herederos", "rich people"]),
                ("Old money y lujo", "Guerras e historia moderna", ["tsar", "zar", "revolution"]),
                ("Old money y lujo", "Mitología y religión", ["god", "dios", "gods"]),
                ("Historias de venganza y drama familiar", "Historias para adultos mayores", ["abuelo", "abuela", "grandma", "grandpa", "elderly",
                 "anciano", "anciana", "old man", "old woman", "old lady", "grandmother", "grandfather", "jubilado"]),
                ("Lugares abandonados y arquitectura", "Historia antigua y medieval", ["medieval", "ancient", "life was like", "edad media"]),
                ("Ciencia y espacio", "Tecnología e IA", ["inteligencia artificial", "artificial intelligence", "ai", "ia", "robot", "robots"]),
                ("Geografía y países", "Curiosidades y datos", ["strange things", "weird things", "only exist", "cosas que", "cosas extranas"]),
                ("Terror y paranormal", "Misterios sin resolver", ["sin resolver", "unsolved", "cold case", "casos sin resolver"]),
                ("Misterios sin resolver", "Ciencia y espacio", ["luna", "moon", "sol", "sun", "planeta", "planet", "universo", "universe", "galaxia"]),
                ("Ingeniería y megaproyectos", "Desastres y accidentes", ["broke", "rompio", "tragedy", "tragedia", "collapse", "derrumbe", "disaster"]),
                ("Old money y lujo", "Historias para adultos mayores", ["abuela", "abuelo", "grandma", "grandpa", "anciana", "anciano"]),
                ("Ciencia y espacio", "Animales y naturaleza", ["animals", "animales", "animal", "creatures", "criaturas", "species", "especies"]),
                ("Animales y naturaleza", "Supervivencia y aventura", ["perdido", "perdida", "lost in", "survived", "sobrevivio", "atrapado", "trapped", "dias", "days"]),
                ("Historia antigua y medieval", "Negocios y marcas", ["empresa", "company", "garaje", "garage", "brand", "marca"]),
                ("Curiosidades y datos", "Salud y cuerpo humano", ["your body", "tu cuerpo", "human body", "cuerpo humano"])]
NICHOS = {k: v["f"] + v["d"] for k, v in TAX.items()}      # compatibilidad: lista plana de palabras


def aprendidos() -> dict:
    d = read_json(APRENDIDOS, {}) or {}
    d.setdefault("nichos", {})     # nombre -> {"palabras": [...], "fuente": "ia"|"usuario", "veces": n}
    d.setdefault("videos", {})     # video_id -> {"nicho": ..., "fuente": ...}
    d.setdefault("canales", {})    # canal_id -> {"nicho": ..., "fuente": ...}
    return d


def nombres() -> list:
    d = aprendidos()
    return sorted(set(NICHOS) | set(d["nichos"]))


def _norm(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " " + re.sub(r"[^a-z0-9/'\-]+", " ", t).replace("'", "") + " "


def _rx(term: str):
    """Palabra completa (con plural). 'raiz*' = cualquier palabra que empiece así. 'r/' = prefijo."""
    raiz = term.endswith("*")
    base = _norm(term.rstrip("*")).strip()
    t = re.escape(base).replace("\\ ", " ")
    if raiz:
        return re.compile(r"(?<![a-z0-9])" + t + r"[a-z]*")
    if base.endswith("/"):
        return re.compile(r"(?<![a-z0-9])" + t)
    return re.compile(r"(?<![a-z0-9])" + t + r"(?:s|es)?(?![a-z0-9])")


_CACHE = {"clave": None, "pats": None}


def _patrones() -> dict:
    """{nicho: [(regex, peso)]} con los nichos de fábrica y los aprendidos (de la IA o tuyos)."""
    ap = aprendidos()
    clave = str(sorted((k, tuple(v.get("palabras", []))) for k, v in ap["nichos"].items()))
    if _CACHE["clave"] == clave:
        return _CACHE["pats"]
    pats = {n: [(_rx(t), 3.0) for t in d["f"]] + [(_rx(t), 1.0) for t in d["d"]] for n, d in TAX.items()}
    for nombre, info in ap["nichos"].items():
        palabras = [p for p in info.get("palabras", []) if len(p) >= 4]
        if palabras and nombre not in TAX:
            pats[nombre] = [(_rx(p), 2.5) for p in palabras]
    _CACHE.update(clave=clave, pats=pats)
    return pats


def puntajes(titulo: str, tags: list | None = None, extra: str = "", pats: dict | None = None) -> Counter:
    pats = pats or _patrones()
    t, tg, ex = _norm(titulo), _norm(" , ".join(tags or [])), _norm(extra)
    pts = Counter()
    for nicho, lista in pats.items():
        usados = []                                   # cada palabra del título cuenta una sola vez por nicho
        for rx, peso in sorted(lista, key=lambda x: -x[1]):
            m = rx.search(t)
            if m and not any(m.start() < b and a_ < m.end() for a_, b in usados):
                usados.append((m.start(), m.end()))
                pts[nicho] += peso
            if tg.strip() and rx.search(tg):
                pts[nicho] += peso * 0.4
            if ex.strip() and rx.search(ex):
                pts[nicho] += peso * 0.25
    # desempates por contexto específico
    for general, especifico, claves in PREFERENCIAS:
        if pts.get(general) and pts.get(especifico) and any(_rx(c).search(t) for c in claves):
            pts[especifico] += 4
    return pts


def clasificar(titulo: str, tags: list | None = None, extra: str = "", pats: dict | None = None) -> tuple:
    """(nicho, confianza 0-1). 'Sin clasificar' si no hay señal clara."""
    pts = puntajes(titulo, tags, extra, pats)
    if not pts:
        return SIN, 0.0
    (n1, p1), *resto = pts.most_common(2)
    p2 = resto[0][1] if resto else 0
    if p1 < 2.5:
        return SIN, 0.0
    margen = (p1 - p2) / p1
    return n1, round(min(1.0, 0.35 + margen * 0.45 + min(p1, 9) / 30), 2)


def clasificar_canal(titulos: list, tags: list | None = None, descripcion: str = "", nombre: str = "") -> tuple:
    """Nicho del CANAL: votos de todos sus títulos + su nombre y descripción. (nicho, confianza, reparto)."""
    pats = _patrones()
    votos = Counter()
    for i, t in enumerate(titulos[:40]):
        n, conf = clasificar(t, (tags or [])[i] if tags and i < len(tags) else [], "", pats)
        if n != SIN:
            votos[n] += 0.5 + conf
    extra = puntajes(nombre + " " + nombre, None, descripcion[:400], pats)
    for n, p in extra.items():
        votos[n] += min(p, 6) * 0.35
    if not votos:                                     # sin reglas: lo que aprendió el modelo con tus datos
        for t in titulos[:40]:
            n, conf = predecir_nb(t)
            if n != SIN:
                votos[n] += conf
    if not votos:
        return SIN, 0.0, {}
    total = sum(votos.values())
    (n1, v1), *resto = votos.most_common(2)
    v2 = resto[0][1] if resto else 0
    conf = round(min(1.0, (v1 / total) * 0.7 + (1 - v2 / v1) * 0.3), 2) if v1 else 0
    return (n1 if v1 / total >= 0.3 else SIN), conf, {k: round(v / total, 2) for k, v in votos.most_common(4)}


def clasificar_video(v: dict, nicho_canal: str = "", conf_canal: float = 0.0, pats: dict | None = None) -> tuple:
    """(nicho, fuente). Prioridad: lo que corregiste tú > IA > tema claramente distinto al del canal > nicho del canal > reglas > modelo."""
    d = aprendidos()
    previo = d["videos"].get(v["id"])
    if previo:
        return previo["nicho"], previo.get("fuente", "ia")
    pats = pats or _patrones()
    pts = puntajes(v.get("titulo", ""), v.get("tags"), (v.get("desc") or "")[:300], pats)
    n, conf = clasificar(v.get("titulo", ""), v.get("tags"), (v.get("desc") or "")[:300], pats)
    if nicho_canal and nicho_canal != SIN:
        if n != SIN and n != nicho_canal and conf >= 0.75 and pts.get(n, 0) >= 6 and pts.get(nicho_canal, 0) < 2:
            return n, "reglas"                      # este video trata claramente de otra cosa
        return nicho_canal, "canal"
    if n != SIN:
        return n, "reglas"
    nb, cb = predecir_nb(v.get("titulo", ""))
    return (nb, "modelo") if nb != SIN else (SIN, "")


def nicho_video(v: dict, pats: dict | None = None) -> tuple:
    """Respeta lo que asignaste tú o la IA antes; si no, usa reglas. -> (nicho, fuente)"""
    d = aprendidos()
    previo = d["videos"].get(v["id"])
    if previo:
        return previo["nicho"], previo.get("fuente", "ia")
    n, conf = clasificar(v.get("titulo", ""), v.get("tags"), v.get("canal", ""), pats)
    return n, "reglas" if n != SIN else ""


def asignar(tipo: str, ident: str, nicho: str, fuente: str = "usuario", palabras: list | None = None, titulos: list | None = None):
    """Guarda un nicho asignado (por ti o por la IA). Las palabras clave solo se guardan si vienen de la IA o
    las escribes tú; los títulos entrenan el modelo (tus correcciones pesan el triple)."""
    nicho = (nicho or "").strip()
    if not nicho:
        return
    d = aprendidos()
    d["videos" if tipo == "video" else "canales"][ident] = {"nicho": nicho, "fuente": fuente}
    if nicho not in TAX:
        info = d["nichos"].setdefault(nicho, {"palabras": [], "fuente": fuente, "veces": 0})
        info["veces"] = int(info.get("veces", 0)) + 1
        info["palabras"] = list(dict.fromkeys(info["palabras"] + [p.lower().strip() for p in (palabras or []) if len(p.strip()) >= 4]))[:30]
    write_json(APRENDIDOS, d)
    if titulos:
        entrenar([(t, nicho, 3 if fuente == "usuario" else 1.5) for t in titulos if t])


def _pedir_lote(lote: list) -> tuple:
    """Pide a la IA nichos para un lote. Devuelve ({id: nicho}, {nicho_nuevo: palabras})."""
    lista = "\n".join(f"- id={v['id']} | {v['titulo'][:110]} | canal: {v.get('canal', '')[:40]}" for v in lote)
    prompt = ("Clasifica cada video de YouTube en un NICHO para canales automatizados (sin rostro). "
              "Usa nombres en español, de 2 a 6 palabras, al nivel de subnicho (ej: 'Historias de venganza y drama familiar'). "
              "Prefiere estos nichos si encajan: " + "; ".join(nombres()) + ". Si ninguno encaja, crea uno nuevo y dame "
              "4-8 palabras clave en inglés y español que lo identifiquen en títulos.\n"
              'Formato exacto: {"videos": [{"id": "...", "nicho": "..."}], "nichos_nuevos": [{"nombre": "...", "palabras": ["..."]}]}\n\n'
              "VIDEOS:\n" + lista)
    try:
        r = llm.ask_json(prompt, 4000)
        if isinstance(r, list):
            r = {"videos": r}
        nuevos = {n.get("nombre"): n.get("palabras", []) for n in (r.get("nichos_nuevos") or []) if isinstance(n, dict) and n.get("nombre")}
        return {x.get("id"): (x.get("nicho") or "").strip() for x in r.get("videos", []) if isinstance(x, dict) and x.get("id")}, nuevos
    except Exception as e:  # noqa: BLE001
        # último intento: aunque el JSON venga roto, rescata los pares id/nicho que sí llegaron completos
        try:
            texto = llm.ask_text(prompt, max_tokens=4000)
            pares = re.findall(r'"id"\s*:\s*"([^"]+)"\s*,\s*"nicho"\s*:\s*"([^"]+)"', texto)
            if pares:
                return dict(pares), {}
        except Exception:  # noqa: BLE001
            pass
        log(f"IA no pudo clasificar un lote de nichos: {e}", "WARN")
        return {}, {}


def aprender_con_ia(videos: list, max_videos: int = 120) -> int:
    """Clasifica con IA los videos sin nicho (en lotes de 25, varios a la vez) y aprende nichos nuevos."""
    pendientes = [v for v in videos if v.get("nicho") == SIN][:max_videos]
    if not pendientes or not llm.disponible():
        return 0
    from concurrent.futures import ThreadPoolExecutor
    lotes = [pendientes[i:i + 25] for i in range(0, len(pendientes), 25)]
    with ThreadPoolExecutor(max_workers=3) as ex:
        resultados = list(ex.map(_pedir_lote, lotes))
    nuevos = {}
    for _, nv in resultados:
        nuevos.update(nv)
    por_id = {k: v for r_, _ in resultados for k, v in r_.items() if v}
    hechos = 0
    for v in pendientes:
        n = por_id.get(v["id"])
        if n:
            asignar("video", v["id"], n, "ia", nuevos.get(n))
            v["nicho"], v["nicho_fuente"] = n, "ia"
            hechos += 1
    return hechos


def nicho_canal(cid: str, titulos_nichos: list) -> str:
    d = aprendidos()
    if cid in d["canales"]:
        return d["canales"][cid]["nicho"]
    validos = [n for n in titulos_nichos if n and n != SIN]
    return Counter(validos).most_common(1)[0][0] if validos else SIN


def palabras_de(titulos: list) -> list:
    """Palabras útiles de una lista de títulos (para que un nicho nuevo se aprenda)."""
    stop = {"the", "and", "with", "this", "that", "from", "what", "when", "your", "they", "their", "have", "para", "como", "esta"}
    c = Counter(w for t in titulos for w in re.findall(r"[a-záéíóúñ]{4,}", t.lower()) if w not in stop)
    return [w for w, _ in c.most_common(8)]


# =====================================================================
# Modelo que APRENDE de tus datos (Naive Bayes local, sin internet)
# =====================================================================
MODELO = DATOS / "modelo_nichos.json"
_STOP_NB = {"the", "a", "an", "of", "and", "to", "in", "on", "for", "with", "is", "was", "this", "that", "it", "at", "by", "from", "as", "are",
            "el", "la", "los", "las", "de", "del", "y", "en", "un", "una", "que", "por", "para", "con", "se", "su", "sus", "al", "lo", "es",
            "how", "why", "what", "who", "when", "you", "your", "his", "her", "their", "they", "he", "she", "we", "i", "my", "me", "como",
            "porque", "por que", "que", "quien", "cuando", "tu", "mi", "yo", "nos", "le", "les", "ever", "never", "most", "more", "mas", "muy"}


def _tokens(texto: str) -> list:
    ws = [w for w in _norm(texto).split() if len(w) > 2 and w not in _STOP_NB and not w.isdigit()]
    return ws + [f"{a}_{b}" for a, b in zip(ws, ws[1:])]


def entrenar(ejemplos: list, guardar: bool = True) -> dict:
    """ejemplos = [(titulo, nicho, peso)]. Suma conteos de palabras por nicho."""
    m = read_json(MODELO, {"conteos": {}, "docs": {}}) if guardar else {"conteos": {}, "docs": {}}
    for titulo, nicho, peso in ejemplos:
        if not nicho or nicho == SIN:
            continue
        c = m["conteos"].setdefault(nicho, {})
        for w in set(_tokens(titulo)):
            c[w] = round(c.get(w, 0) + peso, 2)
        m["docs"][nicho] = round(m["docs"].get(nicho, 0) + peso, 2)
    if guardar:
        # poda: solo palabras vistas al menos 2 veces (evita ruido) cuando el modelo crece
        for nicho, c in m["conteos"].items():
            if len(c) > 4000:
                m["conteos"][nicho] = dict(sorted(c.items(), key=lambda kv: -kv[1])[:4000])
        write_json(MODELO, m)
    return m


def _modelo_mem():
    return read_json_cache(MODELO, {"conteos": {}, "docs": {}}) if MODELO.exists() else {"conteos": {}, "docs": {}}


def predecir_nb(titulo: str, modelo: dict | None = None) -> tuple:
    """(nicho, confianza) según lo aprendido. Sin datos suficientes → Sin clasificar."""
    import math
    m = modelo or _modelo_mem()
    if len(m.get("docs", {})) < 2:
        return SIN, 0.0
    toks = _tokens(titulo)
    vocab = len({w for c in m["conteos"].values() for w in c}) or 1
    total_docs = sum(m["docs"].values())
    puntos = {}
    for nicho, c in m["conteos"].items():
        tot = sum(c.values())
        lp = math.log(m["docs"][nicho] / total_docs)
        conocidas = 0
        for w in toks:
            if w in c:
                conocidas += 1
            lp += math.log((c.get(w, 0) + 0.5) / (tot + 0.5 * vocab))
        puntos[nicho] = (lp, conocidas)
    if not puntos:
        return SIN, 0.0
    orden = sorted(puntos.items(), key=lambda kv: -kv[1][0])
    (n1, (l1, k1)), (n2, (l2, _)) = orden[0], orden[1] if len(orden) > 1 else (orden[0][0], (orden[0][1][0] - 5, 0))
    if k1 == 0:
        return SIN, 0.0
    conf = 1 / (1 + math.exp(-(l1 - l2)))            # probabilidad relativa frente al segundo
    return (n1, round(conf, 2)) if conf >= 0.7 else (SIN, 0.0)


from .utils import read_json_cache  # noqa: E402


# ---------------- IA por CANAL (solo los dudosos) ----------------

def _pedir_canales(lote: list) -> tuple:
    bloques = []
    for c in lote:
        ts = " | ".join(t[:80] for t in c["titulos"][:8])
        bloques.append(f"- id={c['id']} · canal «{c['canal'][:40]}» · descripción: {c.get('desc', '')[:160]!r}\n  títulos: {ts}")
    prompt = ("Asigna UN nicho a cada canal de YouTube (canales automatizados, sin rostro). Mira sus títulos, su nombre y su descripción.\n"
              "Usa EXACTAMENTE uno de estos nombres si encaja: " + "; ".join(nombres()) + ".\n"
              "Solo si ninguno encaja, crea un nombre nuevo en español (2 a 6 palabras, nivel subnicho) y dame 5-8 palabras clave en inglés y español.\n"
              'Formato: {"canales": [{"id": "...", "nicho": "...", "confianza": 0.0-1.0}], "nichos_nuevos": [{"nombre": "...", "palabras": ["..."]}]}\n\n'
              "CANALES:\n" + "\n".join(bloques))
    try:
        r = llm.ask_json(prompt, 3000)
        if isinstance(r, list):
            r = {"canales": r}
        nuevos = {n.get("nombre"): n.get("palabras", []) for n in (r.get("nichos_nuevos") or []) if isinstance(n, dict) and n.get("nombre")}
        return {x.get("id"): (x.get("nicho") or "").strip() for x in r.get("canales", []) if isinstance(x, dict) and x.get("id")}, nuevos
    except Exception as e:  # noqa: BLE001
        log(f"IA no pudo clasificar un lote de canales: {e}", "WARN")
        return {}, {}


def clasificar_canales_con_ia(canales: list) -> int:
    """canales = [{"id", "canal", "titulos", "desc"}] dudosos. Devuelve cuántos clasificó."""
    if not canales or not llm.disponible():
        return 0
    from concurrent.futures import ThreadPoolExecutor
    lotes = [canales[i:i + 12] for i in range(0, min(len(canales), 72), 12)]
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(_pedir_canales, lotes))
    nuevos = {k: v for _, nv in res for k, v in nv.items()}
    hechos = 0
    por_id = {c["id"]: c for c in canales}
    for asign, _ in res:
        for cid, nicho in asign.items():
            if nicho and cid in por_id:
                asignar("canal", cid, nicho, "ia", nuevos.get(nicho), por_id[cid]["titulos"][:15])
                hechos += 1
    return hechos


def entrenar_con_canales(analisis: list):
    """Los canales clasificados con seguridad enseñan su vocabulario al modelo (aprende solo con el uso)."""
    ej = []
    for a in analisis:
        if a.get("nicho") and a.get("nicho") != SIN and (a.get("nicho_conf") or 0) >= 0.6:
            ej += [(v["titulo"], a["nicho"], 1) for v in a.get("videos_lista", [])[:20]]
    if ej:
        entrenar(ej)
