"""Seguimiento REAL de visitas.

NichosForge toma "fotos" periódicas (visitas totales, suscriptores y videos) de los canales que sigues:
tus canales conectados, los guardados en el embudo y los que marcas con "Seguir". Con la diferencia entre fotos
calcula las visitas ganadas de verdad en 24 h, 7 y 30 días, el crecimiento semana contra semana y los
suscriptores ganados. Cuesta 1 unidad de cuota por cada 50 canales.

Retención: solo se guardan los últimos `seguimiento_dias` días (35 por defecto), en línea con la política de la
API de YouTube de no guardar sus datos más de 30 días sin actualizarlos.
"""
import threading
from datetime import datetime, timedelta

from .config import DATOS, ajustes
from .utils import log, read_json, read_json_cache, write_json

FOTOS = DATOS / "seguimiento.json"
SEGUIDOS = DATOS / "seguidos.json"
INTERVALO_HORAS = 6
_lock = threading.RLock()


def _ahora() -> datetime:
    return datetime.now()


def _t(p: dict) -> datetime:
    return datetime.fromisoformat(p["t"])


# ---------------- qué canales se siguen ----------------

def seguidos_extra() -> list:
    return read_json(SEGUIDOS, [])


def seguir(cid: str):
    with _lock:
        s = seguidos_extra()
        if cid not in s:
            s.append(cid)
            write_json(SEGUIDOS, s)


def dejar(cid: str):
    with _lock:
        write_json(SEGUIDOS, [x for x in seguidos_extra() if x != cid])


def ids_seguidos() -> dict:
    """{canal_id: origen} — origen: 'mio', 'guardado' o 'seguido'."""
    from . import motor
    out = {cid: "seguido" for cid in seguidos_extra()}
    out.update({cid: "guardado" for cid in motor.guardados()})
    out.update({cid: "mio" for cid in motor.ids_mis_canales()})
    return out


# ---------------- fotos ----------------

def _compactar(puntos: list, dias: int) -> list:
    """Últimas 48 h: todas las fotos. Antes: una por día (la última). Más viejo que `dias`: se borra."""
    limite = _ahora() - timedelta(days=dias)
    recientes = _ahora() - timedelta(hours=48)
    por_dia, out = {}, []
    for p in sorted(puntos, key=lambda x: x["t"]):
        t = _t(p)
        if t < limite:
            continue
        if t >= recientes:
            out.append(p)
        else:
            por_dia[p["t"][:10]] = p
    return sorted(list(por_dia.values()) + out, key=lambda x: x["t"])


def registrar(canales_raw: dict):
    """Guarda una foto de canales ya leídos de la API (channels.list): no gasta cuota extra."""
    if not canales_raw:
        return 0
    dias = int(ajustes().get("seguimiento_dias") or 35)
    ahora = _ahora().isoformat(timespec="seconds")
    with _lock:
        d = read_json(FOTOS, {}) or {}
        n = 0
        for cid, ch in canales_raw.items():
            st = ch.get("statistics", {})
            if "viewCount" not in st:
                continue
            p = {"t": ahora, "v": int(st.get("viewCount", 0) or 0), "n": int(st.get("videoCount", 0) or 0)}
            if not st.get("hiddenSubscriberCount"):
                p["s"] = int(st.get("subscriberCount", 0) or 0)
            puntos = d.get(cid, [])
            if puntos and (_ahora() - _t(puntos[-1])).total_seconds() < 1800:
                puntos[-1] = p          # fotos con menos de 30 min de diferencia: se reemplaza la última
            else:
                puntos.append(p)
            d[cid] = _compactar(puntos, dias)
            n += 1
        # limpia canales sin fotos recientes (dejaron de seguirse o expiraron)
        d = {k: v for k, v in d.items() if v}
        write_json(FOTOS, d)
    return n


