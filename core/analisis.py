"""Motor de análisis de NichosForge Pro.

Por canal calcula lo que muestran herramientas tipo vidIQ / NexLev con datos públicos:
visitas, me gusta, comentarios, interacción, suscriptores, etiquetas, categoría, CPM y RPM estimados,
ganancias estimadas, techo, piso, outliers, mejores días para publicar y si cumple como referente.
"""
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .config import CATEGORIAS
from .youtube import dur_iso

ES = {"de", "la", "el", "los", "las", "que", "por", "para", "con", "una", "como", "más", "historia", "cómo", "qué",
      "porque", "nunca", "secreto", "verdad", "sus", "del", "fue", "esta", "este", "lo", "se", "mejores", "por qué"}
EN = {"the", "of", "and", "to", "in", "why", "how", "what", "is", "was", "this", "that", "with", "for", "you",
      "never", "story", "who", "their", "secret", "truth", "they", "from", "best"}
STOP = (ES | EN | {"a", "an", "on", "at", "it", "are", "be", "by", "y", "en", "un", "su", "al", "es", "no", "i", "my",
                   "your", "he", "she", "his", "her", "we", "#shorts", "shorts", "vs", "part", "parte", "video",
                   "videos", "new", "nuevo", "official", "full", "will", "can", "all", "todo", "todos", "out", "about",
                   "has", "have", "had", "not", "do", "does", "did", "if", "so", "or", "but", "o", "pero", "si", "ya",
                   "le", "les", "me", "te", "mi", "tu", "yo", "ni", "muy", "hay", "son", "ser", "fue", "era"})

