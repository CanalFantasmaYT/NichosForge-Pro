"""Trabajos en segundo plano de NichosForge Pro: analizar tu canal, buscar nichos, buscar similares.

Solo corre un trabajo a la vez (protege tu cuota). El panel consulta el progreso y puede detenerlo.
"""
import json
import threading
import time
import uuid
from collections import Counter
from datetime import datetime

from . import llm
from . import youtube as yt
from .analisis import analizar_canal, frases_semilla, ligero
from .config import DATOS, ajustes
from .utils import log as log_global, read_json, read_json_cache, write_json

CANALES = DATOS / "canales.json"
MI_CANAL = DATOS / "mi_canal.json"
BUSQUEDAS = DATOS / "busquedas.json"
GUARDADOS = DATOS / "guardados.json"
ETAPAS = ["lista", "filtro1", "filtro2", "filtro3", "elegido", "descartado"]

_trabajo = {"estado": "inactivo", "log": []}
_cancelar = threading.Event()
_lock = threading.Lock()


class Cancelado(Exception):
    pass


def estado() -> dict:
    return {k: v for k, v in _trabajo.items()}


def cancelar():
    if _trabajo.get("estado") == "trabajando":
        _cancelar.set()


def _log(msg: str, pct: float | None = None, nivel: str = "INFO"):
    if _cancelar.is_set():
        raise Cancelado()
    _trabajo["paso"] = msg
    if pct is not None:
        _trabajo["pct"] = round(max(0, min(100, pct)))
    _trabajo["log"] = (_trabajo.get("log") or [])[-200:] + [f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"]
    log_global(msg, nivel)


def _lanzar(titulo: str, fn, *args):
    with _lock:
        if _trabajo.get("estado") == "trabajando":
            raise RuntimeError(f"Ya hay un trabajo en curso: {_trabajo.get('titulo')}. Espera o pulsa Detener.")
        _cancelar.clear()
        _trabajo.clear()
        _trabajo.update({"estado": "trabajando", "titulo": titulo, "inicio": time.time(), "pct": 0, "log": [],
                         "paso": "Iniciando…", "resultado": None})

    def run():
        try:
            _trabajo["resultado"] = fn(*args)
            _trabajo["estado"] = "listo"
            _trabajo["pct"] = 100
        except Cancelado:
            _trabajo["estado"] = "detenido"
            _trabajo["paso"] = "Detenido por ti."
        except Exception as e:  # noqa: BLE001
            _trabajo["estado"] = "error"
            _trabajo["paso"] = f"{e}"
            _trabajo["log"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {e}")
            log_global(str(e), "ERROR")
        finally:
            _trabajo["fin"] = time.time()
            try:
                yt._guardar_cuota(True)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=run, daemon=True).start()


# ---------- almacén de canales analizados ----------

def canal_crudo(cid: str) -> dict | None:
    """El análisis tal como se guardó (sin las visitas reales del seguimiento). Usar para modificar y guardar."""
    return read_json_cache(CANALES, {}).get(cid)


def canal(cid: str) -> dict | None:
    """Análisis del canal con las visitas REALES del seguimiento cuando ya hay mediciones."""
    from .monetizado import resumen
    from .rostros import aplicar
    from .seguimiento import enriquecer
    a = canal_crudo(cid)
    if not a:
        return None
    a = aplicar(enriquecer(a))
    a["monetizado"] = resumen(cid, a)
    return a


_fondo = {"estado": "inactivo", "tareas": 0}
_fondo_lock = threading.Lock()


def fondo() -> dict:
    return dict(_fondo)


def _en_fondo(titulo: str, ids_canales: list, videos: list, fuente: str):
    """Verificación de rostros y catálogo de miniaturas SIN bloquear nuevas búsquedas."""
    def avisar(msg):
        _fondo["paso"] = msg

    def run():
        with _fondo_lock:
            _fondo.update(estado="trabajando", titulo=titulo, paso="Empezando…", tareas=_fondo.get("tareas", 0) + 1)
        try:
            if ids_canales and ajustes().get("verificar_rostros", True):
                from . import rostros
                if rostros.opencv_ok():
                    pend = [c for c in ids_canales if not rostros.resultado(c)][:80]
                    if pend:
                        rostros.verificar_lote(pend, lambda h, t: avisar(f"👁 Verificando rostros ({h}/{t})…"))
            if ids_canales and ajustes().get("leer_paginas_youtube", False):
                from . import monetizado
                monetizado.verificar_lote(ids_canales[:60], lambda h, t: avisar(f"💰 Verificando monetización ({h}/{t})…"))
            if videos:
                from . import miniaturas
                if miniaturas.disponible():
                    miniaturas.agregar(videos, fuente, 400, lambda h, t: avisar(f"🎨 Analizando miniaturas ({h}/{t})…"))
        except Exception as e:  # noqa: BLE001
            log_global(f"Tarea de fondo: {e}", "WARN")
        finally:
            with _fondo_lock:
                _fondo["tareas"] = max(0, _fondo.get("tareas", 1) - 1)
                if not _fondo["tareas"]:
                    _fondo.update(estado="listo", paso="Listo", fin=time.time())
    threading.Thread(target=run, daemon=True).start()


def _catalogar_miniaturas(videos: list, fuente: str, pct0: float, pct1: float):
    """Guarda la huella visual de las miniaturas (en tu PC, sin cuota) para detectar patrones."""
    try:
        from . import miniaturas
        if not miniaturas.disponible() or not videos:
            return
        _log(f"Analizando el diseño de {min(len(videos), 400)} miniaturas…", pct0)
        miniaturas.agregar(videos, fuente, 400, lambda h, t: _log(f"Miniaturas analizadas ({h}/{t})…", pct0 + (pct1 - pct0) * h / t))
    except Cancelado:
        raise
    except Exception as e:  # noqa: BLE001
        _log(f"No pude analizar las miniaturas ({e}).", nivel="WARN")


def _verificar_rostros(ids: list, pct0: float, pct1: float):
    """Fase local (gratis, sin cuota): mira miniaturas y fotogramas para confirmar quién sale a cámara."""
    try:
        from . import rostros
        if not rostros.opencv_ok():
            _log("Para verificar rostros instala OpenCV (instalar_actualizar.bat).", nivel="WARN")
            return
        pend = [c for c in ids if not rostros.resultado(c)][:80]
        if not pend:
            return
        _log(f"Verificando rostros en miniaturas y fotogramas de {len(pend)} canales (en tu PC, sin cuota)…", pct0)
        rostros.verificar_lote(pend, lambda h, t: _log(f"Verificando rostros ({h}/{t})…", pct0 + (pct1 - pct0) * h / t) if h % 5 == 0 or h == t else None)
    except Cancelado:
        raise
    except Exception as e:  # noqa: BLE001
        _log(f"No pude verificar rostros ({e}); sigo con lo demás.", nivel="WARN")


def analizar_uno(cid: str) -> dict | None:
    """Analiza un solo canal fuera de los trabajos en segundo plano (unas 3 unidades de cuota)."""
    ch = yt.canales([cid]).get(cid)
    if not ch:
        return None
    a = analizar_canal(ch, yt.ultimos_videos(ch, int(ajustes()["videos_por_canal"])), ajustes())
    _guardar_canales([a])
    return a


def _foto_gratis(chs: dict):
    """Si ya leímos canales de la API, aprovecha para guardar la foto de los que sigues (sin gastar cuota)."""
    try:
        from . import seguimiento as seg
        seguidos = seg.ids_seguidos()
        seg.registrar({k: v for k, v in (chs or {}).items() if k in seguidos})
    except Exception:  # noqa: BLE001
        pass


def ligero_de(cid: str) -> dict | None:
    a = canal(cid)
    return ligero(a) if a else None


def _guardar_canales(lista: list):
    with _lock:
        todos = read_json(CANALES, {})
        ahora = datetime.now().isoformat(timespec="seconds")
        for a in lista:
            a["analizado"] = ahora
            todos[a["id"]] = a
        write_json(CANALES, todos)


def _analizar(ids: list, pct_ini: float = 30, pct_fin: float = 95) -> list:
    aj = ajustes()
    ids = list(dict.fromkeys(i for i in ids if i))
    if not ids:
        return []
    previos = read_json_cache(CANALES, {})
    frescos, pendientes = [], []
    for cid in ids:
        p = previos.get(cid)
        if p and p.get("analizado") and (datetime.now() - datetime.fromisoformat(p["analizado"])).total_seconds() < float(aj["cache_horas"]) * 3600:
            frescos.append(p)
        else:
            pendientes.append(cid)
    _log(f"Leyendo datos de {len(pendientes)} canales ({len(frescos)} ya estaban analizados)…", pct_ini)
    chs = yt.canales(pendientes) if pendientes else {}
    _foto_gratis(chs)
    nuevos = []
    for i, cid in enumerate(pendientes, 1):
        ch = chs.get(cid)
        if not ch:
            continue
        _log(f"Analizando {i}/{len(pendientes)}: {ch['snippet'].get('title', cid)}",
             pct_ini + (pct_fin - pct_ini) * i / max(1, len(pendientes)))
        try:
            vids = yt.ultimos_videos(ch, int(aj["videos_por_canal"]))
        except RuntimeError as e:
            if "cuota" in str(e).lower() or "clave" in str(e).lower():
                raise
            _log(f"{ch['snippet'].get('title')}: {e}", nivel="WARN")
            continue
        nuevos.append(analizar_canal(ch, vids, aj))
    _guardar_canales(nuevos)
    por_id = {a["id"]: a for a in frescos + nuevos}
    return [por_id[c] for c in ids if c in por_id]


def top_referentes(n: int = 5) -> list:
    mios = ids_mis_canales()
    cs = [canal(a["id"]) for a in read_json_cache(CANALES, {}).values() if a.get("es_referente") and a["id"] not in mios]
    return [{k: a[k] for k in ("id", "canal", "avatar", "visitas_mes", "edad_dias", "ingreso_mes", "score")}
            for a in sorted(cs, key=lambda a: -a["score"])[:n]]


# ---------- mi canal ----------

MIS = DATOS / "mis_canales.json"


def _mis() -> dict:
    d = read_json(MIS, None)
    if d is None:                                   # migra el formato viejo (un solo canal)
        viejo = read_json(MI_CANAL, None)
        d = {"canales": [], "activo": None}
        if viejo and viejo.get("id"):
            d["canales"].append({k: viejo.get(k) for k in ("id", "ref", "actualizado", "sugeridas")})
            d["activo"] = viejo["id"]
        write_json(MIS, d)
    return d


def ids_mis_canales() -> set:
    return {c["id"] for c in _mis()["canales"]}


def mis_canales() -> list:
    d = _mis()
    out = []
    for m in d["canales"]:
        a = canal(m["id"])
        if a:
            out.append({**ligero(a), **{k: m.get(k) for k in ("ref", "actualizado")}, "activo": m["id"] == d["activo"]})
    return out


def mi_canal() -> dict | None:
    d = _mis()
    if not d["canales"]:
        return None
    activo = d["activo"] if any(c["id"] == d["activo"] for c in d["canales"]) else d["canales"][0]["id"]
    meta = next(c for c in d["canales"] if c["id"] == activo)
    a = canal(activo)
    return {**meta, "analisis": a} if a else None


def activar_mi_canal(cid: str):
    d = _mis()
    if not any(c["id"] == cid for c in d["canales"]):
        raise ValueError("Ese canal no está conectado.")
    d["activo"] = cid
    write_json(MIS, d)


def quitar_mi_canal(cid: str):
    d = _mis()
    d["canales"] = [c for c in d["canales"] if c["id"] != cid]
    if d["activo"] == cid:
        d["activo"] = d["canales"][0]["id"] if d["canales"] else None
    write_json(MIS, d)


def _analizar_un_canal_mio(ref: str, pct0: float = 5, pct1: float = 95):
    aj = ajustes()
    _log(f"Buscando tu canal {ref}…", pct0)
    cid = yt.resolver_canal(ref)
    if not cid:
        raise RuntimeError(f"No encontré el canal {ref}.")
    chs1 = yt.canales([cid])
    ch = chs1.get(cid)
    if not ch:
        raise RuntimeError("YouTube no devolvió datos de ese canal.")
    _log(f"Leyendo los últimos videos de {ch['snippet']['title']}…", pct0 + (pct1 - pct0) * 0.3)
    vids = yt.ultimos_videos(ch, 50)
    _log("Calculando métricas, etiquetas y ganancias…", pct0 + (pct1 - pct0) * 0.8)
    a = analizar_canal(ch, vids, aj)
    _guardar_canales([a])
    try:
        from . import seguimiento as seg
        seg.registrar(chs1)                      # empieza a medir tu canal desde ya
    except Exception:  # noqa: BLE001
        pass
    d = _mis()
    meta = {"id": cid, "ref": ref, "actualizado": datetime.now().isoformat(timespec="seconds"), "sugeridas": frases_semilla([a], 8)}
    d["canales"] = [c for c in d["canales"] if c["id"] != cid] + [meta]
    write_json(MIS, d)
    (DATOS / "sugerencias.json").unlink(missing_ok=True)   # que Nichi vuelva a pensar con tu canal nuevo
    return a


def _analizar_mi_canal(ref: str | None = None):
    d = _mis()
    if not ref:
        actual = next((c for c in d["canales"] if c["id"] == d["activo"]), None)
        ref = (actual or {}).get("ref") or ajustes().get("mi_canal")
    if not ref:
        raise RuntimeError("Escribe tu canal (@handle o link).")
    a = _analizar_un_canal_mio(ref)
    activar_mi_canal(a["id"])
    if ajustes().get("verificar_rostros", True):
        _verificar_rostros([a["id"]], 96, 99)
    _log(f"Listo: {a['canal']} · {len(a['videos_lista'])} videos analizados.", 100)
    return {"tipo": "mi_canal", "id": a["id"]}


def analizar_mi_canal(ref: str | None = None):
    _lanzar("Analizar mi canal", _analizar_mi_canal, ref)


def actualizar_mis_canales():
    def _run():
        cs = _mis()["canales"]
        if not cs:
            raise RuntimeError("Aún no conectas canales.")
        for i, c in enumerate(cs):
            _analizar_un_canal_mio(c.get("ref") or c["id"], 100 * i / len(cs), 100 * (i + 1) / len(cs))
        _log(f"Listo: {len(cs)} canales actualizados.", 100)
        return {"tipo": "mi_canal", "id": _mis()["activo"]}
    _lanzar("Actualizar mis canales", _run)


def sugerencias_mi_canal(traducir: bool = True) -> dict:
    d = mi_canal()
    if not d:
        raise RuntimeError("Primero analiza tu canal.")
    es = frases_semilla([d["analisis"]], 8)
    en = []
    if traducir and llm.disponible():
        try:
            r = llm.ask_json(
                "Eres experto en nichos de YouTube. Mi canal se llama \"%s\" (%s). Sus temas: %s.\n"
                "Propón 8 frases de búsqueda en INGLÉS (2-5 palabras, como las escribe la audiencia) para encontrar "
                "canales referentes en inglés del mismo nicho, y 4 subnichos más específicos.\n"
                "Responde SOLO JSON: {\"en\": [\"...\"], \"subnichos\": [\"...\"]}"
                % (d["analisis"]["canal"], d["analisis"]["categoria"], ", ".join(es)))
            en = [x for x in r if isinstance(x, str)] if isinstance(r, list) else (r or {}).get("en", []) + (r or {}).get("subnichos", [])
        except Exception as e:  # noqa: BLE001
            log_global(f"IA no disponible: {e}", "WARN")
    return {"es": es, "en": en, "con_ia": llm.disponible()}


# ---------- búsquedas ----------

def busquedas() -> list:
    return read_json(BUSQUEDAS, [])


def busqueda(bid: str) -> dict:
    for b in busquedas():
        if b["id"] == bid:
            return b
    raise ValueError("Búsqueda no encontrada.")


def borrar_busqueda(bid: str):
    write_json(BUSQUEDAS, [b for b in busquedas() if b["id"] != bid])


def _guardar_busqueda(reg: dict):
    with _lock:
        lista = [b for b in read_json(BUSQUEDAS, []) if b["id"] != reg["id"]]
        lista.insert(0, reg)
        write_json(BUSQUEDAS, lista[:40])


def _buscar(p: dict):
    frases = [(f.get("idioma") or "", f["texto"].strip()) for f in p.get("frases", []) if f.get("texto", "").strip()]
    if not frases:
        raise RuntimeError("Escribe al menos una frase de búsqueda.")
    excluir = set(p.get("excluir") or [])
    excluir |= ids_mis_canales()
    veces, orden, vids_busq = {}, [], {}
    for i, (lang, frase) in enumerate(frases):
        _log(f"Buscando [{(lang or 'todos').upper()}] «{frase}»", 3 + 22 * i / len(frases))
        reg = (p.get("region") or "auto").strip()
        region = ("US" if lang == "en" else "") if reg.lower() in ("auto", "") else ("" if reg.lower() == "todos" else reg.upper())
        try:
            items = yt.buscar_videos(frase, lang, int(p.get("dias") or 365), 50, region,
                                     p.get("duracion") or "", p.get("orden") or "viewCount", int(p.get("paginas") or 1))
        except RuntimeError as e:
            if "cuota" in str(e).lower() or "clave" in str(e).lower() or i == len(frases) - 1 and not veces:
                raise
            _log(f"«{frase}» falló ({e}); sigo con las demás frases.", nivel="WARN")
            continue
        for it in items:
            cid = it["snippet"]["channelId"]
            vid = (it.get("id") or {}).get("videoId")
            if cid in excluir:
                continue
            if vid:
                vids_busq[vid] = frase
            if cid not in veces:
                orden.append(cid)
            veces[cid] = veces.get(cid, 0) + 1
    ranked = sorted(orden, key=lambda c: (-veces[c], orden.index(c)))[:int(p.get("max_canales") or 30)]
    for ref in p.get("canales") or []:
        try:
            cid = yt.resolver_canal(ref)
        except RuntimeError as e:
            _log(f"{ref}: {e}", nivel="WARN")
            continue
        if cid and cid not in ranked:
            ranked.append(cid)
    _log(f"{len(veces)} canales encontrados; se analizan los {len(ranked)} más relevantes.", 25)
    lista = _analizar(ranked, 28, 85)

    # videos virales de la búsqueda (outliers frente a la mediana de su canal)
    _log("Calculando videos virales (outliers)…", 88)
    medianas = {a["id"]: a["mediana"] for a in lista}
    nombres = {a["id"]: a["canal"] for a in lista}
    virales = []
    try:
        vids_virales = yt.videos(list(vids_busq)[:150])
    except RuntimeError as e:
        if "cuota" in str(e).lower() or "clave" in str(e).lower():
            raise
        _log(f"No pude leer los videos virales ({e}); guardo los canales igual.", nivel="WARN")
        vids_virales = []
    for v in vids_virales:
        sn, st = v["snippet"], v.get("statistics", {})
        visitas = int(st.get("viewCount", 0) or 0)
        med = medianas.get(sn["channelId"])
        dias = max(1, (datetime.now().astimezone() - datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))).days)
        dur = yt.dur_iso(v.get("contentDetails", {}).get("duration"))
        virales.append({"id": v["id"], "titulo": sn.get("title"), "canal": nombres.get(sn["channelId"], sn.get("channelTitle")),
                        "canal_id": sn["channelId"], "url": f"https://www.youtube.com/watch?v={v['id']}",
                        "miniatura": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg", "vistas": visitas,
                        "likes": int(st.get("likeCount", 0) or 0), "comentarios": int(st.get("commentCount", 0) or 0),
                        "dias": dias, "vistas_dia": round(visitas / dias), "duracion_seg": dur,
                        "outlier": round(visitas / med, 1) if med else None, "frase": vids_busq.get(v["id"]),
                        "publicado": sn["publishedAt"][:10], "tags": (sn.get("tags") or [])[:25], "desc": (sn.get("description") or "")[:500]})
    virales.sort(key=lambda x: (x["outlier"] or 0, x["vistas"]), reverse=True)
    reg = {"id": p.get("_id") or uuid.uuid4().hex[:10], "tipo": p.get("tipo") or "palabra",
           "titulo": p.get("titulo") or ", ".join(f for _, f in frases)[:80],
           "frases": [{"idioma": l, "texto": f} for l, f in frases], "parametros": {k: v for k, v in p.items() if not k.startswith("_")},
           "fecha": datetime.now().isoformat(timespec="seconds"), "canales": [a["id"] for a in lista], "virales": virales[:120],
           "origen": p.get("origen") or [], "filtro_auto": bool(p.get("filtro_auto"))}
    _guardar_busqueda(reg)
    if p.get("tipo") == "miniatura":                 # la búsqueda por miniatura necesita las huellas ya
        _catalogar_miniaturas(virales[:150], "busqueda", 97, 99)
        _en_fondo("Verificando rostros de la búsqueda", [a["id"] for a in lista], [], "busqueda")
    else:
        _en_fondo("Verificando rostros y miniaturas de la búsqueda", [a["id"] for a in lista], virales[:150], "busqueda")
    ref = sum(1 for a in lista if a["es_referente"])
    autos = sum(1 for a in lista if a.get("auto_tipo") == "automatizado")
    _log(f"Listo: {len(lista)} canales analizados, {ref} referentes, {autos} automatizados, {len(virales)} videos virales.", 100)
    return {"tipo": "busqueda", "id": reg["id"]}


