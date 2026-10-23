"""Patrones de miniatura: reconocer, agrupar, medir qué funciona AHORA y buscar miniaturas/canales parecidos.

Todo el análisis de imagen corre en tu PC con OpenCV (gratis, ilimitado, sin API):
  • Huella visual de cada miniatura (~70 números): distribución de colores en una cuadrícula, tonos, caras (YuNet:
    cuántas, tamaño y posición), texto (cuánto, color y posición), brillo/contraste/saturación, elementos rojos
    (flechas, círculos) y pantalla dividida (formato "vs.", antes/después).
  • Rasgos legibles ("Cara grande a la izquierda", "Texto amarillo", "Fondo oscuro"…) → el PATRÓN de la miniatura.
  • Corpus local (datos/miniaturas.json, 30 días) que crece con tus investigaciones, búsquedas y el radar de tendencias.
"""
import math
import statistics
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from .config import DATOS
from .utils import log, read_json, read_json_cache, write_json

CORPUS = DATOS / "miniaturas.json"
VIGENCIA_DIAS = 30
_lock = threading.RLock()
_local = threading.local()


def disponible() -> bool:
    try:
        from .rostros import cv
        cv()
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------- huella visual ----------------

def _bajar(vid: str):
    from .rostros import cv
    cv2 = cv()
    import numpy as np
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    for nombre in ("mqdefault", "hqdefault"):
        try:
            r = _local.s.get(f"https://i.ytimg.com/vi/{vid}/{nombre}.jpg", timeout=12)
            if r.status_code == 200 and len(r.content) > 2500:
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    if nombre == "hqdefault":                      # 480x360 con franjas negras: recorta a 16:9
                        h = img.shape[0]
                        img = img[int(h * .125):int(h * .875)]
                    return cv2.resize(img, (320, 180))
        except Exception:  # noqa: BLE001
            pass
    return None


def _letras(gris):
    """Candidatas a letra con MSER: regiones estables, de tamaño de letra y proporción de letra."""
    from .rostros import cv
    cv2 = cv()
    h, w = gris.shape
    mser = cv2.MSER_create(5, 30, int(0.04 * h * w))
    cajas = []
    for g in (gris, 255 - gris):                         # letras claras sobre oscuro y oscuras sobre claro
        regiones, boxes = mser.detectRegions(g)
        for reg, (x, y, bw, bh) in zip(regiones, boxes):
            if not (h * 0.08 <= bh <= h * 0.45 and bh * 0.12 <= bw <= bh * 1.25):
                continue
            relleno = len(reg) / float(bw * bh)
            if 0.18 <= relleno <= 0.9:
                cajas.append((int(x), int(y), int(bw), int(bh)))
    # quitar duplicados (MSER devuelve regiones anidadas)
    cajas.sort(key=lambda b: -b[2] * b[3])
    finales = []
    for b in cajas:
        if all(not (abs(b[0] - f[0]) < f[2] * .4 and abs(b[1] - f[1]) < f[3] * .4 and abs(b[3] - f[3]) < f[3] * .4) for f in finales):
            finales.append(b)
    return finales


def _texto(gris, bgr):
    """Texto: filas de 3 o más letras alineadas y de altura parecida (las texturas casi nunca hacen eso)."""
    from .rostros import cv
    cv2 = cv()
    import numpy as np
    h, w = gris.shape
    letras = sorted(_letras(gris), key=lambda b: b[0])
    usadas, lineas = set(), []
    for i, a in enumerate(letras):
        if i in usadas:
            continue
        fila, ult = [a], a
        for j in range(i + 1, len(letras)):
            if j in usadas:
                continue
            b = letras[j]
            cy_a, cy_b = ult[1] + ult[3] / 2, b[1] + b[3] / 2
            if (abs(cy_a - cy_b) < ult[3] * .3 and .72 < b[3] / ult[3] < 1.38 and 0 <= b[0] - (ult[0] + ult[2]) < ult[3] * .9):
                fila.append(b)
                ult = b
                usadas.add(j)
        if len(fila) >= 3:
            usadas.add(i)
            x0, y0 = min(b[0] for b in fila), min(b[1] for b in fila)
            x1, y1 = max(b[0] + b[2] for b in fila), max(b[1] + b[3] for b in fila)
            lineas.append((x0, y0, x1 - x0, y1 - y0))
    mascara = np.zeros_like(gris)
    for x, y, bw, bh in lineas:
        mascara[y:y + bh, x:x + bw] = 255
    frac = float((mascara > 0).mean())
    color = "ninguno"
    if lineas:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        dentro = mascara > 0
        claros = dentro & (hsv[..., 2] > 160)
        if claros.sum() > 30:
            hh, ss = hsv[..., 0][claros], hsv[..., 1][claros]
            cuotas = {"blanco": float((ss < 60).mean()),
                      "amarillo": float(((hh >= 18) & (hh <= 38) & (ss >= 60)).mean()),
                      "rojo": float((((hh <= 8) | (hh >= 170)) & (ss >= 60)).mean())}
            color, cuota = max(cuotas.items(), key=lambda kv: kv[1])
            if cuota < .3:
                color = "de color"
        else:
            color = "oscuro"
    ys = [y + bh / 2 for x, y, bw, bh in lineas]
    pos = "ninguna" if not ys else ("arriba" if statistics.mean(ys) < h * .4 else "abajo" if statistics.mean(ys) > h * .62 else "centro")
    return frac, color, pos


