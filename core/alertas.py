"""Alertas automáticas: cada día revisa tus canales y nichos seguidos y te avisa cuando…
  📈 sale un OUTLIER nuevo: un video reciente que va varias veces más rápido que lo normal en su canal;
  🚀 un canal JOVEN EXPLOTA: menos de 1 año y sus visitas reales se disparan (seguimiento) o, en un nicho que
     sigues, aparece un canal nuevo con un video que vuela.
Coste aproximado: 1 unidad por canal seguido + 102 por nicho seguido (máx. 5 nichos).
"""
import statistics
import threading
import uuid
from datetime import datetime, timedelta, timezone

from . import youtube as yt
from .config import DATOS, ajustes
from .utils import log, read_json, write_json

ALERTAS = DATOS / "alertas.json"
ESTADO = DATOS / "alertas_estado.json"
NICHOS_SEGUIDOS = DATOS / "nichos_seguidos.json"
_lock = threading.RLock()
_corriendo = {"si": False, "paso": "", "ultima": None}


# ---------------- nichos seguidos ----------------

def nichos_seguidos() -> list:
    return read_json(NICHOS_SEGUIDOS, [])


def seguir_nicho(nicho: str):
    with _lock:
        n = nichos_seguidos()
        if nicho and nicho not in n:
            n.append(nicho)
            write_json(NICHOS_SEGUIDOS, n[-12:])


def dejar_nicho(nicho: str):
    with _lock:
        write_json(NICHOS_SEGUIDOS, [x for x in nichos_seguidos() if x != nicho])


# ---------------- almacenamiento ----------------

def lista(solo_nuevas: bool = False) -> list:
    a = read_json(ALERTAS, [])
    return [x for x in a if not x.get("leida")] if solo_nuevas else a


def _guardar_nuevas(nuevas: list) -> int:
    if not nuevas:
        return 0
    with _lock:
        a = read_json(ALERTAS, [])
        claves = {x.get("clave") for x in a}
        nuevas = [x for x in nuevas if x["clave"] not in claves]
        limite = (datetime.now() - timedelta(days=30)).isoformat()
        a = (nuevas + [x for x in a if x.get("fecha", "") >= limite])[:300]
        write_json(ALERTAS, a)
    return len(nuevas)


def marcar_leidas(ids: list | None = None):
    with _lock:
        a = read_json(ALERTAS, [])
        for x in a:
            if ids is None or x["id"] in ids:
                x["leida"] = True
        write_json(ALERTAS, a)


def _alerta(tipo, clave, titulo, detalle, **extra) -> dict:
    return {"id": uuid.uuid4().hex[:10], "tipo": tipo, "clave": clave, "titulo": titulo, "detalle": detalle,
            "fecha": datetime.now().isoformat(timespec="seconds"), "leida": False, **extra}


# ---------------- revisiones ----------------

def _vph(v: dict) -> tuple:
    sn, st = v.get("snippet", {}), v.get("statistics", {})
    pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
    horas = max(1.0, (datetime.now(timezone.utc) - pub).total_seconds() / 3600)
    vistas = int(st.get("viewCount", 0) or 0)
    return vistas / horas, horas, vistas