def tomar_foto(ids: list | None = None) -> dict:
    """Lee las estadísticas actuales de los canales seguidos (1 unidad por cada 50) y las guarda."""
    from . import youtube as yt
    ids = list(ids or ids_seguidos())
    if not ids:
        return {"canales": 0, "mensaje": "Aún no sigues canales: guarda canales, conecta los tuyos o marca 👁 Seguir."}
    lotes = [ids[i:i + 50] for i in range(0, len(ids), 50)]
    datos = {}
    for lote in lotes:
        r = yt.api("channels", usar_cache=False, part="statistics", id=",".join(lote))
        for c in r.get("items", []):
            datos[c["id"]] = c
    n = registrar(datos)
    log(f"Seguimiento: foto de {n} canales.")
    return {"canales": n, "mensaje": f"Foto tomada de {n} canales."}


def ultima_foto() -> str | None:
    d = read_json_cache(FOTOS, {}) or {}
    ts = [p[-1]["t"] for p in d.values() if p]
    return max(ts) if ts else None


def toca_foto() -> bool:
    u = ultima_foto()
    if not u:
        return True
    return (_ahora() - datetime.fromisoformat(u)).total_seconds() >= INTERVALO_HORAS * 3600


# ---------------- métricas ----------------

def _ventana(puntos: list, dias: float) -> dict | None:
    """Visitas ganadas en los últimos `dias`. Si hay menos historial, se proyecta y se marca como proyectado."""
    if len(puntos) < 2:
        return None
    ult = puntos[-1]
    objetivo = _t(ult) - timedelta(days=dias)
    # la foto más cercana al inicio de la ventana (sin pasarse de la última)
    base = min(puntos[:-1], key=lambda p: abs((_t(p) - objetivo).total_seconds()))
    span = (_t(ult) - _t(base)).total_seconds() / 86400
    if span < 0.2:                                         # menos de ~5 horas: aún no es medible
        return None
    ganadas = max(0, ult["v"] - base["v"])          # YouTube a veces corrige visitas hacia abajo: nunca negativo
    subs = (ult.get("s", 0) - base.get("s", 0)) if "s" in ult and "s" in base else None
    proyectado = span < dias * 0.85
    factor = dias / span if proyectado else 1
    return {"ganadas": round(ganadas * factor), "subs": round(subs * factor) if subs is not None else None,
            "videos": ult.get("n", 0) - base.get("n", 0), "dias_medidos": round(span, 1), "proyectado": proyectado}


def metricas(cid: str) -> dict | None:
    puntos = (read_json_cache(FOTOS, {}) or {}).get(cid) or []
    if not puntos:
        return None
    span_total = (_t(puntos[-1]) - _t(puntos[0])).total_seconds() / 86400
    out = {"fotos": len(puntos), "desde": puntos[0]["t"], "ultima": puntos[-1]["t"], "dias": round(span_total, 1),
           "visitas_totales": puntos[-1]["v"], "suscriptores": puntos[-1].get("s")}
    out["d1"], out["d7"], out["d30"] = _ventana(puntos, 1), _ventana(puntos, 7), _ventana(puntos, 30)
    # ritmo diario real y visitas al mes (mejor ventana disponible)
    mejor = out["d30"] or out["d7"] or out["d1"]
    if mejor:
        base_dias = 30 if out["d30"] else 7 if out["d7"] else 1
        out["por_dia"] = round(mejor["ganadas"] / base_dias)
        out["mes"] = round(mejor["ganadas"] * 30 / base_dias)
        out["mes_medido"] = mejor["dias_medidos"]
        out["mes_proyectado"] = mejor["proyectado"]
    # crecimiento: últimos 7 días contra los 7 anteriores (si hay 14 días de datos)
    if span_total >= 12:
        previos = [p for p in puntos if _t(p) <= _t(puntos[-1]) - timedelta(days=7)]
        if len(previos) >= 2:
            ant = _ventana(previos, 7)
            if ant and ant["ganadas"] > 0 and out["d7"]:
                out["crecimiento"] = round(100 * (out["d7"]["ganadas"] - ant["ganadas"]) / ant["ganadas"])
    # serie para gráficos: visitas por día entre fotos consecutivas
    serie = []
    for a, b in zip(puntos, puntos[1:]):
        dd = (_t(b) - _t(a)).total_seconds() / 86400
        if dd >= 0.2:
            serie.append({"t": b["t"], "v": max(0, round((b["v"] - a["v"]) / dd)), "total": b["v"], "s": b.get("s")})
    out["serie"] = serie[-40:]
    return out