def buscar(p: dict):
    titulo = p.get("titulo") or "Buscar nichos"
    _lanzar(titulo, _buscar, p)


DESCUBRIR = DATOS / "descubrir.json"


def descubrir(p: dict | None = None):
    """Buscador aleatorio de canales automatizados (sin rostro) basado en nichos típicos de Aprende a Monetizar."""
    from .academia import semillas_aleatorias
    p = p or {}
    hist = read_json(DESCUBRIR, {"usadas": []})
    frases = semillas_aleatorias(int(p.get("temas") or 3), p.get("categoria") or "", set(hist["usadas"][-40:]))
    hist["usadas"] = (hist["usadas"] + frases)[-80:]
    write_json(DESCUBRIR, hist)
    import random
    dias = int(p.get("dias") or random.choice([90, 180, 365, 365]))
    lang = p.get("idioma") or "en"
    buscar({"frases": [{"idioma": lang, "texto": f} for f in frases], "dias": dias, "region": "US" if lang == "en" else "",
            "max_canales": int(p.get("max_canales") or 30), "tipo": "descubrir", "orden": "viewCount",
            "titulo": "🎲 Descubrir: " + ", ".join(frases), "filtro_auto": True})
    return frases


def similares(ids: list, base: dict | None = None):
    """Busca más canales parecidos a los seleccionados usando sus etiquetas y palabras de títulos."""
    todos = read_json_cache(CANALES, {})
    sel = [todos[i] for i in ids if i in todos]
    if not sel:
        raise ValueError("Selecciona al menos un canal analizado.")
    frases = frases_semilla(sel, int((base or {}).get("n_frases") or 5))
    if not frases:
        raise ValueError("Esos canales no tienen etiquetas ni títulos suficientes para buscar similares.")
    langs = Counter(a["idioma"] for a in sel).most_common(1)
    lang = langs[0][0] if langs else ""
    p = {**(base or {}), "frases": [{"idioma": lang if lang in ("en", "es") else "", "texto": f} for f in frases],
         "excluir": list(ids), "tipo": "similares", "origen": [a["canal"] for a in sel],
         "titulo": "Similares a " + ", ".join(a["canal"] for a in sel[:3]) + ("…" if len(sel) > 3 else "")}
    buscar(p)
    return frases


