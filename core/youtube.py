"""YouTube Data API v3 para NichosForge Pro (mismo esquema que el buscador de VideoForge).

Costo en cuota (gratis: 10.000 unidades al día):
  search.list = 100 · channels / playlistItems / videos = 1 (hasta 50 elementos por llamada)
Las respuestas se guardan en datos/_cache para no pagar dos veces la misma consulta.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone

import threading
from concurrent.futures import ThreadPoolExecutor

import requests

from .config import DATOS, clave, load_global
from .utils import read_json, write_json

API = "https://www.googleapis.com/youtube/v3"
UNIDADES = {"search": 100}
CACHE = DATOS / "_cache"
CUOTA = DATOS / "_cuota.json"


# ---------- cuota (por clave) ----------

def _hoy() -> str:
    # La cuota se reinicia a medianoche hora del Pacífico (UTC-8 aprox.)
    return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d")


def _hash(k: str) -> str:
    return hashlib.sha1(k.encode()).hexdigest()[:10]


_cq = {"d": None, "t": 0.0}
_cq_lock = threading.RLock()


def _cuota() -> dict:
    """Cuota del día en memoria (se guarda en disco como mucho cada medio segundo: va más rápido en paralelo)."""
    with _cq_lock:
        d = _cq["d"]
        if d is None or d.get("dia") != _hoy():
            d = read_json(CUOTA, {}) or {}
            if d.get("dia") != _hoy():                    # día nuevo (o formato viejo): se reinicia
                d = {"dia": _hoy(), "total": 0, "claves": {}}
            _cq["d"] = d
        return d


def _guardar_cuota(forzar: bool = False):
    with _cq_lock:
        if forzar or time.time() - _cq["t"] > 0.5:
            _cq["t"] = time.time()
            write_json(CUOTA, _cq["d"])


def cuota_hoy() -> int:
    return int(_cuota().get("total", 0))


def _sumar_cuota(k: str, n: int):
    with _cq_lock:
        d = _cuota()
        d["total"] = int(d.get("total", 0)) + n
        c = d["claves"].setdefault(_hash(k), {"u": 0})
        c["u"] = int(c.get("u", 0)) + n
        _guardar_cuota()


def _marcar(k: str, motivo: str):
    with _cq_lock:
        _cuota()["claves"].setdefault(_hash(k), {"u": 0})["agotada"] = motivo
        _guardar_cuota(True)


def estado_claves() -> list:
    from .config import claves_youtube
    d = _cuota()
    out = []
    for i, k in enumerate(claves_youtube()):
        c = d["claves"].get(_hash(k), {})
        out.append({"n": i + 1, "vista": k[:6] + "…" + k[-4:] if len(k) > 12 else "✓", "usadas": int(c.get("u", 0)),
                    "agotada": c.get("agotada") or "", "id": _hash(k)})
    return out


# ---------- llamada base ----------

def _cache_get(k: str):
    p = CACHE / f"{k}.json"
    if p.exists() and time.time() - p.stat().st_mtime < float(load_global()["cache_horas"]) * 3600:
        return read_json(p)
    return None


_local = threading.local()


def _sesion() -> requests.Session:
    """Una sesión por hilo: reutiliza la conexión con Google (mucho más rápido que abrir una por petición)."""
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16))
    return _local.s


def en_paralelo(fn, items: list, hilos: int = 8) -> list:
    """Ejecuta fn(item) en paralelo y devuelve los resultados en el mismo orden. Los errores de cuota se propagan."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(hilos, len(items))) as ex:
        return list(ex.map(fn, items))


AGOTADA = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}
INVALIDA = {"keyInvalid", "accessNotConfigured", "ipRefererBlocked", "keyExpired", "API_KEY_INVALID", "forbidden"}