def _marcas_rojas(hsv) -> int:
    """Flechas o círculos rojos: formas rojas grandes pero huecas (poco relleno). Una camiseta roja no cuenta."""
    from .rostros import cv
    cv2 = cv()
    import numpy as np
    h, w = hsv.shape[:2]
    rojo = (((hsv[..., 0] <= 8) | (hsv[..., 0] >= 172)) & (hsv[..., 1] > 170) & (hsv[..., 2] > 130)).astype(np.uint8)
    rojo = cv2.morphologyEx(rojo, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(rojo, 8)
    marcas = 0
    for i in range(1, n):
        x, y, cw, ch, a = st[i]
        caja = cw * ch
        if caja >= 0.015 * h * w and a / float(caja) <= 0.28 and max(cw, ch) >= 0.12 * min(h, w) and a >= 60:
            marcas += 1
    return marcas


def huella(img) -> dict:
    """Vector visual + rasgos legibles de una miniatura (320x180 BGR)."""
    from .rostros import cv
    cv2 = cv()
    import numpy as np
    peq = cv2.resize(img, (160, 90))
    lab = cv2.cvtColor(peq, cv2.COLOR_BGR2LAB).astype(np.float32)
    grid = []
    for gy in range(3):
        for gx in range(4):
            celda = lab[gy * 30:(gy + 1) * 30, gx * 40:(gx + 1) * 40].reshape(-1, 3).mean(0)
            grid += [celda[0] / 255, (celda[1] - 128) / 128, (celda[2] - 128) / 128]
    hsv = cv2.cvtColor(peq, cv2.COLOR_BGR2HSV).astype(np.float32)
    peso = (hsv[..., 1] / 255) * (hsv[..., 2] / 255)
    hist = np.histogram(hsv[..., 0], bins=12, range=(0, 180), weights=peso)[0]
    hist = hist / (hist.sum() or 1)
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brillo, contraste = float(gris.mean() / 255), float(gris.std() / 128)
    saturacion = float(hsv[..., 1].mean() / 255)
    # caras (detector YuNet del módulo de rostros)
    caras = []
    try:
        from .rostros import _caras
        caras = _caras(img)
    except Exception:  # noqa: BLE001
        pass
    mayor = max(caras, key=lambda c: c["area"]) if caras else None
    cx = float((mayor["fila"][0] + mayor["fila"][2] / 2) / img.shape[1]) if mayor else 0.5
    area_cara = float(mayor["area"]) if mayor else 0.0
    txt_frac, txt_color, txt_pos = _texto(gris, img)
    # elementos rojos finos (flechas, círculos) y pantalla dividida
    hsv_g = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    marcas = _marcas_rojas(hsv_g)
    izq, der = lab[:, :80].reshape(-1, 3).mean(0), lab[:, 80:].reshape(-1, 3).mean(0)
    sx = np.abs(cv2.Sobel(cv2.cvtColor(peq, cv2.COLOR_BGR2GRAY), cv2.CV_32F, 1, 0))
    perfil = sx.mean(0)
    banda = sx[:, 74:86]
    continuidad = float((banda.max(1) > max(60.0, float(np.percentile(sx, 90)))).mean())   # % de filas con borde en el centro
    pico = float(perfil[74:86].max() / (np.median(perfil) or 1))
    dividida = float(min(1.0, continuidad * min(1.0, pico / 4) * min(1.0, np.linalg.norm(izq - der) / 25)))
    vec = (grid + [x * 2 for x in hist.tolist()] + [brillo, contraste, saturacion] +
           [1.5 * (len(caras) == 0), 1.5 * (len(caras) == 1), 1.5 * (len(caras) >= 2), 6 * area_cara, cx if mayor else 0.5] +
           [4 * txt_frac] + [1.0 * (txt_color == c) for c in ("blanco", "amarillo", "rojo", "de color", "oscuro")] +
           [1.0 * (txt_pos == p) for p in ("arriba", "centro", "abajo")] + [1.5 * min(marcas, 2), 2 * dividida])
    rasgos = []
    if not caras:
        rasgos.append("Sin cara")
    else:
        lado = "a la izquierda" if cx < .38 else "a la derecha" if cx > .62 else "al centro"
        if len(caras) >= 2:
            rasgos.append("Varias caras")
        elif area_cara >= .06:
            rasgos.append(f"Cara grande {lado}")
        else:
            rasgos.append("Cara pequeña")
    if txt_frac >= .05:
        rasgos.append(f"Texto grande {txt_color}" if txt_color not in ("ninguno", "de color") else "Texto grande")
    elif txt_frac >= .012:
        rasgos.append("Poco texto")
    else:
        rasgos.append("Sin texto")
    if brillo < .32:
        rasgos.append("Fondo oscuro")
    elif saturacion > .5 and brillo > .3:
        rasgos.append("Colores intensos")
    elif brillo > .62:
        rasgos.append("Imagen clara")
    elif saturacion < .18:
        rasgos.append("Colores apagados")
    if marcas:
        rasgos.append("Flecha o círculo rojo")
    if dividida > .6:
        rasgos.append("Pantalla dividida")
    return {"v": [round(float(x), 4) for x in vec], "rasgos": rasgos, "patron": " + ".join(rasgos[:4]),
            "brillo": round(brillo, 2), "saturacion": round(saturacion, 2), "caras": len(caras), "texto": round(txt_frac, 3), "color_texto": txt_color}


def similitud(a: list, b: list) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


# ---------------- corpus ----------------

def corpus() -> dict:
    return read_json_cache(CORPUS, {}) or {}


def agregar(videos: list, fuente: str = "", max_n: int = 400, al_avanzar=None) -> int:
    """Calcula la huella de los videos que aún no estén en el corpus (en paralelo) y los guarda."""
    if not disponible():
        return 0
    ya = corpus()
    pend = [v for v in videos if v.get("id") and v["id"] not in ya and (v.get("duracion_seg") or 999) > 180][:max_n]
    if not pend:
        return 0
    hechos = {"n": 0}

    def uno(v):
        img = _bajar(v["id"])
        hechos["n"] += 1
        if al_avanzar and (hechos["n"] % 25 == 0 or hechos["n"] == len(pend)):
            al_avanzar(hechos["n"], len(pend))
        if img is None:
            return None
        try:
            h = huella(img)
        except Exception:  # noqa: BLE001
            return None
        return v["id"], {**h, "titulo": v.get("titulo", ""), "canal": v.get("canal", ""), "canal_id": v.get("canal_id"),
                         "vistas": v.get("vistas"), "vph": v.get("vph"), "outlier": v.get("outlier"), "nicho": v.get("nicho"),
                         "publicado": v.get("publicado"), "fuente": fuente, "fecha": datetime.now().isoformat(timespec="seconds"),
                         "idioma": v.get("idioma")}
    t0 = time.time()
    from .rostros import pool
    nuevos = dict(r for r in pool().map(uno, pend) if r)
    with _lock:
        d = read_json(CORPUS, {}) or {}
        d.update(nuevos)
        limite = (datetime.now() - timedelta(days=VIGENCIA_DIAS)).isoformat()
        d = {k: v for k, v in d.items() if v.get("fecha", "") >= limite}
        write_json(CORPUS, d)
    log(f"Miniaturas: {len(nuevos)} huellas nuevas en {time.time() - t0:.0f} s (corpus: {len(d)}).")
    return len(nuevos)


# ---------------- patrones y tendencias ----------------

def _dias(publicado: str | None) -> int:
    try:
        return max(1, (datetime.now() - datetime.fromisoformat(publicado[:10])).days)
    except Exception:  # noqa: BLE001
        return 9999


def patrones(dias: int = 30, idioma: str = "", min_videos: int = 3) -> dict:
    """Patrones de miniatura ordenados por lo bien que funcionan AHORA (videos recientes)."""
    c = corpus()
    items = [(k, v) for k, v in c.items() if _dias(v.get("publicado")) <= dias and (not idioma or v.get("idioma", "")[:2] == idioma)]
    if not items:
        return {"patrones": [], "rasgos": [], "total": 0, "corpus": len(c)}
    vph_todos = [v.get("vph") or 0 for _, v in items]
    med_vph = statistics.median(vph_todos) or 1
    grupos = agrupar(items)
    recientes = [k for k, v in items if _dias(v.get("publicado")) <= 7]
    out = []
    for nombre, g in grupos.items():
        canales = {v.get("canal_id") for _, v in g}
        if len(g) < min_videos or len(canales) < 2:
            continue
        vph = statistics.mean([v.get("vph") or 0 for _, v in g])
        outs = [v["outlier"] for _, v in g if v.get("outlier")]
        nuevos = sum(1 for k, _ in g if k in recientes)
        cuota_reciente = nuevos / (len(recientes) or 1)
        cuota_total = len(g) / len(items)
        tendencia = round(100 * (cuota_reciente - cuota_total) / cuota_total) if recientes and cuota_total else None
        viral = (math.log10(1 + vph / med_vph) * 60 + (min(statistics.mean(outs), 20) * 2 if outs else 0)
                 + math.log10(len(canales) + 1) * 15 + (max(-10, min(tendencia or 0, 60)) / 6))
        mejores = sorted(g, key=lambda kv: -((kv[1].get("vph") or 0) * (kv[1].get("outlier") or 1)))[:8]
        out.append({"patron": nombre, "rasgos": nombre.split(" + "), "vector": centroide([v["v"] for _, v in g]), "videos": len(g), "canales": len(canales),
                    "vph": round(vph), "vph_x": round(vph / med_vph, 1), "outlier": round(statistics.mean(outs), 1) if outs else None,
                    "tendencia": tendencia, "puntaje": round(viral, 1),
                    "nichos": [n for n, _ in Counter(v.get("nicho") for _, v in g if v.get("nicho") and v.get("nicho") != "Sin clasificar").most_common(3)],
                    "ejemplos": [{"id": k, "titulo": v.get("titulo"), "canal": v.get("canal"), "canal_id": v.get("canal_id"), "vph": v.get("vph"),
                                  "vistas": v.get("vistas"), "outlier": v.get("outlier"), "miniatura": f"https://i.ytimg.com/vi/{k}/mqdefault.jpg",
                                  "url": f"https://www.youtube.com/watch?v={k}", "nicho": v.get("nicho")} for k, v in mejores]})
    out.sort(key=lambda p: -p["puntaje"])
    # rasgos sueltos: cuánto rinden frente al resto
    rasgos = []
    todos = Counter(r for _, v in items for r in set(v["rasgos"]))
    for r, n in todos.items():
        if n < 4:
            continue
        con = [v.get("vph") or 0 for _, v in items if r in v["rasgos"]]
        sin = [v.get("vph") or 0 for _, v in items if r not in v["rasgos"]]
        if con and sin:
            rasgos.append({"rasgo": r, "videos": n, "pct": round(100 * n / len(items)),
                           "rinde": round(statistics.mean(con) / (statistics.mean(sin) or 1), 2)})
    rasgos.sort(key=lambda x: -x["rinde"])
    fuentes = Counter(v.get("fuente") for _, v in items)
    ult = max((v.get("fecha", "") for _, v in items if v.get("fuente") == "tendencias"), default=None)
    return {"patrones": out[:24], "rasgos": rasgos, "total": len(items), "corpus": len(c), "dias": dias,
            "fuentes": dict(fuentes), "tendencias_actualizadas": ult}


def _ranura(r: str) -> str:
    if r.startswith(("Sin cara", "Cara", "Varias caras")):
        return "cara"
    if r.startswith(("Texto", "Poco texto", "Sin texto")):
        return "texto"
    if r in ("Fondo oscuro", "Colores intensos", "Imagen clara", "Colores apagados"):
        return "fondo"
    return r                                     # extras: flecha/círculo rojo, pantalla dividida


def nombre_grupo(rasgos_lista: list) -> str:
    """Nombre del patrón según lo que tiene la MAYORÍA de las miniaturas del grupo."""
    n = len(rasgos_lista)
    partes = []
    for ranura in ("cara", "texto", "fondo"):
        c = Counter(r for rs in rasgos_lista for r in rs if _ranura(r) == ranura)
        if c:
            r, k = c.most_common(1)[0]
            if ranura != "fondo" or k >= n * .5:
                partes.append(r)
    for extra in ("Flecha o círculo rojo", "Pantalla dividida"):
        if sum(1 for rs in rasgos_lista if extra in rs) >= n * .5:
            partes.append(extra)
    return " + ".join(partes)


def centroide(vs: list) -> list:
    return [round(sum(col) / len(vs), 4) for col in zip(*vs)] if vs else []


def agrupar(items: list, umbral: float = 0.9) -> dict:
    """Agrupa miniaturas por parecido visual (no por el nombre exacto) y nombra cada grupo por mayoría."""
    import numpy as np
    if not items:
        return {}
    orden = sorted(items, key=lambda kv: -(kv[1].get("vph") or 0))
    X = np.array([kv[1]["v"] for kv in orden], dtype=np.float32)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    centros, miembros = [], []
    for i in range(len(orden)):
        if centros:
            sims = np.array(centros) @ X[i]
            j = int(sims.argmax())
            if sims[j] >= umbral:
                miembros[j].append(i)
                c = X[miembros[j]].mean(0)
                centros[j] = c / (np.linalg.norm(c) + 1e-9)
                continue
        centros.append(X[i].copy())
        miembros.append([i])
    # une grupos con la misma base (cara + texto + fondo) que son visualmente casi iguales
    fusion = []
    for i, m in enumerate(miembros):
        base = " + ".join(nombre_grupo([orden[k][1]["rasgos"] for k in m]).split(" + ")[:3])
        dest = next((f for f in fusion if f["base"] == base and float(f["centro"] @ centros[i]) >= .85), None)
        if dest:
            dest["m"] += m
        else:
            fusion.append({"base": base, "centro": centros[i], "m": list(m)})
    grupos = defaultdict(list)
    for f in fusion:
        g = [orden[i] for i in f["m"]]
        grupos[nombre_grupo([v["rasgos"] for _, v in g])] += g     # grupos con el mismo nombre se unen
    return grupos


_MAT = {"id": None, "claves": [], "X": None}


def _matriz():
    """Todas las huellas normalizadas en una matriz (se rehace solo si el catálogo cambió): comparar es instantáneo."""
    import numpy as np
    c = corpus()
    if _MAT["id"] != id(c):
        claves = [k for k, v in c.items() if v.get("v")]
        X = np.array([c[k]["v"] for k in claves], dtype=np.float32) if claves else np.zeros((0, 1), np.float32)
        if len(claves):
            X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
        _MAT.update(id=id(c), claves=claves, X=X)
    return c, _MAT["claves"], _MAT["X"]


def parecidas(vec: list, excluir: str = "", n: int = 40, umbral: float = 0.86) -> dict:
    """Miniaturas visualmente parecidas a `vec` y los canales que más las usan."""
    import numpy as np
    c, claves, X = _matriz()
    if not claves:
        return {"videos": [], "canales": []}
    q = np.array(vec, dtype=np.float32)
    q /= (np.linalg.norm(q) + 1e-9)
    s_ = X @ q
    orden = np.argsort(-s_)[:n + 1]
    sims = [(float(s_[i]), claves[i], c[claves[i]]) for i in orden if claves[i] != excluir][:n]
    videos = [{"id": k, "similitud": round(100 * s), "titulo": v.get("titulo"), "canal": v.get("canal"), "canal_id": v.get("canal_id"),
               "patron": v.get("patron"), "vph": v.get("vph"), "vistas": v.get("vistas"), "outlier": v.get("outlier"),
               "miniatura": f"https://i.ytimg.com/vi/{k}/mqdefault.jpg", "url": f"https://www.youtube.com/watch?v={k}"}
              for s, k, v in sims[:n] if s >= umbral]
    por_canal = defaultdict(list)
    for v in videos:
        if v.get("canal_id"):
            por_canal[v["canal_id"]].append(v)
    canales = sorted(({"id": cid, "canal": g[0]["canal"], "parecidas": len(g), "similitud": max(x["similitud"] for x in g),
                       "vph": round(statistics.mean([x.get("vph") or 0 for x in g]))} for cid, g in por_canal.items()),
                     key=lambda c_: (-c_["parecidas"], -c_["similitud"]))
    return {"videos": videos, "canales": canales[:20]}


def huella_de(vid: str) -> dict | None:
    v = corpus().get(vid)
    if v:
        return v
    img = _bajar(vid)
    return huella(img) if img is not None else None


def vector_patron(nombre: str, dias: int = 90) -> list | None:
    p = next((x for x in patrones(dias, min_videos=1)["patrones"] if x["patron"] == nombre), None)
    return p["vector"] if p else None