def enriquecer(a: dict) -> dict:
    """Devuelve una copia del análisis del canal con las visitas al mes REALES si ya hay mediciones."""
    m = metricas(a["id"])
    if not m:
        return {**a, "seguimiento": None}
    out = {**a, "seguimiento": m,
           "visitas_24h": (m["d1"] or {}).get("ganadas"), "visitas_7d": (m["d7"] or {}).get("ganadas"),
           "visitas_30d": (m["d30"] or {}).get("ganadas"), "subs_7d": (m["d7"] or {}).get("subs"), "crecimiento": m.get("crecimiento")}
    if m.get("mes") is not None and (m.get("mes_medido") or 0) >= 1:
        mes = m["mes"]
        out["visitas_mes_estimadas"] = a.get("visitas_mes")
        out["visitas_mes"] = mes
        out["metodo_mes"] = (f"REAL: medido en {m['mes_medido']} días" + (" (proyectado a 30)" if m["mes_proyectado"] else ""))
        rpm = a.get("rpm") or 0
        out["ingreso_mes"] = round(mes / 1000 * rpm)
        out["ingreso_mes_bajo"] = round(mes / 1000 * (a.get("rpm_bajo") or 0))
        out["ingreso_mes_alto"] = round(mes / 1000 * (a.get("rpm_alto") or 0))
        out["ingreso_anio"] = round(mes * 12 / 1000 * rpm)
        out["real"] = True
        aj = ajustes()
        mes_min = int(aj["visitas_mes_min"])
        if a.get("checks"):
            checks = [list(c) for c in a["checks"]]
            checks[1] = [f"{mes_min:,} visitas al mes o más (medido)".replace(",", "."), mes >= mes_min]
            out["checks"] = checks
            out["es_referente"] = checks[0][1] and checks[1][1] and checks[2][1] and a.get("idioma") == "en"
            if out["es_referente"]:
                out["rol"] = "referente"
            elif a.get("rol") == "referente":
                out["rol"] = "ingles"
    return out


# ---------------- programador automático ----------------

def _radar_auto():
    """Cada 6 h actualiza el radar de miniaturas (si está activado y no hay otro trabajo en curso)."""
    from . import miniaturas, motor
    from .config import claves_youtube
    if not ajustes().get("radar_miniaturas_auto", True) or not claves_youtube() or not miniaturas.disponible():
        return
    ult = max((v.get("fecha", "") for v in miniaturas.corpus().values() if v.get("fuente") == "tendencias"), default="")
    if ult and (_ahora() - datetime.fromisoformat(ult)).total_seconds() < INTERVALO_HORAS * 3600:
        return
    if motor.estado().get("estado") != "trabajando":
        motor.radar_miniaturas()

def iniciar_programador():
    """Hilo en segundo plano: cada 30 min revisa si toca una foto nueva (cada 6 h)."""
    def ciclo():
        import time
        time.sleep(20)
        while True:
            try:
                from .config import claves_youtube
                if claves_youtube() and ids_seguidos() and toca_foto():
                    tomar_foto()
                _radar_auto()
                from . import alertas
                if ajustes().get("alertas", True) and claves_youtube() and alertas.toca_revision():
                    alertas.en_fondo()
            except Exception as e:  # noqa: BLE001
                log(f"Seguimiento: no se pudo tomar la foto ({e}).", "WARN")
            time.sleep(1800)
    threading.Thread(target=ciclo, daemon=True, name="seguimiento").start()