def api(endpoint: str, usar_cache: bool = True, **params) -> dict:
    from .config import claves_youtube
    params = {k: v for k, v in params.items() if v not in (None, "", [])}
    ck = hashlib.sha1((endpoint + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    if usar_cache:
        hit = _cache_get(ck)
        if hit is not None:
            return hit
    claves = claves_youtube()
    if not claves:
        raise RuntimeError("No hay ninguna clave de YouTube (agrégala en Ajustes).")
    estado = _cuota()["claves"]
    disponibles = [k for k in claves if not estado.get(_hash(k), {}).get("agotada")]
    if not disponibles:
        raise RuntimeError(f"Se acabó la cuota de tus {len(claves)} clave(s) de YouTube por hoy "
                           "(se reinicia a medianoche hora del Pacífico). Agrega otra clave en Ajustes.")
    ultimo = ""
    for k in disponibles:
        r = None
        for intento in range(4):                       # cortes momentáneos: reintenta con pausas crecientes
            try:
                r = _sesion().get(f"{API}/{endpoint}", params={**params, "key": k}, timeout=30)
                if r.status_code in (500, 502, 503, 504) and intento < 3:
                    time.sleep(0.8 * (intento + 1))
                    continue
                break
            except requests.RequestException as e:
                if hasattr(_local, "s"):
                    del _local.s                       # conexión rota: abre una nueva
                if intento == 3:
                    raise RuntimeError(f"No se pudo conectar con YouTube tras 4 intentos ({type(e).__name__}). "
                                       "Revisa tu internet y vuelve a intentarlo.") from e
                time.sleep(0.8 * (intento + 1))
        _sumar_cuota(k, UNIDADES.get(endpoint, 1))
        if r.status_code == 200:
            data = r.json()
            CACHE.mkdir(exist_ok=True)
            write_json(CACHE / f"{ck}.json", data)
            return data
        try:
            err = r.json()["error"]
            msg = err.get("message", "")
            razones = {e.get("reason") for e in err.get("errors", [])} | {d.get("reason") for d in err.get("details", []) if isinstance(d, dict)}
        except Exception:  # noqa: BLE001
            msg, razones = r.text[:300], set()
        if razones & AGOTADA:
            _marcar(k, "sin cuota")
            ultimo = "sin cuota"
            continue                                       # siguiente clave
        if razones & INVALIDA or "API key not valid" in msg:
            _marcar(k, "inválida o sin permiso")
            ultimo = "clave inválida"
            continue
        if "playlistNotFound" in razones:
            raise RuntimeError("playlistNotFound")
        raise RuntimeError(f"YouTube API ({endpoint}): {re.sub(r'<[^>]+>', '', msg)}")
    raise RuntimeError("Se acabó la cuota de todas tus claves de YouTube por hoy." if ultimo == "sin cuota"
                       else "Ninguna de tus claves de YouTube funciona: revísalas en Ajustes.")


def limpiar_cache() -> int:
    n = 0
    if CACHE.exists():
        for p in CACHE.glob("*.json"):
            p.unlink(missing_ok=True)
            n += 1
    return n


def probar_clave(k: str | None = None) -> str:
    """Prueba una clave concreta (o la rotación completa si no se da ninguna)."""
    if not k:
        api("videos", usar_cache=False, part="id", id="dQw4w9WgXcQ")
        return "La clave funciona."
    r = requests.get(f"{API}/videos", params={"part": "id", "id": "dQw4w9WgXcQ", "key": k}, timeout=20)
    _sumar_cuota(k, 1)
    if r.status_code == 200:
        with _cq_lock:
            _cuota()["claves"].setdefault(_hash(k), {"u": 0}).pop("agotada", None)
            _guardar_cuota(True)
        return "Funciona"
    try:
        msg = r.json()["error"]["message"]
    except Exception:  # noqa: BLE001
        msg = r.text[:200]
    raise RuntimeError(re.sub(r"<[^>]+>", "", msg))


def probar_claves() -> list:
    from .config import claves_youtube
    out = []
    for i, k in enumerate(claves_youtube()):
        try:
            out.append({"n": i + 1, "ok": True, "mensaje": probar_clave(k)})
        except Exception as e:  # noqa: BLE001
            out.append({"n": i + 1, "ok": False, "mensaje": str(e)[:160]})
    return out


# ---------- utilidades ----------

def dur_iso(s: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def norm_txt(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


# ---------- búsquedas ----------

def buscar_videos(frase: str, idioma: str = "", dias: int = 365, n: int = 50, region: str = "",
                  duracion: str = "", orden: str = "viewCount", paginas: int = 1, categoria: str = "", tema: str = "") -> list:
    """Videos de una frase en el periodo (search.list: 100 unidades por página de 50)."""
    despues = (datetime.now(timezone.utc) - timedelta(days=int(dias))).strftime("%Y-%m-%dT%H:%M:%SZ") if dias else None
    items, token = [], None
    for _ in range(max(1, int(paginas))):
        d = api("search", part="snippet", q=frase, type="video", maxResults=min(50, int(n)), order=orden or "viewCount",
                publishedAfter=despues, relevanceLanguage=idioma or None, regionCode=region or None,
                videoDuration=duracion if duracion in ("short", "medium", "long") else None, pageToken=token,
                videoCategoryId=categoria or None, topicId=tema or None)
        items += d.get("items", [])
        token = d.get("nextPageToken")
        if not token:
            break
    return items


def populares(region: str = "US", categoria: str = "", n: int = 50) -> list:
    """Videos en tendencia de un país y categoría (chart=mostPopular): solo 1 unidad por 50 videos."""
    try:
        d = api("videos", part="snippet,statistics,contentDetails", chart="mostPopular", regionCode=region,
                videoCategoryId=categoria or None, maxResults=min(50, n))
    except RuntimeError as e:
        if "cuota" in str(e).lower() or "clave" in str(e).lower():
            raise
        return []   # hay categorías sin lista de tendencias en algunos países
    return d.get("items", [])


def buscar_canales(frase: str, idioma: str = "", n: int = 25, region: str = "") -> list:
    """Canales por palabra clave (search.list type=channel: 100 unidades)."""
    d = api("search", part="snippet", q=frase, type="channel", maxResults=min(50, int(n)),
            relevanceLanguage=idioma or None, regionCode=region or None)
    return [it["snippet"]["channelId"] for it in d.get("items", []) if it.get("snippet", {}).get("channelId")]


def resolver_canal(ref: str) -> str | None:
    """Acepta ID (UC...), link /channel/, @handle, link con @handle o el nombre del canal."""
    ref = (ref or "").strip()
    if not ref:
        return None
    m = re.search(r"(UC[\w-]{22})", ref)
    if m:
        return m.group(1)
    m = re.search(r"@([\w.\-·]+)", ref)
    handle = m.group(1) if m else ref.rstrip("/").split("/")[-1]
    if " " not in handle:
        d = api("channels", part="id", forHandle="@" + handle.lstrip("@"))
        if d.get("items"):
            return d["items"][0]["id"]
    d = api("search", part="snippet", q=ref, type="channel", maxResults=5)
    items = d.get("items") or []
    for it in items:
        if norm_txt(it["snippet"].get("title")) == norm_txt(ref):
            return it["snippet"]["channelId"]
    return items[0]["snippet"]["channelId"] if items else None


def canales(ids: list) -> dict:
    ids = list(dict.fromkeys(i for i in ids if i))
    lotes = [ids[i:i + 50] for i in range(0, len(ids), 50)]
    res = en_paralelo(lambda l: api("channels", part="snippet,statistics,contentDetails,status,brandingSettings,topicDetails",
                                     id=",".join(l)).get("items", []), lotes, 4)
    return {c["id"]: c for lote in res for c in lote}


def videos(ids: list) -> list:
    ids = list(dict.fromkeys(i for i in ids if i))
    lotes = [ids[i:i + 50] for i in range(0, len(ids), 50)]
    res = en_paralelo(lambda l: api("videos", part="snippet,statistics,contentDetails", id=",".join(l)).get("items", []), lotes, 6)
    return [v for lote in res for v in lote]


def ultimos_videos(canal: dict, n: int = 30) -> list:
    pl = (canal.get("contentDetails", {}).get("relatedPlaylists") or {}).get("uploads")
    if not pl:
        return []
    ids, token = [], None
    while len(ids) < n:
        try:
            d = api("playlistItems", part="contentDetails", playlistId=pl, maxResults=min(50, n - len(ids)),
                    pageToken=token)
        except RuntimeError as e:
            if "playlistNotFound" in str(e) or "404" in str(e):
                return []
            raise
        ids += [it["contentDetails"]["videoId"] for it in d.get("items", [])]
        token = d.get("nextPageToken")
        if not token:
            break
    return videos(ids)


def top_videos_canal(canal_id: str, n: int = 15) -> list:
    """Los más vistos de toda la historia del canal (100 unidades)."""
    d = api("search", part="id", channelId=canal_id, type="video", order="viewCount", maxResults=min(50, n))
    return videos([it["id"]["videoId"] for it in d.get("items", []) if it.get("id", {}).get("videoId")])
