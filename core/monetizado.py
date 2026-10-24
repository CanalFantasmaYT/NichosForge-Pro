"""¿Está monetizado este canal? — verificador honesto.

Ningún dato público dice al 100 % si un canal está en el Programa de Socios de YouTube (YPP): solo su dueño lo ve en
YouTube Studio, y desde 2021 YouTube muestra anuncios también en canales que NO son socios. Por eso este módulo solo
dice «confirmado» cuando hay una PRUEBA segura y, si no, da una probabilidad con sus motivos:

  ✅ Confirmado socio       → botón «Unirse» (membresías) o «Super Thanks»: solo existen en canales del YPP
                              (que puede ser el nivel ampliado, solo con funciones de fans; los anuncios se indican aparte).
  ⛔ Muy probable NO        → menos de 500 suscriptores (mínimo de cualquier nivel del Programa de Socios).
  ⏳ Sin anuncios           → 500-999 suscriptores: sin anuncios, pero podría tener funciones de fans (YPP ampliado).
  🟢 Muy probable           → cumple requisitos (1.000 subs + ~4.000 h o 10M visitas en Shorts) y señal de anuncios activa.
  🟡 Elegible sin confirmar → cumple requisitos, sin prueba directa.
  🟠 Aún no cumple          → 1.000 subs pero pocas horas de reproducción estimadas.

Las pruebas seguras están en la página PÚBLICA del canal (no en la API). Leerla es opcional (`leer_paginas_youtube`,
apagado por defecto): los términos de servicio de YouTube restringen el acceso automatizado a sus páginas.
"""
import re
import threading
from datetime import datetime, timedelta

import requests

from .config import DATOS, ajustes
from .utils import log, read_json, read_json_cache, write_json

RESULTADOS = DATOS / "monetizacion.json"
VIGENCIA_DIAS = 7
_lock = threading.RLock()
CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
             "Accept-Language": "en-US,en;q=0.9"}
COOKIES = {"CONSENT": "YES+cb", "SOCS": "CAI"}          # evita la página de consentimiento de cookies de la UE

# Pruebas en el HTML público (varias formas, porque YouTube cambia su código con frecuencia)
PATRON_UNIRSE = re.compile(r'"sponsorButton"|"sponsorshipsButton"|channelSponsorshipRenderer|"membershipButton"|'
                           r'/channel/[\w-]+/join|"text":\{"content":"(?:Join|Unirse|Unirme|Hazte miembro)"\}', re.I)
PATRON_THANKS = re.compile(r'"superThanks|SUPER_THANKS|"Super Thanks"|superThanksButton|"Gracias Super"', re.I)
PATRON_ANUNCIOS = re.compile(r'"key"\s*:\s*"is_monetization_enabled"\s*,\s*"value"\s*:\s*"(true|false)"')


# ---------------- requisitos con datos de la API ----------------

def _requisitos(a: dict) -> dict:
    """Estimación de horas de reproducción públicas (12 meses) y visitas de Shorts (90 días) con los videos conocidos."""
    hace12 = datetime.now() - timedelta(days=365)
    hace90 = datetime.now() - timedelta(days=90)
    horas, shorts90 = 0.0, 0
    for v in a.get("videos_lista", []):
        try:
            pub = datetime.fromisoformat(str(v.get("publicado"))[:10])
        except Exception:  # noqa: BLE001
            continue
        if v.get("es_short"):
            if pub >= hace90:
                shorts90 += v.get("vistas") or 0
        elif pub >= hace12:
            # una persona ve en promedio ~35-45 % de un video largo: usamos 35 % (estimación conservadora)
            horas += (v.get("vistas") or 0) * (v.get("duracion_seg") or 0) * 0.35 / 3600
    # si la lista de videos es parcial (canales con cientos de videos), extrapola con el total del canal
    conocidos = len(a.get("videos_lista", []))
    total = a.get("videos") if isinstance(a.get("videos"), int) else conocidos
    if conocidos and total > conocidos * 1.3:
        horas *= min(4.0, total / conocidos) * 0.6
    return {"horas_12m": round(horas), "shorts_90d": shorts90}


# ---------------- lectura de la página pública (opcional) ----------------

_ultimo_error = {"msg": ""}