def analizar_links(links: list):
    def _run():
        ids = []
        for i, ref in enumerate(links):
            _log(f"Buscando {ref}…", 3 + 20 * i / max(1, len(links)))
            cid = yt.resolver_canal(ref)
            if cid:
                ids.append(cid)
            else:
                _log(f"No encontré {ref}", nivel="WARN")
        lista = _analizar(ids, 25, 95)
        reg = {"id": uuid.uuid4().hex[:10], "tipo": "canales", "titulo": "Canales: " + ", ".join(a["canal"] for a in lista[:3]),
               "frases": [], "parametros": {}, "fecha": datetime.now().isoformat(timespec="seconds"),
               "canales": [a["id"] for a in lista], "virales": [], "origen": links}
        _guardar_busqueda(reg)
        _log(f"Listo: {len(lista)} canales analizados.", 100)
        return {"tipo": "busqueda", "id": reg["id"]}
    _lanzar("Analizar canales", _run)


def top_historico(cid: str) -> dict:
    a = canal_crudo(cid)
    if not a:
        raise ValueError("Canal no analizado.")
    a = dict(a)   # copia: el original vive en la caché compartida
    vids = yt.top_videos_canal(cid, 15)
    a["top_historico"] = sorted(({"titulo": v["snippet"]["title"], "url": f"https://www.youtube.com/watch?v={v['id']}",
                                  "miniatura": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg",
                                  "vistas": int(v.get("statistics", {}).get("viewCount", 0) or 0),
                                  "likes": int(v.get("statistics", {}).get("likeCount", 0) or 0),
                                  "publicado": v["snippet"]["publishedAt"][:10],
                                  "duracion_seg": yt.dur_iso(v.get("contentDetails", {}).get("duration"))} for v in vids),
                                key=lambda x: x["vistas"], reverse=True)
    if a["top_historico"] and a["top_historico"][0]["vistas"] > a["techo"]:
        t = a["top_historico"][0]
        a["techo"], a["techo_titulo"], a["techo_url"] = t["vistas"], t["titulo"], t["url"]
    todos = read_json(CANALES, {})
    todos[cid] = a
    write_json(CANALES, todos)
    return a


# ---------- guardados (embudo) ----------

def guardados() -> dict:
    return read_json(GUARDADOS, {})