EVITAR = {
    "Música / recopilaciones": ["lyrics", "letra", "official audio", "audio oficial", "full album", "compilation",
                                "compilación", "recopilación", "remix", "lofi", "lo-fi"],
    "Películas o series": ["full movie", "película completa", "pelicula completa", "full episode", "capítulo completo"],
    "Violencia gráfica": ["gore", "beheaded", "masacre", "decapit", "graphic footage"],
    "Temas de adultos": ["nsfw", "18+", "onlyfans", "porn", "xxx"],
    "Drogas o alcohol": ["cocaine", "cocaína", "drug lord", "narco", "marihuana"],
    "Política / guerras actuales": ["trump", "biden", "democrat", "republican", "elecciones", "ukraine war", "gaza"],
    "Desinformación médica": ["cure cancer", "cura el cáncer", "doctors hate", "miracle cure", "cura milagrosa"],
}
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
TRAMOS = [("< 1 min", 0, 60), ("1–4 min", 60, 240), ("4–8 min", 240, 480), ("8–15 min", 480, 900),
          ("15–30 min", 900, 1800), ("30+ min", 1800, 10 ** 9)]


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _fecha(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def idioma(canal: dict, vids: list) -> str:
    langs = []
    for v in [canal.get("snippet", {}).get("defaultLanguage")] + [
            (x.get("snippet", {}).get("defaultAudioLanguage") or x.get("snippet", {}).get("defaultLanguage"))
            for x in vids[:20]]:
        if v:
            langs.append(v.split("-")[0].lower())
    if langs:
        top = Counter(langs).most_common(1)[0][0]
        if top in ("en", "es"):
            return top
    palabras = re.findall(r"[a-záéíóúñü']+", " ".join(x.get("snippet", {}).get("title", "") for x in vids[:30]).lower())
    es, en = sum(w in ES for w in palabras), sum(w in EN for w in palabras)
    if es == en == 0:
        return "otro"
    return "es" if es > en else "en"


def riesgos(canal: dict, vids: list) -> list:
    flags = set()
    texto = " ".join([canal.get("snippet", {}).get("title", ""), canal.get("snippet", {}).get("description", "")]
                     + [x.get("snippet", {}).get("title", "") for x in vids[:30]]).lower()
    for etiqueta, palabras in EVITAR.items():
        if any(p in texto for p in palabras):
            flags.add(etiqueta)
    cats = Counter(x.get("snippet", {}).get("categoryId") for x in vids)
    if cats and cats.most_common(1)[0][0] == "10":
        flags.add("Música / recopilaciones")
    if canal.get("status", {}).get("madeForKids"):
        flags.add("Para niños (COPPA)")
    return sorted(flags)


def tipo_contenido(visitas: list) -> tuple:
    if len(visitas) < 5 or not sum(visitas):
        return "sin_datos", "Muy pocos videos para clasificar."
    top = max(visitas) / sum(visitas)
    med_mean = statistics.median(visitas) / statistics.mean(visitas)
    if top >= 0.5 or med_mean < 0.15:
        return "trendy", f"Su video techo concentra el {top:.0%} de las visitas: depende de virales."
    if med_mean >= 0.35 and top < 0.3:
        return "evergreen", "Visitas bien repartidas: crecimiento progresivo y estable."
    return "mixto", "Combina videos estables con algunos picos virales."


PRIMERA_PERSONA = re.compile(r"\b(i|i'm|i've|my|me|we|our|yo|mi|mis|nosotros|nuestro|nuestra|conmigo)\b", re.I)
PERSONAL = re.compile(r"\b(vlog|vlogs|podcast|live|livestream|directo|en vivo|reaction|reacciono|reaccionando|react|unboxing|"
                      r"q&a|preguntas y respuestas|my day|un día conmigo|get ready|grwm|tour|haul|storytime|mi vida|rutina|challenge|reto)\b", re.I)
NARRATIVO = re.compile(r"\b(story|stories|documentary|explained|history|facts|secret|secrets|truth|mystery|mysteries|top|why|how|what happened|"
                       r"the rise|the fall|downfall|untold|hidden|forgotten|legend|legends|richest|biggest|historia|historias|documental|"
                       r"explicad[oa]|secreto|secretos|misterio|misterios|curiosidades|verdad|leyenda|nunca|nadie|por qué|lo que|así fue)\b", re.I)
DESC_AUTO = re.compile(r"(narrat|voice ?over|ai voice|voz (en off|ia|artificial)|faceless|stock footage|for entertainment purposes|"
                       r"educational purposes|fines educativos|fines de entretenimiento|fair use|uso justo|documentar|documentary channel)", re.I)
JOVEN = re.compile(r"\b(minecraft|fortnite|roblox|anime|gaming|gamer|tiktok|meme|memes|brainrot|skibidi|kpop|k-pop|freefire|free fire|gta)\b", re.I)
MAYOR = re.compile(r"\b(elderly|grandma|grandpa|grandmother|grandfather|retire|retirement|pension|seniors?|abuel[oa]s?|jubilad|"
                   r"bible|biblia|dios|god|inheritance|herencia|old money|nursing home|asilo|war|guerra|history|historia|royal|realeza|"
                   r"1950s|1960s|1970s|old hollywood|vintage)\b", re.I)


def automatizacion(canal: dict, vids: list, pct_largos: float, pct_shorts: float, por_semana: float, edad: int, n_videos: int, cat: str) -> dict:
    """¿Es un canal automatizado (sin rostro)? Señales de Aprende a Monetizar: nadie a cámara, narración/stock/IA,
    volumen alto, branding global y clickbait. Sin ver las imágenes, se estima con títulos, descripción y ritmo."""
    titulos = [v.get("snippet", {}).get("title", "") for v in vids[:40]]
    n = max(1, len(titulos))
    desc = (canal.get("snippet", {}).get("description") or "") + " " + " ".join((v.get("snippet", {}).get("description") or "")[:300] for v in vids[:8])
    p1 = sum(1 for t in titulos if PRIMERA_PERSONA.search(t)) / n
    pers = sum(1 for t in titulos if PERSONAL.search(t)) / n
    narr = sum(1 for t in titulos if NARRATIVO.search(t)) / n
    score, senales = 35, []
    if pct_largos >= 0.6:
        score += 12; senales.append("➕ Videos largos (8+ min)")
    if por_semana >= 3:
        score += 15; senales.append(f"➕ Volumen alto ({por_semana:.1f} videos/semana)")
    elif por_semana >= 1:
        score += 7; senales.append(f"➕ Sube seguido ({por_semana:.1f}/semana)")
    if edad and n_videos / max(edad, 1) >= 0.35 and edad <= 730:
        score += 8; senales.append("➕ Muchos videos en poco tiempo")
    if narr >= 0.3:
        score += 14; senales.append("➕ Títulos de narración/documental/clickbait")
    if DESC_AUTO.search(desc):
        score += 10; senales.append("➕ La descripción menciona narración, IA o stock")
    if p1 <= 0.08:
        score += 10; senales.append("➕ Títulos sin primera persona (sin 'yo/mi')")
    elif p1 >= 0.3:
        score -= 22; senales.append("➖ Muchos títulos en primera persona (marca personal)")
    if pers >= 0.15:
        score -= 25; senales.append("➖ Vlogs, directos, reacciones o retos")
    if str(cat) in ("20", "10"):
        score -= 10; senales.append("➖ Categoría de videojuegos o música")
    if pct_shorts >= 0.7:
        score -= 8; senales.append("➖ Casi todo son Shorts")
    score = int(max(0, min(100, score)))
    tipo = "automatizado" if score >= 65 else "posible" if score >= 45 else "marca"
    return {"auto_score": score, "auto_tipo": tipo, "auto_senales": senales}


def audiencia(vids: list, aj_largo_titulo: int = 55) -> dict:
    """Aprende a Monetizar: mayores → títulos largos o semi largos, edición simple, RPM alto. Jóvenes → títulos minimalistas."""
    titulos = [v.get("snippet", {}).get("title", "") for v in vids[:40]]
    if not titulos:
        return {"audiencia": "general", "audiencia_nota": "Sin datos."}
    largo = statistics.mean(len(t) for t in titulos)
    texto = " ".join(titulos) + " " + " ".join(" ".join(v.get("snippet", {}).get("tags") or []) for v in vids[:20])
    m, j = len(MAYOR.findall(texto)), len(JOVEN.findall(texto))
    puntos = (1 if largo >= aj_largo_titulo else -1 if largo <= 38 else 0) + (1 if m > j and m >= 3 else 0) - (1 if j > m and j >= 3 else 0)
    if puntos >= 1:
        return {"audiencia": "mayores", "audiencia_nota": f"Títulos largos ({largo:.0f} caracteres) y temas de adultos: edición simple y RPM alto."}
    if puntos <= -1:
        return {"audiencia": "jovenes", "audiencia_nota": f"Títulos cortos ({largo:.0f} caracteres) o temas juveniles: más edición y RPM más bajo."}
    return {"audiencia": "general", "audiencia_nota": f"Títulos de {largo:.0f} caracteres: audiencia mixta."}


def salud(a: dict) -> dict:
    """Estado del canal para colores y para Nichi: rentable, prometedor, dudoso o peligroso."""
    if a["riesgos"]:
        return {"salud": "peligroso", "salud_nota": "Toca temas que espantan anunciantes: " + ", ".join(a["riesgos"])}
    if a["es_referente"] or (a["ingreso_mes"] >= 3000 and a["score"] >= 70):
        return {"salud": "rentable", "salud_nota": f"Gana aprox. ${a['ingreso_mes']:,}/mes y cumple casi todo."}
    if a["score"] >= 55 or a["visitas_mes"] >= 300_000:
        return {"salud": "prometedor", "salud_nota": "Buen ritmo, pero aún no cumple todos los criterios de referente."}
    return {"salud": "dudoso", "salud_nota": "Pocas visitas o poco estable para replicar."}


TEMPORADA = {1: 0.75, 2: 0.85, 3: 0.95, 4: 0.95, 5: 1.0, 6: 1.0, 7: 0.95, 8: 0.95, 9: 1.0, 10: 1.12, 11: 1.25, 12: 1.35}
NOMBRE_MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def monetizacion(cat: str, pais: str, lang: str, pct_shorts: float, pct_largos: float, aj: dict,
                 nicho: str = "", audiencia: str = "general", dur_min: float = 0) -> dict:
    """CPM y RPM adaptados a cada canal: nicho (o categoría) × país/idioma × audiencia × duración × temporada."""
    partes = []
    cpm_nicho = (aj.get("cpm_nicho") or {}).get(nicho) if nicho else None
    if cpm_nicho:
        cpm_base = float(cpm_nicho)
        partes.append(f"CPM del nicho «{nicho}» ${cpm_base:.2f}")
    else:
        cpm_base = float(aj["cpm_categoria"].get(str(cat), 6.0))
        partes.append(f"CPM de {CATEGORIAS.get(str(cat), 'categoría general')} ${cpm_base:.2f}")
    fp = aj["factor_pais"].get((pais or "").upper())
    if fp is not None:
        partes.append(f"país {pais.upper()} ×{float(fp):.2f}")
    else:
        fp = float(aj["factor_idioma"].get(lang, aj["factor_idioma"].get("otro", 0.4)))
        partes.append(f"idioma {lang} ×{fp:.2f}")
    fa = float((aj.get("factor_audiencia") or {}).get(audiencia, 1.0))
    if fa != 1:
        partes.append(f"audiencia {audiencia} ×{fa:.2f}")
    ft = 1.0
    if aj.get("temporada", True):
        m = datetime.now().month
        ft = TEMPORADA.get(m, 1.0)
        if ft != 1:
            partes.append(f"temporada de {NOMBRE_MES[m]} ×{ft:.2f}")
    cpm = cpm_base * float(fp) * fa * ft
    rpm = cpm * float(aj["reparto_youtube"]) * float(aj["vistas_monetizadas"])
    if pct_largos >= 0.5:                      # más minutos = más anuncios en medio (mid-rolls)
        fd = 1.35 if dur_min >= 25 else 1.25 if dur_min >= 15 else float(aj.get("bonus_largos", 1.2)) if dur_min >= 8 else 1.0
        if fd != 1:
            rpm *= fd
            partes.append(f"videos de {dur_min:.0f} min ×{fd:.2f}")
    if pct_shorts >= 0.7:
        rpm *= float(aj["factor_shorts"])
        cpm *= float(aj["factor_shorts"])
        partes.append("casi todo Shorts")
    return {"cpm": round(cpm, 2), "rpm": round(rpm, 2), "rpm_bajo": round(rpm * 0.7, 2), "rpm_alto": round(rpm * 1.3, 2),
            "base": " · ".join(partes)}


def nicho_de_canal(cid: str, titulos: list, tags: list, descripcion: str = "", nombre: str = "") -> tuple:
    """(nicho, confianza). Lo que asignaste tú o la IA manda; si no, votan todos sus títulos + nombre + descripción."""
    try:
        from . import clasificador as clf
        ap = clf.aprendidos()
        if cid in ap["canales"]:
            return ap["canales"][cid]["nicho"], 1.0
        n, conf, _ = clf.clasificar_canal(titulos, tags, descripcion, nombre)
        return ("" if n == clf.SIN else n), conf
    except Exception:  # noqa: BLE001
        return "", 0.0


def analizar_canal(canal: dict, vids_raw: list, aj: dict) -> dict:
    sn, st = canal.get("snippet", {}), canal.get("statistics", {})
    ahora = datetime.now(timezone.utc)
    creado = _fecha(sn["publishedAt"]) if sn.get("publishedAt") else ahora
    edad = max(1, (ahora - creado).days)
    total = int(st.get("viewCount", 0) or 0)
    subs = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0) or 0)
    n_videos = int(st.get("videoCount", 0) or 0)
    largo_seg = float(aj.get("minutos_video_largo") or 8) * 60

    vids = []
    for v in vids_raw:
        vs, vd = v.get("statistics", {}), v.get("snippet", {})
        if not vd.get("publishedAt"):
            continue
        pub = _fecha(vd["publishedAt"])
        dur = dur_iso(v.get("contentDetails", {}).get("duration"))
        visitas = int(vs.get("viewCount", 0) or 0)
        likes = int(vs.get("likeCount", 0) or 0)
        coms = int(vs.get("commentCount", 0) or 0)
        dias = max(1, (ahora - pub).days)
        vids.append({"id": v["id"], "titulo": vd.get("title", ""), "url": f"https://www.youtube.com/watch?v={v['id']}",
                     "miniatura": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg", "publicado": vd["publishedAt"][:10],
                     "dia_semana": pub.weekday(), "hora_utc": pub.hour, "dias": dias, "duracion_seg": dur,
                     "vistas": visitas, "likes": likes, "comentarios": coms, "vistas_dia": round(visitas / dias),
                     "interaccion": round(100 * (likes + coms) / visitas, 2) if visitas else 0,
                     "categoria": vd.get("categoryId", ""), "tags": (vd.get("tags") or [])[:30],
                     "es_short": dur <= 180})
    visitas = [v["vistas"] for v in vids]
    largos = [v for v in vids if not v["es_short"]]
    pct_shorts = (len(vids) - len(largos)) / len(vids) if vids else 0
    pct_largos = sum(1 for v in vids if v["duracion_seg"] >= largo_seg) / len(vids) if vids else 0

    # visitas al mes (la API no las entrega para canales ajenos: se estiman)
    recientes = sum(v["vistas"] for v in vids if v["dias"] <= 30)
    if edad <= 365:
        mes, metodo = total / edad * 30, "promedio de vida del canal (total ÷ edad × 30)"
    else:
        mes = sum(v["vistas"] / max(v["dias"], 30) * 30 for v in vids) if vids else total / edad * 30
        mes, metodo = max(mes, recientes), "ritmo mensual de sus últimos videos"

    med = statistics.median(visitas) if visitas else 0
    prom = statistics.mean(visitas) if visitas else 0
    for v in vids:
        v["outlier"] = round(v["vistas"] / med, 1) if med else None
    techo_v = max(vids, key=lambda v: v["vistas"]) if vids else None
    piso = 0
    if visitas:
        bajos = sorted(visitas)[:max(3, len(visitas) // 4)]
        piso = sum(bajos) / len(bajos)

    lang = idioma(canal, vids_raw)
    flags = riesgos(canal, vids_raw)
    tipo, nota = tipo_contenido(visitas)
    cat = Counter(v["categoria"] for v in vids).most_common(1)[0][0] if vids else ""
    pais = sn.get("country", "")
    aud = audiencia(vids_raw)
    nicho, nicho_conf = nicho_de_canal(canal["id"], [v["titulo"] for v in vids], [v["tags"] for v in vids],
                                       sn.get("description", ""), sn.get("title", ""))
    dur_prom = statistics.mean([v["duracion_seg"] for v in largos]) / 60 if largos else 0
    mon = monetizacion(cat, pais, lang, pct_shorts, pct_largos, aj, nicho, aud["audiencia"], dur_prom)

    likes_tot = sum(v["likes"] for v in vids)
    coms_tot = sum(v["comentarios"] for v in vids)
    v_tot = sum(visitas) or 1

    # cuándo publica y cómo le va
    por_dia = defaultdict(list)
    for v in vids:
        por_dia[v["dia_semana"]].append(v["vistas"])
    semana = [{"dia": DIAS[i], "videos": len(por_dia[i]), "vistas_prom": round(statistics.mean(por_dia[i])) if por_dia[i] else 0}
              for i in range(7)]
    duraciones = []
    for nombre, a, b in TRAMOS:
        xs = [v["vistas"] for v in vids if a <= v["duracion_seg"] < b]
        duraciones.append({"tramo": nombre, "videos": len(xs), "vistas_prom": round(statistics.mean(xs)) if xs else 0})

    # etiquetas: frecuencia y visitas promedio de los videos que las usan
    tag_v = defaultdict(list)
    for v in vids:
        for t in {t.lower().strip() for t in v["tags"] if t.strip()}:
            tag_v[t].append(v["vistas"])
    etiquetas = sorted(({"tag": t, "usos": len(xs), "vistas_prom": round(statistics.mean(xs))} for t, xs in tag_v.items()),
                       key=lambda x: (-x["usos"], -x["vistas_prom"]))[:40]

    edad_max, mes_min = int(aj["edad_max_canal_dias"]), int(aj["visitas_mes_min"])
    checks = [[f"Creado hace {edad_max} días o menos", edad <= edad_max],
              [f"{mes_min:,} visitas al mes o más (estimado)".replace(",", "."), mes >= mes_min],
              ["Sin temas a evitar", not flags],
              [f"La mayoría de videos dura {int(largo_seg // 60)} min o más", pct_largos >= 0.5],
              ["Canal en inglés (fuente de ideas)", lang == "en"]]
    es_referente = checks[0][1] and checks[1][1] and checks[2][1] and lang == "en"

    s_vis = _clamp((math.log10(mes + 1) - 4) / 3) * 35
    s_edad = 20 if edad <= 90 else 20 - (edad - 90) / 275 * 10 if edad <= 365 else 5 if edad <= 730 else 0
    s_rep = _clamp((math.log10(prom + 1) - 3) / 3) * 20
    s_estable = _clamp(med / prom if prom else 0) * 10
    s_pocos = 5 if n_videos and n_videos <= 60 and mes >= 300_000 else 0
    score = round(_clamp(s_vis + s_edad + s_rep + pct_largos * 10 + s_estable + s_pocos - 15 * len(flags), 0, 100), 1)

    if len(vids) >= 2:
        span = max(v["dias"] for v in vids) - min(v["dias"] for v in vids)
        por_semana = len(vids) / max(1, span) * 7
    else:
        por_semana = 0
    thumbs = sn.get("thumbnails") or {}
    auto = automatizacion(canal, vids_raw, pct_largos, pct_shorts, por_semana, edad, n_videos, cat)
    out = {
        "id": canal["id"], "canal": sn.get("title", ""), "handle": sn.get("customUrl", ""),
        "descripcion": (sn.get("description") or "")[:400],
        "url": f"https://www.youtube.com/channel/{canal['id']}",
        "avatar": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
        "banner": ((canal.get("brandingSettings") or {}).get("image") or {}).get("bannerExternalUrl", ""),
        "pais": pais, "idioma": lang, "creado": creado.strftime("%Y-%m-%d"), "edad_dias": edad,
        "suscriptores": subs, "visitas_totales": total, "videos": n_videos,
        "rol": "referente" if es_referente else ("competidor" if lang == "es" else ("ingles" if lang == "en" else "otro")),
        "visitas_mes": round(mes), "metodo_mes": metodo, "visitas_30d_nuevos": recientes,
        "promedio": round(prom), "mediana": round(med), "techo": techo_v["vistas"] if techo_v else 0,
        "techo_titulo": techo_v["titulo"] if techo_v else "", "techo_url": techo_v["url"] if techo_v else "",
        "piso": round(piso), "likes_prom": round(likes_tot / len(vids)) if vids else 0,
        "comentarios_prom": round(coms_tot / len(vids)) if vids else 0,
        "interaccion": round(100 * (likes_tot + coms_tot) / v_tot, 2), "likes_por_mil": round(1000 * likes_tot / v_tot, 1),
        "vistas_por_sub": round(prom / subs, 2) if subs else None,
        "subs_por_video": round(subs / n_videos) if subs and n_videos else None,
        "duracion_prom_min": round(statistics.mean([v["duracion_seg"] for v in largos]) / 60, 1) if largos else 0,
        "pct_largos": round(pct_largos * 100), "pct_shorts": round(pct_shorts * 100), "videos_semana": round(por_semana, 1),
        "dias_ultimo_video": min((v["dias"] for v in vids), default=None),
        "categoria_id": cat, "categoria": CATEGORIAS.get(str(cat), "Otra") if cat else "", "nicho": nicho, "nicho_conf": nicho_conf,
        "tipo": tipo, "tipo_nota": nota, **mon,
        "ingreso_mes": round(mes / 1000 * mon["rpm"]), "ingreso_mes_bajo": round(mes / 1000 * mon["rpm_bajo"]),
        "ingreso_mes_alto": round(mes / 1000 * mon["rpm_alto"]), "ingreso_anio": round(mes * 12 / 1000 * mon["rpm"]),
        "ingreso_por_video": round(prom / 1000 * mon["rpm"]),
        "ingreso_total_est": round(total / 1000 * mon["rpm"]),
        "riesgos": flags, "checks": checks, "es_referente": es_referente, "score": score,
        "semana": semana, "duraciones": duraciones, "etiquetas": etiquetas,
        "videos_lista": sorted(vids, key=lambda v: v["publicado"]),
        "palabras": palabras_clave([v["titulo"] for v in vids], [v["vistas"] for v in vids], 25),
        **auto, **aud,
    }
    out.update(salud(out))
    return out


def palabras_clave(titulos: list, pesos: list | None = None, n: int = 30) -> list:
    cnt = Counter()
    for i, t in enumerate(titulos):
        ws = [w for w in re.findall(r"[a-záéíóúñü0-9']+", (t or "").lower()) if w not in STOP and len(w) > 2 and not w.isdigit()]
        peso = 1 + math.log10((pesos[i] if pesos else 0) + 1)
        for w in ws:
            cnt[w] += peso
        for a, b in zip(ws, ws[1:]):
            cnt[f"{a} {b}"] += peso * 1.6
    return [[k, round(v, 1)] for k, v in cnt.most_common(n)]


def frases_semilla(analisis: list, n: int = 6) -> list:
    """Frases para buscar más canales parecidos a los seleccionados: etiquetas y combinaciones de los títulos."""
    pesos = Counter()
    for a in analisis:
        for e in a.get("etiquetas", [])[:15]:
            if 1 <= len(e["tag"].split()) <= 5:
                pesos[e["tag"]] += e["usos"] * 1.5
        for k, p in a.get("palabras", [])[:15]:
            if " " in k:
                pesos[k] += p
    salida, vistos = [], set()
    for frase, _ in pesos.most_common(60):
        clave = frozenset(frase.split())
        if clave in vistos or any(clave <= v or v <= clave for v in vistos):
            continue
        vistos.add(clave)
        salida.append(frase)
        if len(salida) >= n:
            break
    return salida


def ligero(a: dict) -> dict:
    """Versión para tablas: sin listas pesadas."""
    out = {k: v for k, v in a.items() if k not in ("videos_lista", "semana", "duraciones", "etiquetas", "palabras", "descripcion")}
    top = sorted(a.get("videos_lista", []), key=lambda v: v["vistas"], reverse=True)[:3]
    out["top3"] = [{"titulo": v["titulo"], "miniatura": v["miniatura"], "vistas": v["vistas"], "url": v["url"]} for v in top]
    if a.get("rostro"):
        out["rostro"] = {k: a["rostro"].get(k) for k in ("veredicto", "confianza", "motivo")}
    if a.get("monetizado"):
        out["monetizado"] = {k: a["monetizado"].get(k) for k in ("veredicto", "confianza", "titulo", "motivo")}
    out["tags_top"] = [e["tag"] for e in a.get("etiquetas", [])[:8]]
    return out