def _leer(url: str) -> str | None:
    """Descarga una página pública de YouTube (máx. ~20 s). Guarda el motivo si falla."""
    try:
        r = requests.get(url, headers=CABECERAS, cookies=COOKIES, timeout=(6, 14))
        if r.status_code == 200 and len(r.text) > 5000:
            if "consent.youtube.com" in r.url or "before you continue" in r.text[:20000].lower():
                _ultimo_error["msg"] = "YouTube pidió aceptar cookies"
                return None
            return r.text
        _ultimo_error["msg"] = f"YouTube respondió {r.status_code}"
    except requests.Timeout:
        _ultimo_error["msg"] = "YouTube tardó demasiado en responder"
    except Exception as e:  # noqa: BLE001
        _ultimo_error["msg"] = f"sin conexión ({type(e).__name__})"
    return None


def senales_pagina(cid: str, video_id: str | None) -> dict:
    """Busca en la página pública del canal (y de un video reciente) las pruebas de monetización."""
    out = {"leida": False, "unirse": False, "super_thanks": False, "anuncios": None}
    paginas = [f"https://www.youtube.com/channel/{cid}"]
    if video_id:
        paginas.append(f"https://www.youtube.com/watch?v={video_id}")
    _ultimo_error["msg"] = ""
    for url in paginas:
        log(f"Monetización: leyendo {url} …")
        html = _leer(url)
        if not html:
            log(f"Monetización: no pude leer la página ({_ultimo_error['msg']}).", "WARN")
            continue
        out["leida"] = True
        if PATRON_UNIRSE.search(html):
            out["unirse"] = True
        if PATRON_THANKS.search(html):
            out["super_thanks"] = True
        m = PATRON_ANUNCIOS.search(html)
        if m and out["anuncios"] is not True:
            out["anuncios"] = m.group(1) == "true"
        if out["unirse"] or out["super_thanks"]:
            break                                      # prueba directa encontrada: no hace falta la segunda página
    out["error"] = "" if out["leida"] else _ultimo_error["msg"]
    log(f"Monetización: página {'leída' if out['leida'] else 'NO leída'} · Unirse={out['unirse']} · Super Thanks={out['super_thanks']} · anuncios={out['anuncios']}")
    return out


# ---------------- veredicto ----------------

def evaluar(a: dict, pagina: dict | None = None) -> dict:
    subs = a.get("suscriptores")
    req = _requisitos(a)
    cumple_horas = req["horas_12m"] >= 4000
    cumple_shorts = req["shorts_90d"] >= 10_000_000
    senales = []
    if subs is None:
        senales.append(("neutral", "El canal oculta su número de suscriptores."))
    else:
        senales.append(("bien" if subs >= 1000 else "neutral" if subs >= 500 else "mal",
                        f"{subs:,} suscriptores (anuncios: mínimo 1.000 · funciones de fans: mínimo 500).".replace(",", ".")))
    senales.append(("bien" if cumple_horas else "neutral", f"≈{req['horas_12m']:,} horas de reproducción ESTIMADAS en 12 meses (mínimo 4.000; es una estimación, no una prueba).".replace(",", ".")))
    if req["shorts_90d"]:
        senales.append(("bien" if cumple_shorts else "neutral", f"≈{req['shorts_90d']:,} visitas de Shorts en 90 días (mínimo 10 millones).".replace(",", ".")))
    p = pagina or {}
    if p.get("leida"):
        if p.get("unirse"):
            senales.append(("bien", "Tiene botón «Unirse» (membresías): solo existe en canales del Programa de Socios."))
        if p.get("super_thanks"):
            senales.append(("bien", "Tiene «Super Thanks»: solo existe en canales del Programa de Socios."))
        if p.get("anuncios") is True:
            senales.append(("bien", "La página indica anuncios activos (puede ser monetización del canal o de YouTube)."))
        elif p.get("anuncios") is False:
            senales.append(("mal", "La página indica que la monetización está desactivada."))
    elif pagina is not None:
        senales.append(("neutral", "No se pudo leer la página pública del canal."))

    subs_n = subs if subs is not None else -1
    cumple_anuncios = subs_n >= 1000 and (cumple_horas or cumple_shorts)          # estimación, no prueba
    if p.get("unirse") or p.get("super_thanks"):
        v, conf, titulo = "si", "confirmado", "En el Programa de Socios (confirmado)"
        anuncios = ("muy probablemente activos" if cumple_anuncios else
                    "sin confirmar (con menos de 1.000 suscriptores solo tendría funciones de fans)" if 0 <= subs_n < 1000 else "sin confirmar")
        motivo = f"Tiene funciones que YouTube solo da a socios. Anuncios: {anuncios}."
    elif p.get("anuncios") is False:
        v, conf, titulo = "no", "alta", "Probablemente sin monetización activa"
        motivo = "La página pública indica la monetización desactivada."
    elif 0 <= subs_n < 500:
        v, conf, titulo = "no", "alta", "Muy probablemente no monetizado"
        motivo = "No llega a 500 suscriptores, el mínimo de cualquier nivel del Programa de Socios."
    elif 500 <= subs_n < 1000:
        v, conf, titulo = "aun_no", "media", "Sin anuncios (muy probable)"
        motivo = ("Con 500-999 suscriptores no puede tener anuncios, pero podría tener funciones de fans "
                  "(membresías, Super Thanks) si entró al Programa de Socios ampliado.")
    elif cumple_anuncios and p.get("anuncios") is True:
        v, conf, titulo = "probable", "alta", "Muy probablemente monetizado"
        motivo = "Según la estimación cumple los requisitos y la página muestra anuncios activos (que también pueden ser de YouTube)."
    elif cumple_anuncios:
        v, conf, titulo = "probable", "media", "Elegible según la estimación (sin confirmar)"
        motivo = "Por suscriptores y horas ESTIMADAS cumpliría los requisitos, pero no hay una prueba directa."
    elif subs_n >= 1000:
        v, conf, titulo = "desconocido", "baja", "Sin confirmar"
        motivo = "Las horas de reproducción estimadas quedan por debajo de 4.000, pero es una estimación: no prueba que no esté monetizado."
    else:
        v, conf, titulo = "desconocido", "baja", "No se puede saber"
        motivo = "Faltan datos públicos (suscriptores ocultos y sin pruebas en la página)."
    return {"veredicto": v, "confianza": conf, "titulo": titulo, "motivo": motivo, "senales": senales,
            "requisitos": req, "pagina_leida": bool(p.get("leida")), "fecha": datetime.now().isoformat(timespec="seconds")}