def guardar(ids: list, nicho: str = ""):
    try:                                          # empieza a medir sus visitas reales desde ya (1 unidad)
        from . import seguimiento as seg
        nuevos = [i for i in ids if i not in guardados()]
        if nuevos:
            threading.Thread(target=lambda: seg.tomar_foto(nuevos), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass
    g = guardados()
    ahora = datetime.now().isoformat(timespec="seconds")
    for cid in ids:
        g.setdefault(cid, {"etapa": "lista", "notas": "", "nicho": nicho, "agregado": ahora})
        if nicho and not g[cid].get("nicho"):
            g[cid]["nicho"] = nicho
    write_json(GUARDADOS, g)


def editar_guardado(cid: str, cambios: dict):
    g = guardados()
    if cid not in g:
        raise ValueError("No está en guardados.")
    for k in ("etapa", "notas", "nicho"):
        if k in cambios:
            if k == "etapa" and cambios[k] not in ETAPAS:
                raise ValueError("Etapa inválida.")
            g[cid][k] = cambios[k]
    write_json(GUARDADOS, g)


def quitar_guardados(ids: list):
    g = guardados()
    for cid in ids:
        g.pop(cid, None)
    write_json(GUARDADOS, g)


def lista_guardados() -> list:
    out = []
    for cid, meta in guardados().items():
        a = canal(cid)
        if a:
            out.append({**ligero(a), **meta})  # noqa
    return out


def borrar_todo():
    """Deja NichosForge Pro como recién instalado (no toca ajustes ni claves)."""
    from .clasificador import APRENDIDOS
    for p in (CANALES, MI_CANAL, MIS, BUSQUEDAS, GUARDADOS, INVESTIGACIONES, VIDEOS_G, SUGERENCIAS, DATOS / "descubrir.json", APRENDIDOS,
              DATOS / "seguimiento.json", DATOS / "seguidos.json", DATOS / "rostros.json", DATOS / "monetizacion.json"):
        p.unlink(missing_ok=True)
    yt.limpiar_cache()


# =====================================================================
# INVESTIGACIÓN: muchos videos → canales automatizados → nicho por video
# =====================================================================
import random as _rnd

from . import clasificador as clf

INVESTIGACIONES = DATOS / "investigaciones.json"
VIDEOS_G = DATOS / "videos_guardados.json"
SUGERENCIAS = DATOS / "sugerencias.json"

CATS_INV = ["27", "24", "22", "28", "19", "2", "17", "26", "15", "1"]   # sin música (10) ni videojuegos (20)
TEMAS_INV = ["/m/098wr", "/m/01k8wb", "/m/019_rr", "/m/02jjt", "/m/06ntj", "/m/07c1v", "/m/07bxq", "/m/068hy", "/m/07yv9", "/m/09s1f"]
AMPLIAS = {"en": ["story", "stories", "documentary", "explained", "history", "facts", "mystery", "truth", "secret", "why",
                  "what happened", "untold", "the rise and fall", "biggest", "richest", "inside", "how"],
           "es": ["historia", "historias", "documental", "explicado", "misterio", "verdad", "secreto", "por qué", "lo que pasó",
                  "nadie", "nunca", "el más", "así fue"]}
MERCADOS = {"en": ["US", "GB", "CA", "AU"], "es": ["MX", "ES", "CO", "AR", "US"]}
PROFUNDIDAD = {"rapida": {"busquedas": 2, "tendencias": 4, "canales": 50},
               "normal": {"busquedas": 4, "tendencias": 8, "canales": 100},
               "profunda": {"busquedas": 8, "tendencias": 12, "canales": 180}}


def costo_investigacion(prof: str) -> int:
    c = PROFUNDIDAD.get(prof, PROFUNDIDAD["normal"])
    return c["busquedas"] * 100 + c["tendencias"] + int(c["canales"] * 1.4) + 10


def _sondas(p: dict) -> tuple:
    """Arma búsquedas variadas sin depender de nichos: categorías, temas amplios, fechas y países al azar."""
    lang0 = p.get("idioma") or "en"
    conf = PROFUNDIDAD.get(p.get("profundidad") or "normal", PROFUNDIDAD["normal"])
    q_usuario = (p.get("q") or "").strip()
    busq = []
    for i in range(conf["busquedas"]):
        lang = ("en" if i % 2 == 0 else "es") if lang0 == "ambos" else lang0
        s = {"frase": q_usuario or _rnd.choice(AMPLIAS.get(lang, AMPLIAS["en"])), "idioma": lang,
             "dias": int(p.get("dias") or _rnd.choice([30, 60, 90, 180, 365])),
             "region": _rnd.choice(MERCADOS.get(lang, ["US"])), "duracion": _rnd.choice(["medium", "long"])}
        if i % 2 == 0:
            s["categoria"] = _rnd.choice(CATS_INV)
        else:
            s["tema"] = _rnd.choice(TEMAS_INV)
        busq.append(s)
    mercados = MERCADOS["en"] + MERCADOS["es"] if lang0 == "ambos" else MERCADOS.get(lang0, ["US"])
    if p.get("region"):
        mercados = [p["region"]]
        for b_ in busq:
            b_["region"] = p["region"]
    tend = [(_rnd.choice(mercados), c) for c in _rnd.sample(CATS_INV, min(len(CATS_INV), conf["tendencias"]))]
    if conf["tendencias"] > len(CATS_INV):
        tend += [(_rnd.choice(mercados), _rnd.choice(CATS_INV)) for _ in range(conf["tendencias"] - len(CATS_INV))]
    return busq, tend, conf


def _vid_basico(v: dict) -> dict | None:
    sn, st = v.get("snippet", {}), v.get("statistics", {})
    if not sn.get("publishedAt") or sn.get("liveBroadcastContent") not in (None, "none"):
        return None
    dur = yt.dur_iso(v.get("contentDetails", {}).get("duration"))
    pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
    horas = max(1.0, (datetime.now(pub.tzinfo) - pub).total_seconds() / 3600)
    visitas = int(st.get("viewCount", 0) or 0)
    return {"id": v["id"], "titulo": sn.get("title", ""), "canal": sn.get("channelTitle", ""), "canal_id": sn.get("channelId"),
            "url": f"https://www.youtube.com/watch?v={v['id']}", "miniatura": f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg",
            "vistas": visitas, "likes": int(st.get("likeCount", 0) or 0), "comentarios": int(st.get("commentCount", 0) or 0),
            "publicado": sn["publishedAt"][:10], "dias": max(1, int(horas // 24)), "vph": round(visitas / horas, 1),
            "duracion_seg": dur, "categoria_id": sn.get("categoryId", ""), "tags": (sn.get("tags") or [])[:25],
            "desc": (sn.get("description") or "")[:500],
            "idioma": (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "")[:2]}


def _subidas_en_lote(chs: dict, n: int = 15, pct0: float = 50, pct1: float = 80) -> dict:
    """Últimos videos de muchos canales a la vez (en paralelo): 1 unidad por canal + videos en lotes de 50."""
    hechos = {"n": 0}
    total = len(chs)

    def una(item):
        cid, ch = item
        pl = (ch.get("contentDetails", {}).get("relatedPlaylists") or {}).get("uploads")
        if not pl:
            return cid, []
        try:
            d = yt.api("playlistItems", part="contentDetails", playlistId=pl, maxResults=n)
        except RuntimeError as e:
            if "cuota" in str(e).lower() or "clave" in str(e).lower():
                raise
            return cid, []
        hechos["n"] += 1
        if hechos["n"] % 20 == 0:
            _log(f"Leyendo subidas de los canales ({hechos['n']}/{total})…", pct0 + (pct1 - pct0) * 0.6 * hechos["n"] / total)
        return cid, [it["contentDetails"]["videoId"] for it in d.get("items", [])]

    ids_por_canal = dict(yt.en_paralelo(una, list(chs.items()), 10))
    todos = [v for lista in ids_por_canal.values() for v in lista]
    _log(f"Leyendo estadísticas de {len(todos)} videos…", pct0 + (pct1 - pct0) * 0.7)
    por_id = {v["id"]: v for v in yt.videos(todos)}
    return {cid: [por_id[v] for v in lista if v in por_id] for cid, lista in ids_por_canal.items()}


def _investigar(p: dict):
    aj = ajustes()
    busq, tend, conf = _sondas(p)
    lang = p.get("idioma") or "en"
    vistas_min = int(p.get("vistas_min") or aj.get("inv_vistas_min") or 10000)
    if lang == "ambos":
        lang = "en"  # solo para el título
    candidatos = {}
    from .config import CATEGORIAS
    _log(f"Explorando {len(tend)} listas de tendencias y {len(busq)} búsquedas a la vez…", 4)
    for lista in yt.en_paralelo(lambda rc: yt.populares(rc[0], rc[1]), tend, 6):
        for v in lista:
            b = _vid_basico(v)
            if b:
                candidatos[b["id"]] = b
    _log(f"Tendencias leídas: {len(candidatos)} videos. Buscando más…", 12)

    def una_busqueda(s):
        try:
            return yt.buscar_videos(s["frase"], s["idioma"], s["dias"], 50, s["region"], s["duracion"], "viewCount", 1,
                                    s.get("categoria", ""), s.get("tema", ""))
        except RuntimeError as e:
            if "cuota" in str(e).lower() or "clave" in str(e).lower():
                raise
            _log(f"Una búsqueda falló ({e}); sigo con las demás.", nivel="WARN")
            return []
    sin_stats = []
    for items in yt.en_paralelo(una_busqueda, busq, 4):
        for it in items:
            vid = (it.get("id") or {}).get("videoId")
            if vid and vid not in candidatos:
                sin_stats.append(vid)
    for s_ in busq:
        _log(f"Exploré «{s_['frase']}» ({s_['region']}, {CATEGORIAS.get(s_.get('categoria', ''), 'tema amplio')}, últimos {s_['dias']} días)")
    if sin_stats:
        _log(f"Leyendo estadísticas de {len(sin_stats)} videos encontrados…", 22)
        for v in yt.videos(sin_stats):
            b = _vid_basico(v)
            if b:
                candidatos[b["id"]] = b
    # filtros base: sin Shorts, sin música, con un mínimo de visitas
    cand = [v for v in candidatos.values() if v["duracion_seg"] > 180 and v["categoria_id"] != "10" and v["vistas"] >= vistas_min]
    if not cand:
        raise RuntimeError("No encontré videos largos con suficientes visitas en esta tirada. Prueba otra vez o baja las visitas mínimas.")
    _log(f"{len(cand)} videos largos candidatos de {len({v['canal_id'] for v in cand})} canales.", 30)
    # canales a analizar: los de mejores videos primero
    mejor = {}
    for v in sorted(cand, key=lambda x: -x["vph"]):
        mejor.setdefault(v["canal_id"], v)
    mios = ids_mis_canales()
    ids = [c for c in mejor if c not in mios][:conf["canales"]]
    previos = read_json_cache(CANALES, {})
    frescos = {c: previos[c] for c in ids if c in previos and previos[c].get("analizado") and
               (datetime.now() - datetime.fromisoformat(previos[c]["analizado"])).total_seconds() < float(aj["cache_horas"]) * 3600}
    pend = [c for c in ids if c not in frescos]
    _log(f"Analizando {len(pend)} canales ({len(frescos)} ya estaban al día)…", 35)
    chs = yt.canales(pend) if pend else {}
    _foto_gratis(chs)
    subidas = _subidas_en_lote(chs, 15, 40, 75) if chs else {}
    analizados = dict(frescos)
    nuevos = []
    for k, (cid, ch) in enumerate(chs.items(), 1):
        if k % 15 == 0:
            _log(f"Detectando canales automatizados ({k}/{len(chs)})…", 75 + 10 * k / len(chs))
        a = analizar_canal(ch, subidas.get(cid, []), aj)
        analizados[cid] = a
        nuevos.append(a)
    _guardar_canales(nuevos)
    solo_auto = p.get("solo_automatizados", aj.get("inv_solo_automatizados", True))
    permitidos = {"automatizado", "posible"} if solo_auto else {"automatizado", "posible", "marca"}
    malos = {"Música / recopilaciones", "Temas de adultos", "Violencia gráfica"}
    ok = {cid: a for cid, a in analizados.items() if a.get("auto_tipo") in permitidos and not (set(a.get("riesgos", [])) & malos)}
    # videos: los candidatos de esos canales + el mayor outlier reciente de cada canal
    _log("Asignando un nicho a cada video…", 87)
    pats = clf._patrones()
    vids = {}
    for v in cand:
        if v["canal_id"] in ok:
            vids[v["id"]] = v
    for cid, a in ok.items():
        for v in sorted(a.get("videos_lista", []), key=lambda x: -(x.get("outlier") or 0))[:2]:
            if (v.get("outlier") or 0) >= 2 and v["duracion_seg"] > 180 and v["id"] not in vids:
                horas = max(1, v["dias"] * 24)
                vids[v["id"]] = {"id": v["id"], "titulo": v["titulo"], "canal": a["canal"], "canal_id": cid, "url": v["url"],
                                 "miniatura": f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg", "vistas": v["vistas"], "likes": v["likes"],
                                 "comentarios": v["comentarios"], "publicado": v["publicado"], "dias": v["dias"], "vph": round(v["vistas"] / horas, 1),
                                 "duracion_seg": v["duracion_seg"], "categoria_id": v["categoria"], "tags": v["tags"][:15], "idioma": a["idioma"]}
    lista = []

    def nicho_del_canal(cid):
        ap = clf.aprendidos()["canales"].get(cid)
        if ap:
            return ap["nicho"], 1.0
        a_ = ok[cid]
        return (a_.get("nicho") or clf.SIN), (a_.get("nicho_conf") or 0)
    for v in vids.values():
        a = ok[v["canal_id"]]
        nc, cc = nicho_del_canal(v["canal_id"])
        n, fuente = clf.clasificar_video(v, nc, cc, pats)
        v.update({"nicho": n, "nicho_fuente": fuente, "outlier": round(v["vistas"] / a["mediana"], 1) if a.get("mediana") else None,
                  "avatar": a["avatar"], "suscriptores": a["suscriptores"], "auto_tipo": a["auto_tipo"], "auto_score": a["auto_score"],
                  "salud": a["salud"], "idioma": v.get("idioma") or a["idioma"], "canal_visitas_mes": a["visitas_mes"]})
        lista.append(v)
    rid = uuid.uuid4().hex[:10]
    from .analisis import palabras_clave

    def armar_registro():
        canales_out = []
        for cid in ok:
            nichos_c = [v["nicho"] for v in lista if v["canal_id"] == cid]
            if nichos_c:
                nc, _ = nicho_del_canal(cid)
                canales_out.append({"id": cid, "nicho": nc if nc != clf.SIN else Counter(nichos_c).most_common(1)[0][0], "videos_encontrados": len(nichos_c)})
        lista.sort(key=lambda v: -((v["outlier"] or 0) * 0.6 + min(50, v["vph"] / 100) * 0.4))
        return {"id": rid, "fecha": datetime.now().isoformat(timespec="seconds"),
                "titulo": ("🔎 " + p["q"]) if p.get("q") else ("🎲 Investigación al azar · " + {"en": "inglés", "es": "español", "ambos": "inglés y español"}.get(p.get("idioma") or "en", "inglés")),
                "parametros": {k: v for k, v in p.items() if not str(k).startswith("_")}, "videos": lista[:400], "canales": canales_out,
                "nichos": Counter(v["nicho"] for v in lista).most_common(),
                "palabras": palabras_clave([v["titulo"] for v in lista], [v["vistas"] for v in lista], 30),
                "analizados": len(analizados), "candidatos": len(cand)}

    def guardar_reg(reg):
        with _lock:
            todas = [r for r in read_json(INVESTIGACIONES, []) if r["id"] != reg["id"]]
            write_json(INVESTIGACIONES, [reg] + todas[:14])

    reg = armar_registro()
    guardar_reg(reg)
    _trabajo["parcial"] = {"tipo": "investigacion", "id": rid}       # el panel ya puede mostrar resultados
    clf.entrenar_con_canales(list(ok.values()))            # el modelo aprende de los canales seguros
    dudosos = [{"id": cid, "canal": a["canal"], "desc": a.get("descripcion", ""), "titulos": [x["titulo"] for x in a.get("videos_lista", [])[:10]]}
               for cid, a in ok.items() if cid not in clf.aprendidos()["canales"] and ((a.get("nicho_conf") or 0) < 0.55 or not a.get("nicho"))]
    if clf.llm.disponible() and dudosos:
        _log(f"Resultados listos. La IA está revisando los {min(len(dudosos), 72)} canales de nicho dudoso…", 92)
        hechos = clf.clasificar_canales_con_ia(dudosos)
        for v in lista:                                     # sus videos heredan el nicho que decidió la IA
            if v.get("nicho_fuente") in ("canal", "reglas", "modelo", ""):
                nc, cc = nicho_del_canal(v["canal_id"])
                if nc != clf.SIN:
                    v["nicho"], v["nicho_fuente"] = clf.clasificar_video(v, nc, cc, pats)
        sobran = [v for v in lista if v["nicho"] == clf.SIN]
        if sobran:
            hechos += clf.aprender_con_ia(sobran, 60)
        _log(f"La IA clasificó {hechos} canales/videos dudosos." if hechos else "La IA no pudo revisar los dudosos esta vez.", 97)
        reg = armar_registro()
        guardar_reg(reg)
    _en_fondo("Verificando rostros y miniaturas de la investigación", list(ok), lista, "investigacion")
    SUGERENCIAS.unlink(missing_ok=True)
    conteo = Counter(v["nicho"] for v in lista)
    _log(f"Listo: {len(lista)} videos de {len(reg['canales'])} canales automatizados en {len(conteo)} nichos "
         f"(de {len(analizados)} canales revisados).", 100)
    return {"tipo": "investigacion", "id": rid}


def investigar(p: dict):
    _lanzar("Investigación" + (f": {p['q']}" if p.get("q") else " al azar"), _investigar, p)


def investigaciones() -> list:
    return [{k: r[k] for k in ("id", "fecha", "titulo", "nichos")} | {"videos": len(r["videos"]), "canales": len(r["canales"])}
            for r in read_json_cache(INVESTIGACIONES, [])]


def investigacion(rid: str | None = None) -> dict | None:
    todas = read_json_cache(INVESTIGACIONES, [])
    if not todas:
        return None
    r = next((x for x in todas if x["id"] == rid), todas[0]) if rid else todas[0]
    r = {**r, "videos": [dict(v) for v in r["videos"]], "canales": list(r["canales"])}   # copia: no tocar la caché
    ap = clf.aprendidos()
    vg = videos_guardados()
    for v in r["videos"]:                       # aplica lo que tú (o la IA) corregiste después: por video o por canal
        if v["id"] in ap["videos"]:
            v["nicho"], v["nicho_fuente"] = ap["videos"][v["id"]]["nicho"], ap["videos"][v["id"]].get("fuente", "usuario")
        elif v.get("canal_id") in ap["canales"] and v.get("nicho_fuente") in ("canal", "modelo", "", None):
            v["nicho"], v["nicho_fuente"] = ap["canales"][v["canal_id"]]["nicho"], "canal"
        v["guardado"] = v["id"] in vg
    g = guardados()
    cs = []
    for c in r["canales"]:
        a = ligero_de(c["id"])
        if a:
            n = ap["canales"].get(c["id"], {}).get("nicho") or c["nicho"]
            cs.append({**a, "nicho": n, "videos_encontrados": c["videos_encontrados"], "guardado": c["id"] in g})
    solo_auto = (r.get("parametros") or {}).get("solo_automatizados", True)
    por_id = {c["id"]: c for c in cs}
    vids = []
    for v in r["videos"]:
        c = por_id.get(v["canal_id"])
        if c:
            v["auto_tipo"], v["auto_score"], v["salud"] = c.get("auto_tipo"), c.get("auto_score"), c.get("salud")
            v["rostro"] = (c.get("rostro") or {}).get("veredicto")
        if solo_auto and v.get("rostro") == "con_rostro":
            continue                                 # verificado: hay un creador a cámara
        vids.append(v)
    r["videos"] = vids
    r["canales"] = [c for c in cs if not (solo_auto and (c.get("rostro") or {}).get("veredicto") == "con_rostro")]
    r["ocultos_con_rostro"] = len(cs) - len(r["canales"])
    r["nichos"] = Counter(v["nicho"] for v in r["videos"]).most_common()
    return r


def borrar_investigacion(rid: str):
    with _lock:
        write_json(INVESTIGACIONES, [r for r in read_json(INVESTIGACIONES, []) if r["id"] != rid])


# ---------- videos guardados y categorías ----------

def videos_guardados() -> dict:
    return read_json(VIDEOS_G, {})


def guardar_video(v: dict, categoria: str = ""):
    if not v.get("id"):
        raise ValueError("Video inválido.")
    with _lock:
        g = videos_guardados()
        previo = g.get(v["id"], {})
        campos = ("id", "titulo", "canal", "canal_id", "url", "miniatura", "vistas", "likes", "comentarios", "publicado", "vph",
                  "duracion_seg", "outlier", "nicho", "avatar", "auto_tipo", "salud", "tags")
        g[v["id"]] = {**{k: v.get(k) for k in campos}, "categoria": categoria or previo.get("categoria") or v.get("nicho") or "",
                      "notas": previo.get("notas", ""), "guardado": previo.get("guardado") or datetime.now().isoformat(timespec="seconds")}
        write_json(VIDEOS_G, g)


def editar_video(vid: str, cambios: dict):
    with _lock:
        g = videos_guardados()
        if vid not in g:
            raise ValueError("Ese video no está guardado.")
        for k in ("categoria", "notas"):
            if k in cambios:
                g[vid][k] = cambios[k]
        write_json(VIDEOS_G, g)
    if cambios.get("categoria"):
        clf.asignar("video", vid, cambios["categoria"], "usuario", clf.palabras_de([g[vid].get("titulo", "")]))


def quitar_video(vid: str):
    with _lock:
        g = videos_guardados()
        g.pop(vid, None)
        write_json(VIDEOS_G, g)


def nicho_manual(tipo: str, ident: str, nicho: str, titulos: list | None = None, canal_id: str = "", todo_canal: bool = False,
                 palabras: list | None = None):
    """Tú corriges el nicho de un video o canal: se guarda y NichosForge lo aprende (y opcionalmente todo su canal)."""
    if tipo == "video" and todo_canal and canal_id:
        a = canal_crudo(canal_id) or {}
        clf.asignar("canal", canal_id, nicho, "usuario", palabras, [v["titulo"] for v in a.get("videos_lista", [])[:20]] or titulos)
        # los videos ya corregidos uno por uno de ese canal se respetan; el resto hereda
    clf.asignar(tipo, ident, nicho, "usuario", palabras, titulos or [])
    if tipo == "canal":
        with _lock:
            g = guardados()
            if ident in g:
                g[ident]["nicho"] = nicho
                write_json(GUARDADOS, g)
    else:
        with _lock:
            g = videos_guardados()
            if ident in g:
                g[ident]["categoria"] = nicho
                write_json(VIDEOS_G, g)


def categorias() -> list:
    usadas = {x.get("categoria") for x in videos_guardados().values()} | {x.get("nicho") for x in guardados().values()}
    return sorted({c for c in usadas if c} | set(clf.nombres()))


# ---------- sugerencias de Nichi (IA o reglas) ----------

def _resumen_para_ia() -> dict:
    mc = mi_canal()
    inv = investigacion()
    corto = lambda a: {k: a.get(k) for k in ("canal", "rol", "auto_tipo", "audiencia", "salud", "suscriptores", "visitas_mes",
                                            "edad_dias", "ingreso_mes", "rpm", "categoria", "score")}
    return {
        "mis_canales": [corto(c) for c in mis_canales()],
        "canal_activo": corto(mc["analisis"]) if mc else None,
        "investigacion": {"nichos": (inv or {}).get("nichos", [])[:12],
                          "videos_top": [{k: v.get(k) for k in ("titulo", "canal", "vistas", "outlier", "vph", "nicho")} for v in (inv or {}).get("videos", [])[:12]],
                          "canales_top": [corto(c) | {"nicho": c.get("nicho")} for c in (inv or {}).get("canales", [])[:10]]} if inv else None,
        "busquedas": [b["titulo"] for b in busquedas()[:6]],
        "guardados": len(guardados()), "videos_guardados": len(videos_guardados()),
        "cuota_hoy": yt.cuota_hoy(), "claves_youtube": len(yt.estado_claves()),
    }


def _reglas_sugerencias(ctx: dict) -> list:
    out = []
    if not ctx["mis_canales"]:
        out.append({"icono": "📺", "titulo": "Conecta tu canal", "detalle": "Así comparo tus números con los referentes y te sugiero nichos parecidos.",
                    "accion": {"tipo": "ir", "valor": "micanal"}})
    inv = ctx.get("investigacion")
    if not inv:
        out.append({"icono": "🔎", "titulo": "Haz tu primera investigación", "detalle": "Reviso cientos de videos, detecto los canales sin rostro y les pongo nicho.",
                    "accion": {"tipo": "ir", "valor": "investigacion"}})
    else:
        if inv["nichos"]:
            n, c = inv["nichos"][0]
            if n != "Sin clasificar":
                out.append({"icono": "🔥", "titulo": f"«{n}» está caliente", "detalle": f"{c} videos virales de canales automatizados en tu última investigación. Búscalo a fondo.",
                            "accion": {"tipo": "buscar", "valor": n}})
        jov = [c for c in inv["canales_top"] if (c.get("edad_dias") or 9999) <= 365 and c.get("auto_tipo") == "automatizado"]
        if jov:
            c = jov[0]
            out.append({"icono": "🚀", "titulo": f"{c['canal']} es un canal joven que ya vuela", "detalle": f"{c['edad_dias']} días y ~{c['visitas_mes']:,} visitas/mes. Candidato a referente: guárdalo.".replace(",", "."),
                        "accion": {"tipo": "investigacion", "valor": "canales"}})
    if ctx["claves_youtube"] <= 1:
        out.append({"icono": "🔑", "titulo": "Agrega otra clave de YouTube", "detalle": "Si una se queda sin cuota, sigo con la otra sin detenerme.",
                    "accion": {"tipo": "ir", "valor": "ajustes"}})
    if ctx["guardados"] >= 5:
        out.append({"icono": "🗂", "titulo": "Filtra tu embudo", "detalle": f"Tienes {ctx['guardados']} canales guardados: pásalos por los filtros 1-3 hasta quedarte con 5 referentes.",
                    "accion": {"tipo": "ir", "valor": "guardados"}})
    out.append({"icono": "📘", "titulo": "Secreto #1: tickets de lotería", "detalle": "Más videos = más probabilidades de viralizar. La meta es 1 video diario con un banco de 15 adelantados.",
                "accion": {"tipo": "ir", "valor": "academia"}})
    return out[:4]


def sugerencias(forzar: bool = False) -> dict:
    guardado = read_json(SUGERENCIAS, None)
    if guardado and not forzar:
        edad = (datetime.now() - datetime.fromisoformat(guardado["fecha"])).total_seconds()
        if edad < 600:
            return guardado
    ctx = _resumen_para_ia()
    items, fuente = [], "reglas"
    if llm.disponible():
        from .academia import conocimiento_texto
        try:
            r = llm.ask_json(
                "Eres Nichi, asistente de NichosForge Pro (nichos y canales automatizados sin rostro de YouTube, metodología de la "
                "Aprende a Monetizar). Analiza estos datos y da 4 sugerencias MUY concretas y accionables para hoy.\n"
                "Tipos de acción posibles: {\"tipo\":\"buscar\",\"valor\":\"frase en inglés\"} (buscar ese nicho), "
                "{\"tipo\":\"investigacion\",\"valor\":\"videos|canales\"}, {\"tipo\":\"ir\",\"valor\":\"micanal|explorar|guardados|academia|ajustes\"}.\n"
                'Formato: {"sugerencias": [{"icono": "emoji", "titulo": "máx 8 palabras", "detalle": "1-2 frases con números", "accion": {...}}]}\n\n'
                "METODOLOGÍA (resumen):\n" + conocimiento_texto()[:6000] + "\n\nDATOS:\n" + json.dumps(ctx, ensure_ascii=False, default=str)[:7000])
            lista_ia = r if isinstance(r, list) else (r.get("sugerencias") or next((v for v in r.values() if isinstance(v, list)), []))
            items = [x for x in lista_ia if isinstance(x, dict) and x.get("titulo")][:4]
            fuente = llm.nombre(llm.ultimo.get("proveedor"))
        except Exception as e:  # noqa: BLE001
            log_global(f"Sugerencias IA no disponibles: {e}", "WARN")
    if not items:
        items = _reglas_sugerencias(ctx)
    out = {"fecha": datetime.now().isoformat(timespec="seconds"), "fuente": fuente, "sugerencias": items}
    write_json(SUGERENCIAS, out)
    return out


# =====================================================================
# MINIATURAS: radar de tendencias y búsqueda de canales por miniatura
# =====================================================================
RADAR_MERCADOS = {"en": ["US", "GB", "CA", "AU"], "es": ["MX", "ES", "CO", "AR", "CL", "PE"]}


def _radar_miniaturas(p: dict | None = None):
    """Lee lo que está en tendencia AHORA (1 unidad por lista) y cataloga sus miniaturas."""
    from . import clasificador as clf_
    from . import miniaturas
    if not miniaturas.disponible():
        raise RuntimeError("Falta OpenCV: ejecuta instalar_actualizar.bat.")
    mercado = (p or {}).get("mercado") or ajustes().get("radar_mercado") or "ambos"
    regiones = RADAR_MERCADOS["en"] + RADAR_MERCADOS["es"] if mercado == "ambos" else RADAR_MERCADOS.get(mercado, ["US"])
    combos = [(r, c) for r in regiones for c in CATS_INV]
    _log(f"Leyendo {len(combos)} listas de tendencias de {len(regiones)} países…", 5)
    vids = {}
    for lista in yt.en_paralelo(lambda rc: yt.populares(rc[0], rc[1]), combos, 8):
        for v in lista:
            b = _vid_basico(v)
            if b and b["duracion_seg"] > 180 and b["categoria_id"] != "10":
                vids[b["id"]] = b
    lista = list(vids.values())
    pats = clf_._patrones()
    for v in lista:
        v["nicho"], _ = clf_.nicho_video(v, pats)
    _log(f"{len(lista)} videos largos en tendencia. Analizando sus miniaturas…", 30)
    n = miniaturas.agregar(lista, "tendencias", 800, lambda h, t: _log(f"Miniaturas analizadas ({h}/{t})…", 30 + 65 * h / t))
    _log(f"Listo: {n} miniaturas nuevas en el radar ({len(lista)} videos en tendencia).", 100)
    return {"tipo": "miniaturas"}


def radar_miniaturas(p: dict | None = None):
    _lanzar("Radar de miniaturas", _radar_miniaturas, p)


def _buscar_por_miniatura(p: dict):
    from . import miniaturas
    vec, etiqueta = p["vec"], p.get("etiqueta") or "esta miniatura"
    sim = miniaturas.parecidas(vec, excluir=p.get("excluir", ""), n=80, umbral=.84)
    semillas = [c["id"] for c in sim["canales"][:8] if c.get("id")]
    if not semillas:
        raise RuntimeError("Aún no tengo miniaturas parecidas guardadas. Actualiza el radar o haz una investigación y vuelve a intentarlo.")
    _log(f"{len(semillas)} canales usan miniaturas parecidas. Leyendo de qué tratan…", 5)
    analizados = _analizar(semillas, 5, 25)
    frases = frases_semilla(analizados, 5)
    langs = Counter(a["idioma"] for a in analizados).most_common(1)
    lang = langs[0][0] if langs and langs[0][0] in ("en", "es") else "en"
    if not frases:
        frases = [w for w, _ in Counter(w for a in analizados for w, _ in a.get("palabras", [])[:3]).most_common(4)]
    res = _buscar({"frases": [{"idioma": lang, "texto": f} for f in frases], "max_canales": 30, "tipo": "miniatura",
                   "canales": semillas, "titulo": f"🎨 Miniaturas parecidas a «{etiqueta}»", "origen": [etiqueta]})
    b = busqueda(res["id"])
    # que cada canal tenga miniaturas catalogadas y calcula qué tanto se parecen
    faltan = []
    cat = miniaturas.corpus()
    for cid in b["canales"]:
        if not any(v.get("canal_id") == cid for v in cat.values()):
            a = canal_crudo(cid) or {}
            faltan += [{**v, "canal": a.get("canal"), "canal_id": cid} for v in sorted(a.get("videos_lista", []), key=lambda x: -x["vistas"])[:3]]
    if faltan:
        _log("Comparando las miniaturas de los canales encontrados…", 96)
        miniaturas.agregar(faltan, "busqueda", 200)
    cat = miniaturas.corpus()
    parecido = {}
    for cid in b["canales"]:
        sims = [miniaturas.similitud(vec, v["v"]) for v in cat.values() if v.get("canal_id") == cid and v.get("v")]
        if sims:
            parecido[cid] = round(100 * max(sims))
    b["sim_miniatura"] = parecido
    b["canales"] = sorted(b["canales"], key=lambda c: -parecido.get(c, 0))
    _guardar_busqueda(b)
    _log(f"Listo: {sum(1 for x in parecido.values() if x >= 85)} canales con miniaturas muy parecidas.", 100)
    return {"tipo": "busqueda", "id": b["id"]}


def buscar_por_miniatura(p: dict):
    _lanzar("Buscar canales por miniatura", _buscar_por_miniatura, p)


# =====================================================================
# 🎯 MAPA DE MI CANAL: referentes en inglés + competencia directa e indirecta
# =====================================================================
MAPAS = DATOS / "mapas.json"
GRUPOS_NICHO = [  # nichos vecinos: comparten audiencia o formato (competencia indirecta)
    {"Historias de venganza y drama familiar", "Historias para adultos mayores", "Historias de Reddit narradas", "Terror y paranormal"},
    {"Misterios sin resolver", "Crimen real", "Estafas y fraudes", "Terror y paranormal", "Desastres y accidentes"},
    {"Historia antigua y medieval", "Guerras e historia moderna", "Militar y aviación", "Mitología y religión", "Lugares abandonados y arquitectura"},
    {"Old money y lujo", "Negocios y marcas", "Celebridades y Hollywood", "Estafas y fraudes"},
    {"Ciencia y espacio", "Ingeniería y megaproyectos", "Tecnología e IA", "Geografía y países", "Curiosidades y datos"},
    {"Animales y naturaleza", "Supervivencia y aventura", "Desastres y accidentes", "Geografía y países"},
    {"Psicología y estoicismo", "Salud y cuerpo humano", "Mitología y religión"},
    {"Autos, camiones y máquinas", "Ingeniería y megaproyectos", "Militar y aviación", "Deportes y leyendas"},
]


def vecinos(nicho: str) -> set:
    out = set()
    for g in GRUPOS_NICHO:
        if nicho in g:
            out |= g
    out.discard(nicho)
    return out


def _vocab(a: dict, n: int = 45) -> Counter:
    c = Counter()
    for v in a.get("videos_lista", [])[:40]:
        for w in set(clf._tokens(v.get("titulo", ""))):
            if "_" not in w and len(w) > 3:
                c[w] += 1
    return Counter(dict(c.most_common(n)))


def _parecido(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


SEMILLAS = {   # frases de búsqueda probadas por nicho: (inglés para referentes, español para competencia)
    "Old money y lujo": (["old money families", "billionaire dynasty", "richest families history"], ["familias millonarias", "herederos de fortunas"]),
    "Historias de venganza y drama familiar": (["revenge stories", "entitled family stories", "karma stories"], ["historias de venganza", "historias de karma"]),
    "Historias para adultos mayores": (["elderly stories heartwarming", "grandma story", "old man story"], ["historias de abuelos", "historias de ancianos"]),
    "Historias de Reddit narradas": (["reddit stories", "pro revenge reddit", "aita stories"], ["historias de reddit", "reddit en español"]),
    "Terror y paranormal": (["scary stories", "true horror stories", "paranormal encounters"], ["historias de terror", "relatos de terror reales"]),
    "Misterios sin resolver": (["unsolved mysteries", "mysterious disappearances", "unexplained mysteries"], ["misterios sin resolver", "desapariciones misteriosas"]),
    "Crimen real": (["true crime documentary", "serial killer documentary", "cold case solved"], ["crimen real", "casos de crimen real"]),
    "Estafas y fraudes": (["biggest scams in history", "con artist documentary", "fraud documentary"], ["estafas más grandes", "estafadores famosos"]),
    "Historia antigua y medieval": (["ancient history documentary", "medieval life", "roman empire history"], ["historia antigua", "imperio romano historia"]),
    "Guerras e historia moderna": (["ww2 documentary", "world war history", "cold war history"], ["segunda guerra mundial", "historia de la guerra"]),
    "Militar y aviación": (["military aircraft", "fighter jets explained", "navy submarine"], ["aviones militares", "armamento militar"]),
    "Negocios y marcas": (["rise and fall of companies", "brand history", "why companies went bankrupt"], ["historia de marcas", "empresas que quebraron"]),
    "Celebridades y Hollywood": (["what happened to celebrities", "hollywood stars downfall", "child stars then and now"], ["famosos que lo perdieron todo", "qué pasó con los famosos"]),
    "Deportes y leyendas": (["football legends", "athletes who went broke", "sports stories"], ["leyendas del fútbol", "historias del deporte"]),
    "Autos, camiones y máquinas": (["biggest trucks", "engine explained", "heavy machinery"], ["camiones gigantes", "maquinaria pesada"]),
    "Ciencia y espacio": (["space documentary", "black hole explained", "universe facts"], ["documental del universo", "misterios del espacio"]),
    "Animales y naturaleza": (["dangerous animals", "animal facts documentary", "deep sea creatures"], ["animales peligrosos", "datos de animales"]),
    "Supervivencia y aventura": (["survival stories", "lost at sea survived", "incredible survival"], ["historias de supervivencia", "sobrevivió"]),
    "Mitología y religión": (["greek mythology explained", "norse mythology", "bible stories"], ["mitología griega", "historias de la biblia"]),
    "Ingeniería y megaproyectos": (["megaprojects", "engineering marvels", "biggest construction projects"], ["megaproyectos", "obras de ingeniería"]),
    "Geografía y países": (["geography explained", "strange countries", "why countries are"], ["geografía curiosa", "países curiosos"]),
    "Psicología y estoicismo": (["stoicism", "stoic lessons", "dark psychology"], ["estoicismo", "psicología oscura"]),
    "Desastres y accidentes": (["disaster documentary", "plane crash documentary", "minute by minute disaster"], ["desastres históricos", "tragedias de la historia"]),
    "Lugares abandonados y arquitectura": (["abandoned places", "exploring abandoned mansion", "urban exploration"], ["lugares abandonados", "exploración urbana"]),
    "Tecnología e IA": (["artificial intelligence explained", "future technology", "ai news"], ["inteligencia artificial", "tecnología del futuro"]),
    "Comida y cocina": (["food history", "most expensive food", "food documentary"], ["historia de la comida", "comida más cara"]),
    "Salud y cuerpo humano": (["human body facts", "what happens to your body", "health facts"], ["cuerpo humano curiosidades", "qué le pasa a tu cuerpo"]),
    "Curiosidades y datos": (["facts you didn't know", "interesting facts", "explained"], ["datos curiosos", "curiosidades que no sabías"]),
}


def _frases_mapa(yo: dict) -> tuple:
    """Frases en español (de sus títulos) y en inglés (con IA o con el vocabulario del nicho)."""
    sem_en, sem_es = SEMILLAS.get(yo.get("nicho"), ([], []))
    es = list(dict.fromkeys(sem_es + frases_semilla([yo], 3)))[:4]
    en = []
    if llm.disponible():
        try:
            r = llm.ask_json(
                f'Mi canal de YouTube "{yo["canal"]}" trata de: {", ".join(es)} (nicho: {yo.get("nicho") or yo.get("categoria")}). '
                "Dame 4 frases de búsqueda en INGLÉS (2-5 palabras, como las escribe la audiencia) para encontrar canales del MISMO nicho en inglés. "
                'Formato: {"en": ["..."]}')
            en = [x for x in (r if isinstance(r, list) else r.get("en", [])) if isinstance(x, str)][:4]
        except Exception as e:  # noqa: BLE001
            log_global(f"Mapa: IA no disponible para traducir ({e})", "WARN")
    en = list(dict.fromkeys(en + sem_en))[:4]
    return es[:4], (en or es)[:4]


def _candidatos(frases: list, idioma: str, excluir: set, limite: int) -> list:
    veces = Counter()
    for f in frases:
        try:
            for it in yt.buscar_videos(f, idioma, 365, 50, "US" if idioma == "en" else "", "", "viewCount", 1):
                cid = it["snippet"]["channelId"]
                if cid not in excluir:
                    veces[cid] += 1
        except RuntimeError as e:
            if "cuota" in str(e).lower() or "clave" in str(e).lower():
                raise
            _log(f"«{f}» falló ({e}); sigo.", nivel="WARN")
    return [c for c, _ in veces.most_common(limite)]


def _mapa_canal(p: dict):
    ref = (p.get("ref") or "").strip()
    if not ref:
        d = _mis()
        ref = next((c.get("ref") or c["id"] for c in d["canales"] if c["id"] == d.get("activo")), "")
    if not ref:
        raise RuntimeError("Escribe tu canal (@handle o link).")
    _log(f"Leyendo tu canal {ref}…", 3)
    cid = yt.resolver_canal(ref)
    if not cid:
        raise RuntimeError(f"No encontré el canal {ref}.")
    _analizar([cid], 3, 10)
    yo = canal(cid)
    yo_crudo = canal_crudo(cid)
    nicho = yo.get("nicho") or clf.SIN
    es, en = _frases_mapa(yo_crudo)
    _log(f"Tu nicho: {nicho}. Buscando referentes en inglés ({', '.join(en)})…", 12)
    ids_en = _candidatos(en, "en", {cid}, 25)
    _log(f"Buscando tu competencia en español ({', '.join(es)})…", 32)
    ids_es = _candidatos(es + ([nicho] if nicho != clf.SIN else []), "es", {cid}, 25)
    _log(f"Analizando {len(ids_en) + len(ids_es)} canales…", 50)
    _analizar(list(dict.fromkeys(ids_en + ids_es)), 50, 90)
    mio = _vocab(yo_crudo)
    vec = vecinos(nicho)
    ref_en, directa, indirecta = [], [], []
    for x in dict.fromkeys(ids_en + ids_es):
        a = canal(x)
        if not a:
            continue
        crudo = canal_crudo(x)
        sim = _parecido(mio, _vocab(crudo))
        mismo = a.get("nicho") == nicho and nicho != clf.SIN
        rostro = (a.get("rostro") or {}).get("veredicto")
        fila = {**ligero(a), "parecido": round(100 * sim), "mismo_nicho": mismo}
        if a.get("idioma") == "en":
            if (mismo or sim >= 0.12) and a.get("auto_tipo") != "marca" and rostro != "con_rostro":
                edad = a.get("edad_dias") or 9999
                fila["puntaje_ref"] = round(min(100, (40 if mismo else 20) + sim * 60 + (20 if edad <= 365 else 8 if edad <= 730 else 0)
                                              + min(20, (a.get("visitas_mes") or 0) / 100_000) + (10 if a.get("es_referente") else 0)))
                fila["por_que"] = ("mismo nicho" if mismo else f"{round(100 * sim)}% de temas en común") + \
                                  (f" · canal joven ({edad} días)" if edad <= 365 else "") + (" · cumple como referente" if a.get("es_referente") else "")
                ref_en.append(fila)
        elif a.get("idioma") == "es":
            if mismo or sim >= 0.2:
                fila["por_que"] = "mismo nicho" + (f" · {round(100 * sim)}% de temas en común" if sim else "")
                directa.append(fila)
            elif a.get("nicho") in vec or sim >= 0.06 or (a.get("audiencia") == yo.get("audiencia") and a.get("categoria") == yo.get("categoria")):
                fila["por_que"] = (f"nicho vecino: {a.get('nicho')}" if a.get("nicho") in vec else
                                   f"{round(100 * sim)}% de temas en común" if sim >= 0.06 else "misma audiencia y categoría")
                indirecta.append(fila)
    ref_en.sort(key=lambda f: -f["puntaje_ref"])
    directa.sort(key=lambda f: (-f["parecido"], -(f.get("visitas_mes") or 0)))
    indirecta.sort(key=lambda f: -(f.get("visitas_mes") or 0))
    # huecos de contenido: temas de los videos que más rinden en los otros y que tú no has tocado
    def temas(filas, solo_outliers=True):
        c = Counter()
        for f in filas[:12]:
            for v in (canal_crudo(f["id"]) or {}).get("videos_lista", []):
                if not solo_outliers or (v.get("outlier") or 0) >= 1.5:
                    for w in set(clf._tokens(v["titulo"])):
                        if "_" not in w and len(w) > 3 and w not in mio:
                            c[w] += 1
        return [w for w, k in c.most_common(14) if k >= 2]
    import statistics as _st
    def prom(filas):
        vs = [f.get("visitas_mes") or 0 for f in filas]
        return round(_st.median(vs)) if vs else 0
    mis_vm = yo.get("visitas_mes") or 0
    posicion = 1 + sum(1 for f in directa if (f.get("visitas_mes") or 0) > mis_vm)
    reg = {"id": uuid.uuid4().hex[:10], "fecha": datetime.now().isoformat(timespec="seconds"),
           "yo": {**ligero(yo), "frases_es": es, "frases_en": en},
           "referentes": ref_en[:15], "directa": directa[:15], "indirecta": indirecta[:15],
           "huecos_en": temas(ref_en), "huecos_es": temas(directa) or temas(indirecta), "huecos_es_de": "directa" if directa else "indirecta",
           "comparativa": {"yo": mis_vm, "referentes": prom(ref_en[:10]), "directa": prom(directa[:10]), "indirecta": prom(indirecta[:10]),
                           "posicion": posicion, "de": len(directa) + 1}}
    with _lock:
        write_json(MAPAS, [reg] + [m for m in read_json(MAPAS, []) if m["yo"]["id"] != cid][:9])
    _en_fondo("Verificando rostros de tu mapa", [f["id"] for f in ref_en[:15] + directa[:15] + indirecta[:15]], [], "mapa")
    _log(f"Listo: {len(ref_en)} referentes en inglés, {len(directa)} competidores directos y {len(indirecta)} indirectos.", 100)
    return {"tipo": "mapa", "id": reg["id"]}


def mapa_canal(p: dict):
    _lanzar("Mapa de mi canal", _mapa_canal, p)


def mapas() -> list:
    return read_json(MAPAS, [])


def mapa(mid: str | None = None) -> dict | None:
    ms = mapas()
    if not ms:
        return None
    m = next((x for x in ms if x["id"] == mid), ms[0]) if mid else ms[0]
    for grupo in ("referentes", "directa", "indirecta"):          # datos frescos (visitas reales, rostro, monetización)
        nuevos = []
        for f in m[grupo]:
            a = canal(f["id"])
            nuevos.append({**f, **(ligero(a) if a else {}), "parecido": f.get("parecido"), "por_que": f.get("por_que"),
                           "puntaje_ref": f.get("puntaje_ref"), "guardado": f["id"] in guardados()})
        m[grupo] = nuevos
    return m


# =====================================================================
# 🚀 OUTLIERS DE CANALES REFERENTES
# =====================================================================
def ids_referentes() -> dict:
    """{canal_id: origen}: guardados, seguidos, los que cumplen como referentes y los de tu último mapa."""
    from . import seguimiento as seg
    out = {}
    for a in read_json_cache(CANALES, {}).values():
        if a.get("es_referente"):
            out[a["id"]] = "referente"
    for m in mapas()[:1]:
        for f in m.get("referentes", []):
            out.setdefault(f["id"], "mapa")
    for cid, org in seg.ids_seguidos().items():
        if org != "mio":
            out[cid] = org
    for cid in ids_mis_canales():
        out.pop(cid, None)
    return out


def outliers_referentes(dias: int = 90, omin: float = 2.0, nicho: str = "", idioma: str = "") -> dict:
    origen = ids_referentes()
    vids = []
    for cid, org in origen.items():
        a = canal(cid)
        crudo = canal_crudo(cid) or {}
        if not a:
            continue
        if (idioma and a.get("idioma") != idioma) or (nicho and a.get("nicho") != nicho):
            continue
        for v in crudo.get("videos_lista", []):
            if v.get("es_short") or (v.get("outlier") or 0) < omin or (v.get("dias") or 9999) > dias:
                continue
            vids.append({**{k: v.get(k) for k in ("id", "titulo", "url", "miniatura", "vistas", "likes", "comentarios", "publicado", "dias", "duracion_seg", "outlier", "tags")},
                         "vph": round((v.get("vistas") or 0) / max(1, (v.get("dias") or 1) * 24), 1),
                         "canal": a["canal"], "canal_id": cid, "avatar": a.get("avatar"), "suscriptores": a.get("suscriptores"),
                         "nicho": a.get("nicho") or "Sin clasificar", "nicho_fuente": "canal", "auto_tipo": a.get("auto_tipo"),
                         "salud": a.get("salud"), "origen": org, "idioma": a.get("idioma"),
                         "canal_actualizado": crudo.get("analizado")})
    vids.sort(key=lambda v: (-(v["outlier"] or 0)))
    nichos = Counter(v["nicho"] for v in vids).most_common()
    return {"videos": vids[:300], "canales": len(origen), "nichos": nichos}


def _actualizar_referentes(p: dict | None = None):
    ids = list(ids_referentes())[:120]
    if not ids:
        raise RuntimeError("Aún no tienes referentes: guarda canales, sigue canales o genera tu mapa.")
    _log(f"Leyendo los videos más recientes de {len(ids)} referentes…", 5)
    # fuerza el reanálisis (lo ya analizado hace menos de 6 h se respeta)
    todos = read_json(CANALES, {})
    viejos = [c for c in ids if c not in todos or (datetime.now() - datetime.fromisoformat(todos[c].get("analizado", "2000-01-01"))).total_seconds() > 6 * 3600]
    with _lock:
        for c in viejos:
            if c in todos:
                todos[c]["analizado"] = "2000-01-01T00:00:00"
        write_json(CANALES, todos)
    _analizar(viejos, 5, 95)
    _log(f"Listo: {len(viejos)} referentes actualizados.", 100)
    return {"tipo": "referentes"}


def actualizar_referentes():
    _lanzar("Actualizar referentes", _actualizar_referentes, {})
