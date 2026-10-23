"""Detección de patrones en lo que ya funcionó: títulos, miniaturas, etiquetas y SEO.

Compara los videos que más superan a su canal (outliers) contra el resto para decir QUÉ se repite en los ganadores:
fórmulas de título, tipos de título, ideas repetidas entre canales, colores y estilo de miniatura, miniaturas casi iguales,
etiquetas y calidad SEO. Todo con datos públicos; las miniaturas se analizan con Pillow si está instalado.
"""
import io
import math
import re
import statistics
from collections import Counter, defaultdict

import requests

from .config import DATOS
from .utils import read_json, write_json

CARPETA = DATOS / "patrones"
STOP = {"the", "a", "an", "of", "and", "to", "in", "on", "for", "with", "is", "was", "this", "that", "it", "at", "by", "from", "as",
        "el", "la", "los", "las", "de", "del", "y", "en", "un", "una", "que", "por", "para", "con", "se", "su", "sus", "al", "lo", "es"}

RASGOS = [
    ("numero", "Empieza con número o lista", r"^\s*(\d+|top\s*\d+|los\s+\d+|las\s+\d+)\b"),
    ("pregunta", "Es una pregunta", r"\?|^\s*(why|how|what|who|where|when|is|are|did|does|por qué|cómo|qué|quién|dónde|cuándo|¿)"),
    ("negativo", "Connotación negativa", r"\b(never|worst|nobody|no one|stop|mistake|wrong|dark|deadly|dangerous|banned|failed|lost|ruined|"
                                         r"nunca|peor|nadie|error|prohibid|peligros|mortal|oscur|fracas|arruin)"),
    ("curiosidad", "Curiosidad o secreto", r"\b(secret|truth|hidden|untold|nobody knows|real reason|what happened|mystery|"
                                            r"secreto|verdad|oculto|nadie sabe|la razón|lo que pasó|misterio)"),
    ("superlativo", "Superlativo (el más…)", r"\b(richest|biggest|largest|most|best|greatest|deadliest|oldest|"
                                             r"más rico|más grande|el más|la más|mejor|mayor)"),
    ("historia", "Formato historia / narración", r"\b(story|stories|the rise|the fall|downfall|became|who\s+\w+ed|historia|así fue|se convirtió)"),
    ("tiempo", "Periodo de tiempo", r"\b(\d{4}s?|\d+\s*(years?|days?|hours?|años|días|horas)|century|siglo|decade|década|ago|hace)\b"),
    ("comparacion", "Comparación (vs.)", r"\b(vs\.?|versus|than|compared|contra|comparad)\b"),
    ("tu", "Le habla al espectador", r"\b(you|your|tú|tu|te|usted)\b"),
    ("mayusculas", "PALABRAS EN MAYÚSCULAS", r"\b[A-ZÁÉÍÓÚÑ]{4,}\b"),
    ("separador", "Usa « | », « : » o « - »", r"[|:]| - "),
    ("emoji", "Usa emojis", r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"),
]
TIPOS_TITULO = [("Lista", "numero"), ("Pregunta", "pregunta"), ("Comparación", "comparacion"), ("Secreto / curiosidad", "curiosidad"),
                ("Negativo", "negativo"), ("Historia / narración", "historia"), ("Superlativo", "superlativo")]


def _palabras(t: str) -> set:
    return {w for w in re.findall(r"[a-záéíóúñü0-9']+", (t or "").lower()) if w not in STOP and len(w) > 2}


def _plantilla(t: str) -> str:
    """Primeras 3 palabras normalizadas: los números se vuelven N (así '10 richest…' y '7 richest…' son la misma fórmula)."""
    ws = re.findall(r"[a-záéíóúñü0-9']+", (t or "").lower())[:3]
    return " ".join("N" if w.isdigit() else w for w in ws)


def _prom(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else 0


# ---------------- títulos ----------------

def analizar_titulos(vids: list) -> dict:
    total = len(vids) or 1
    rasgos = []
    for clave, nombre, pat in RASGOS:
        rx = re.compile(pat, re.I if clave != "mayusculas" else 0)
        con = [v for v in vids if rx.search(v.get("titulo", ""))]
        sin = [v for v in vids if not rx.search(v.get("titulo", ""))]
        if len(con) < 3:
            continue
        oc, os_ = _prom([v.get("outlier") for v in con]), _prom([v.get("outlier") for v in sin])
        rasgos.append({"id": clave, "nombre": nombre, "pct": round(100 * len(con) / total), "n": len(con),
                       "outlier_con": oc, "outlier_sin": os_, "lift": round(oc / os_, 2) if os_ else None,
                       "ejemplos": [v["titulo"] for v in sorted(con, key=lambda x: -(x.get("outlier") or 0))[:3]]})
    rasgos.sort(key=lambda r: -(r["lift"] or 0))
    # fórmulas (plantillas de inicio) que se repiten
    grupos = defaultdict(list)
    for v in vids:
        k = _plantilla(v.get("titulo", ""))
        if len(k.split()) >= 2:
            grupos[k].append(v)
    formulas = [{"formula": k, "n": len(g), "canales": len({v.get("canal_id") for v in g}), "outlier": _prom([v.get("outlier") for v in g]),
                 "ejemplos": [v["titulo"] for v in sorted(g, key=lambda x: -(x.get("outlier") or 0))[:3]]}
                for k, g in grupos.items() if len(g) >= 3]
    formulas.sort(key=lambda f: (-f["canales"], -f["outlier"]))
    # tipos de título
    tipos = []
    asignado = {}
    for v in vids:
        t = v.get("titulo", "")
        asignado[v["id"]] = next((nom for nom, cl in TIPOS_TITULO if re.search(dict((c, p) for c, _, p in RASGOS)[cl], t, re.I)), "Directo / descriptivo")
    for nom in [n for n, _ in TIPOS_TITULO] + ["Directo / descriptivo"]:
        g = [v for v in vids if asignado[v["id"]] == nom]
        if g:
            tipos.append({"tipo": nom, "n": len(g), "pct": round(100 * len(g) / total), "outlier": _prom([v.get("outlier") for v in g]),
                          "vistas": round(_prom([v.get("vistas") for v in g]))})
    largos = [len(v.get("titulo", "")) for v in vids]
    top = sorted(vids, key=lambda x: -(x.get("outlier") or 0))[:max(5, len(vids) // 5)]
    return {"rasgos": rasgos, "formulas": formulas[:15], "tipos": tipos, "tipo_por_video": asignado,
            "largo_prom": round(_prom(largos)), "largo_top": round(_prom([len(v.get("titulo", "")) for v in top]))}


def ideas_repetidas(vids: list, umbral: float = 0.38) -> list:
    """Agrupa videos con títulos parecidos (misma idea) — si la idea aparece en varios canales, está validada."""
    items = [(v, _palabras(v.get("titulo", ""))) for v in sorted(vids, key=lambda x: -(x.get("outlier") or 0))]
    usados, grupos = set(), []
    for i, (v, pv) in enumerate(items):
        if v["id"] in usados or len(pv) < 2:
            continue
        g = [v]
        for w, pw in items[i + 1:]:
            if w["id"] in usados or len(pw) < 2:
                continue
            if len(pv & pw) / len(pv | pw) >= umbral:
                g.append(w)
        if len(g) >= 2:
            usados.update(x["id"] for x in g)
            comunes = Counter(w for x in g for w in _palabras(x["titulo"]))
            grupos.append({"idea": " · ".join(w for w, c in comunes.most_common(4) if c >= 2) or v["titulo"][:50],
                           "n": len(g), "canales": len({x.get("canal_id") for x in g}), "outlier": _prom([x.get("outlier") for x in g]),
                           "videos": [{k: x.get(k) for k in ("id", "titulo", "canal", "url", "miniatura", "vistas", "outlier")} for x in g[:6]]})
    grupos.sort(key=lambda g: (-g["canales"], -g["outlier"]))
    return grupos[:20]


# ---------------- etiquetas y SEO ----------------

def analizar_seo(vids: list) -> dict:
    tags = Counter()
    tags_out = defaultdict(list)
    puntajes = []
    for v in vids:
        tg = [t.lower().strip() for t in (v.get("tags") or []) if t.strip()]
        for t in set(tg):
            tags[t] += 1
            tags_out[t].append(v.get("outlier") or 0)
        titulo = _palabras(v.get("titulo", ""))
        desc = (v.get("desc") or "")
        p, checks = 0, {}
        checks["etiquetas"] = len(tg) >= 5
        checks["titulo_en_etiquetas"] = bool(titulo & {w for t in tg for w in _palabras(t)})
        checks["titulo_en_descripcion"] = bool(titulo & _palabras(desc[:250])) if desc else False
        checks["descripcion_larga"] = len(desc) >= 200
        checks["hashtags"] = "#" in desc
        p = round(100 * sum(checks.values()) / len(checks))
        v["seo"] = p
        puntajes.append((p, v.get("outlier") or 0, checks))
    con_desc = sum(1 for v in vids if v.get("desc"))
    nombres = {"etiquetas": "5 o más etiquetas", "titulo_en_etiquetas": "Palabras del título repetidas en etiquetas",
               "titulo_en_descripcion": "Palabras del título en las primeras líneas de la descripción",
               "descripcion_larga": "Descripción de 200+ caracteres", "hashtags": "Usa #hashtags"}
    practicas = []
    for k, n in nombres.items():
        si = [o for p, o, c in puntajes if c[k]]
        no = [o for p, o, c in puntajes if not c[k]]
        if (k in ("titulo_en_descripcion", "descripcion_larga", "hashtags")) and not con_desc:
            continue
        practicas.append({"practica": n, "pct": round(100 * len(si) / (len(puntajes) or 1)), "outlier_si": _prom(si), "outlier_no": _prom(no)})
    top = sorted(puntajes, key=lambda x: -x[1])[:max(5, len(puntajes) // 5)]
    return {"etiquetas": [{"tag": t, "n": c, "outlier": _prom(tags_out[t])} for t, c in tags.most_common(40)],
            "pct_con_etiquetas": round(100 * sum(1 for v in vids if v.get("tags")) / (len(vids) or 1)),
            "etiquetas_prom": round(_prom([len(v.get("tags") or []) for v in vids]), 1),
            "seo_prom": round(_prom([p for p, _, _ in puntajes])), "seo_top": round(_prom([p for p, _, _ in top])),
            "practicas": practicas, "con_descripcion": con_desc}


# ---------------- miniaturas ----------------

def _dhash(img) -> int:
    g = img.convert("L").resize((9, 8))
    px = list(g.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if px[y * 9 + x] > px[y * 9 + x + 1] else 0)
    return bits


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(x) for x in c[:3])


def _rasgos_imagen(contenido: bytes) -> dict:
    from PIL import Image, ImageFilter, ImageStat  # noqa: F401
    img = Image.open(io.BytesIO(contenido)).convert("RGB").resize((160, 90))
    hsv = img.convert("HSV")
    st = ImageStat.Stat(img.convert("L"))
    sat = ImageStat.Stat(hsv).mean[1] / 255
    bordes = ImageStat.Stat(img.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0] / 255
    pal = img.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    paleta_raw = pal.getpalette()[:15]
    cuenta = sorted(pal.getcolors(), reverse=True)
    paleta = [_hex(paleta_raw[i * 3:i * 3 + 3]) for _, i in cuenta[:4]]
    r, g, b = ImageStat.Stat(img).mean
    px = list(hsv.getdata())
    rojos = sum(1 for h, s_, v in px if (h < 12 or h > 240) and s_ > 110 and v > 90) / len(px)
    amarillos = sum(1 for h, s_, v in px if 25 < h < 45 and s_ > 110 and v > 120) / len(px)
    return {"brillo": round(st.mean[0] / 255, 3), "contraste": round(st.stddev[0] / 128, 3), "saturacion": round(sat, 3),
            "detalle": round(bordes, 3), "calidez": round((r - b) / 255, 3), "rojo": round(rojos, 3), "amarillo": round(amarillos, 3),
            "paleta": paleta, "hash": _dhash(img)}


def estilo_miniatura(m: dict) -> str:
    if m["brillo"] < 0.33:
        return "Oscura / dramática"
    if m["rojo"] > 0.12 or (m["amarillo"] > 0.12 and m["contraste"] > 0.45):
        return "Colores de alerta (rojo/amarillo)"
    if m["saturacion"] > 0.45 and m["brillo"] > 0.45:
        return "Brillante y colorida"
    if m["contraste"] > 0.55:
        return "Alto contraste"
    if m["saturacion"] < 0.2:
        return "Apagada / casi sin color"
    return "Equilibrada"


def analizar_miniaturas(vids: list, max_n: int = 120) -> dict:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return {"error": "Instala Pillow (instalar_actualizar.bat) para analizar miniaturas."}
    elegidos = sorted(vids, key=lambda x: -(x.get("outlier") or 0))[:max_n]
    sesion = requests.Session()

    def bajar(v):
        try:
            r = sesion.get(f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg", timeout=12)
            if r.status_code == 200:
                return v, _rasgos_imagen(r.content)
        except Exception:  # noqa: BLE001
            pass
        return v, None
    from .rostros import pool
    res = [(v, m) for v, m in pool().map(bajar, elegidos) if m]
    if not res:
        return {"error": "No pude descargar las miniaturas (¿sin internet?)."}
    for v, m in res:
        m["estilo"] = estilo_miniatura(m)
        v["mini"] = {k: m[k] for k in ("brillo", "contraste", "saturacion", "estilo", "paleta")}
    n_top = max(5, len(res) // 4)
    top, resto = res[:n_top], res[n_top:]
    metricas = []
    for k, nombre in (("brillo", "Brillo"), ("contraste", "Contraste"), ("saturacion", "Saturación de color"), ("detalle", "Detalle / texto"),
                      ("rojo", "Presencia de rojo"), ("amarillo", "Presencia de amarillo"), ("calidez", "Tonos cálidos")):
        a, b = _prom([m[k] for _, m in top]), _prom([m[k] for _, m in resto]) if resto else 0
        metricas.append({"id": k, "nombre": nombre, "top": a, "resto": b, "dif": round((a - b) / b * 100) if b else None})
    estilos = []
    for e in sorted({m["estilo"] for _, m in res}):
        g = [(v, m) for v, m in res if m["estilo"] == e]
        estilos.append({"estilo": e, "n": len(g), "pct": round(100 * len(g) / len(res)), "outlier": _prom([v.get("outlier") for v, _ in g]),
                        "ejemplos": [{"miniatura": v["miniatura"], "url": v["url"], "titulo": v["titulo"]} for v, _ in g[:4]]})
    estilos.sort(key=lambda e: -e["outlier"])
    colores = Counter(c for _, m in top for c in m["paleta"][:3])
    # miniaturas casi iguales (mismo diseño o plantilla)
    usados, parecidas = set(), []
    for i, (v, m) in enumerate(res):
        if v["id"] in usados:
            continue
        g = [v] + [w for w, n in res[i + 1:] if w["id"] not in usados and bin(m["hash"] ^ n["hash"]).count("1") <= 12]
        if len(g) >= 2:
            usados.update(x["id"] for x in g)
            parecidas.append({"n": len(g), "canales": len({x.get("canal_id") for x in g}), "outlier": _prom([x.get("outlier") for x in g]),
                              "videos": [{k: x.get(k) for k in ("titulo", "canal", "url", "miniatura", "outlier")} for x in g[:6]]})
    parecidas.sort(key=lambda g: (-g["canales"], -g["n"]))
    return {"analizadas": len(res), "metricas": metricas, "estilos": estilos, "colores_top": [c for c, _ in colores.most_common(8)],
            "parecidas": parecidas[:12]}


# ---------------- conclusiones ----------------

def conclusiones(t: dict, s: dict, m: dict) -> list:
    out = []
    for r in t["rasgos"][:3]:
        if r["lift"] and r["lift"] >= 1.15:
            out.append(f"Los títulos con «{r['nombre'].lower()}» rinden {r['lift']}x más que el resto ({r['pct']} % de los videos).")
    if t["formulas"]:
        f = t["formulas"][0]
        out.append(f"Fórmula repetida en {f['canales']} canales: «{f['formula']}…» ({f['n']} videos, {f['outlier']}x de outlier promedio).")
    if t["largo_top"] and t["largo_prom"]:
        out.append(f"Los títulos ganadores miden {t['largo_top']} caracteres en promedio (el resto, {t['largo_prom']}).")
    if m and not m.get("error"):
        for x in sorted([x for x in m["metricas"] if x["dif"] is not None], key=lambda x: -abs(x["dif"]))[:2]:
            if abs(x["dif"]) >= 10:
                out.append(f"Las miniaturas de los videos top tienen {abs(x['dif'])} % {'más' if x['dif'] > 0 else 'menos'} {x['nombre'].lower()}.")
        if m["estilos"]:
            e = m["estilos"][0]
            out.append(f"El estilo de miniatura que mejor rinde es «{e['estilo']}» ({e['outlier']}x).")
    if s["practicas"]:
        mejor = max(s["practicas"], key=lambda p: (p["outlier_si"] - p["outlier_no"]))
        if mejor["outlier_si"] > mejor["outlier_no"]:
            out.append(f"SEO: «{mejor['practica']}» aparece en los videos que más rinden ({mejor['outlier_si']}x vs {mejor['outlier_no']}x).")
    return out


def analizar(clave: str, vids: list, miniaturas: bool = True, forzar: bool = False) -> dict:
    CARPETA.mkdir(exist_ok=True)
    ruta = CARPETA / f"{re.sub(r'[^a-zA-Z0-9_-]', '', clave)}.json"
    if not forzar:
        hit = read_json(ruta, None)
        if hit and hit.get("n") == len(vids) and (hit.get("miniaturas") or not miniaturas):
            return hit
    vids = [dict(v) for v in vids if v.get("titulo")]
    t = analizar_titulos(vids)
    s = analizar_seo(vids)
    m = analizar_miniaturas(vids) if miniaturas else None
    grupos = ideas_repetidas(vids)
    tipo_v = t.pop("tipo_por_video")
    out = {"n": len(vids), "titulos": t, "seo": s, "miniaturas": m, "ideas": grupos, "conclusiones": conclusiones(t, s, m),
           "clasificacion": {v["id"]: {"titulo": tipo_v.get(v["id"]), "miniatura": (v.get("mini") or {}).get("estilo"), "seo": v.get("seo")} for v in vids}}
    write_json(ruta, out)
    return out