# ---------------- caché, lotes y uso desde el resto del programa ----------------

def resultado(cid: str) -> dict | None:
    r = (read_json_cache(RESULTADOS, {}) or {}).get(cid)
    if r and r.get("fecha") and datetime.now() - datetime.fromisoformat(r["fecha"]) < timedelta(days=VIGENCIA_DIAS):
        return r
    return None


def _guardar(nuevos: dict):
    with _lock:
        d = read_json(RESULTADOS, {}) or {}
        d.update(nuevos)
        limite = (datetime.now() - timedelta(days=30)).isoformat()
        write_json(RESULTADOS, {k: v for k, v in d.items() if v.get("fecha", "") >= limite})


def verificar(cid: str, forzar: bool = False, leer_pagina: bool | None = None) -> dict | None:
    from . import motor
    if not forzar:
        r = resultado(cid)
        if r and (r.get("pagina_leida") or not (leer_pagina or ajustes().get("leer_paginas_youtube"))):
            return r
    a = motor.canal_crudo(cid)
    if not a:
        return None
    leer = ajustes().get("leer_paginas_youtube", False) if leer_pagina is None else leer_pagina
    pagina = None
    if leer:
        largos = sorted([v for v in a.get("videos_lista", []) if not v.get("es_short")], key=lambda v: str(v.get("publicado")), reverse=True)
        pagina = senales_pagina(cid, largos[0]["id"] if largos else None)
    r = evaluar(a, pagina)
    if pagina is not None and not pagina.get("leida"):
        r["error_pagina"] = pagina.get("error") or "no se pudo leer"
    _guardar({cid: r})
    return r


def verificar_lote(ids: list, al_avanzar=None) -> int:
    from concurrent.futures import ThreadPoolExecutor
    pend = [c for c in dict.fromkeys(ids) if not resultado(c)]
    hechos = {"n": 0}

    def uno(cid):
        try:
            verificar(cid)
        finally:
            hechos["n"] += 1
            if al_avanzar:
                al_avanzar(hechos["n"], len(pend))
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(uno, pend))
    return len(pend)


def resumen(cid: str, a: dict | None = None) -> dict | None:
    """Lo que ve el resto del programa: el resultado guardado o, si no hay, la evaluación sin leer la página."""
    r = resultado(cid)
    if r:
        return r
    return evaluar(a) if a else None