def revisar_canales(avisar=lambda m: None) -> list:
    """Videos nuevos (≤ 7 días) que van mucho más rápido que lo normal en su canal."""
    from . import motor, seguimiento as seg
    umbral = float(ajustes().get("alerta_outlier_x", 3))
    seguidos = seg.ids_seguidos()
    estado = read_json(ESTADO, {}) or {}
    out = []
    chs = yt.canales(list(seguidos)) if seguidos else {}
    for i, (cid, ch) in enumerate(chs.items(), 1):
        if i % 10 == 0:
            avisar(f"Revisando videos nuevos ({i}/{len(chs)})…")
        a = motor.canal_crudo(cid) or {}
        try:
            vids = yt.ultimos_videos(ch, 8)
        except RuntimeError as e:
            if "cuota" in str(e).lower():
                raise
            continue
        ritmo = [v["vistas"] / max(24.0, v["dias"] * 24) for v in a.get("videos_lista", []) if v.get("dias") and v["dias"] > 3]
        normal = statistics.median(ritmo) if ritmo else None
        for v in vids:
            vph, horas, vistas = _vph(v)
            if horas > 7 * 24 or not normal or vistas < 2000:
                continue
            x = vph / normal
            if x >= umbral:
                sn = v["snippet"]
                out.append(_alerta("outlier", f"outlier:{v['id']}", f"📈 Outlier nuevo en {sn.get('channelTitle', '')}",
                                   f"«{sn.get('title', '')[:90]}» va {x:.1f}x más rápido que lo normal en su canal ({vistas:,} visitas en {horas / 24:.1f} días).".replace(",", "."),
                                   canal_id=cid, video_id=v["id"], url=f"https://www.youtube.com/watch?v={v['id']}",
                                   miniatura=f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg", x=round(x, 1), origen=seguidos.get(cid)))
        estado[cid] = {"revisado": datetime.now().isoformat(timespec="seconds")}
    # canales jóvenes que explotan (con visitas REALES del seguimiento)
    for cid, origen in seguidos.items():
        a = motor.canal_crudo(cid) or {}
        m = seg.metricas(cid)
        if not m or not a or (a.get("edad_dias") or 9999) > 365:
            continue
        d1, d7 = (m.get("d1") or {}).get("ganadas"), (m.get("d7") or {}).get("ganadas")
        crec = m.get("crecimiento")
        if d1 and d7 and (m["d7"]["dias_medidos"] >= 3) and d1 >= 2.5 * d7 / 7 and d1 >= 20_000:
            out.append(_alerta("explota", f"explota:{cid}:{datetime.now():%Y-%m-%d}", f"🚀 {a.get('canal')} está explotando",
                               f"Ganó {d1:,} visitas en 24 h, {d1 / (d7 / 7):.1f}x su ritmo de la semana. Tiene {a.get('edad_dias')} días.".replace(",", "."),
                               canal_id=cid, origen=origen, miniatura=(a.get("top3") or [{}])[0].get("miniatura")))
        elif crec is not None and crec >= 60:
            out.append(_alerta("explota", f"crece:{cid}:{datetime.now():%Y-%W}", f"🚀 {a.get('canal')} creció {crec}% esta semana",
                               f"Canal joven ({a.get('edad_dias')} días) con crecimiento real de +{crec}% frente a la semana anterior.",
                               canal_id=cid, origen=origen))
    write_json(ESTADO, estado)
    return out


def revisar_nichos(avisar=lambda m: None) -> list:
    """En cada nicho seguido busca videos de los últimos 3 días de canales JÓVENES que vuelan."""
    from . import clasificador as clf
    out = []
    nichos = nichos_seguidos()[:5]
    hace3 = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i, nicho in enumerate(nichos, 1):
        avisar(f"Revisando el nicho «{nicho}» ({i}/{len(nichos)})…")
        terminos = [t for t in (clf.TAX.get(nicho, {}).get("f") or clf.aprendidos()["nichos"].get(nicho, {}).get("palabras", []))
                    if not t.endswith("*") and t.isascii() and len(t) > 3][:3]
        q = " | ".join(terminos) or nicho
        try:
            d = yt.api("search", part="snippet", q=q, type="video", order="viewCount", maxResults=25, publishedAfter=hace3,
                       relevanceLanguage="en", videoDuration="medium")
        except RuntimeError as e:
            if "cuota" in str(e).lower():
                raise
            continue
        ids = [it["id"]["videoId"] for it in d.get("items", []) if it.get("id", {}).get("videoId")]
        vids = yt.videos(ids)
        chs = yt.canales(list({v["snippet"]["channelId"] for v in vids}))
        candidatos, canales_vistos = [], set()
        for v in sorted(vids, key=lambda x: -_vph(x)[0]):
            ch = chs.get(v["snippet"]["channelId"]) or {}
            creado = ch.get("snippet", {}).get("publishedAt")
            if not creado:
                continue
            edad = (datetime.now(timezone.utc) - datetime.fromisoformat(creado.replace("Z", "+00:00"))).days
            vph, horas, vistas = _vph(v)
            if edad <= 365 and vph >= 800 and vistas >= 20_000 and horas <= 96 and v["snippet"]["channelId"] not in canales_vistos \
                    and len(candidatos) < 3:
                canales_vistos.add(v["snippet"]["channelId"])
                sn = v["snippet"]
                candidatos.append(_alerta("nicho", f"nicho:{v['id']}", f"🚀 Canal joven explotando en «{nicho}»",
                                   f"{sn.get('channelTitle', '')} ({edad} días): «{sn.get('title', '')[:80]}» lleva {vistas:,} visitas en {horas / 24:.1f} días.".replace(",", "."),
                                   canal_id=v["snippet"]["channelId"], video_id=v["id"], url=f"https://www.youtube.com/watch?v={v['id']}",
                                   miniatura=f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg", nicho=nicho))
        out += candidatos
    return out


def revisar(forzar: bool = False) -> dict:
    """Revisión completa. Corre en segundo plano y no bloquea las búsquedas."""
    if _corriendo["si"]:
        return {"ok": False, "mensaje": "Ya estoy revisando."}
    if not forzar and not ajustes().get("alertas", True):
        return {"ok": False, "mensaje": "Las alertas están apagadas en Ajustes."}
    _corriendo.update(si=True, paso="Empezando…")
    nuevas = []
    try:
        avisar = lambda m: _corriendo.update(paso=m)  # noqa: E731
        nuevas += revisar_canales(avisar)
        if ajustes().get("alertas_nichos", True):
            nuevas += revisar_nichos(avisar)
        n = _guardar_nuevas(nuevas)
        log(f"Alertas: {n} nuevas.")
        return {"ok": True, "nuevas": n}
    except Exception as e:  # noqa: BLE001
        log(f"Alertas: no pude revisar ({e}).", "WARN")
        return {"ok": False, "mensaje": str(e)}
    finally:
        _corriendo.update(si=False, paso="", ultima=datetime.now().isoformat(timespec="seconds"))
        estado = read_json(ESTADO, {}) or {}
        estado["_ultima_revision"] = _corriendo["ultima"]
        write_json(ESTADO, estado)


def en_fondo(forzar: bool = False):
    threading.Thread(target=revisar, args=(forzar,), daemon=True).start()


def estado() -> dict:
    return {"revisando": _corriendo["si"], "paso": _corriendo["paso"],
            "ultima": (read_json(ESTADO, {}) or {}).get("_ultima_revision"), "nuevas": len(lista(True)), "nichos": nichos_seguidos()}


def toca_revision() -> bool:
    u = (read_json(ESTADO, {}) or {}).get("_ultima_revision")
    horas = float(ajustes().get("alertas_cada_horas", 24))
    return not u or (datetime.now() - datetime.fromisoformat(u)).total_seconds() >= horas * 3600
