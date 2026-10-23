"""Verificación LOCAL de "sin rostro": 100 % gratis, ilimitada y sin API.

Cómo decide (criterio central de Aprende a Monetizar: nadie aparece a cámara):
  1. Descarga de i.ytimg.com (público, sin cuota) la miniatura y 3 fotogramas de DENTRO de cada video
     (hq1/hq2/hq3, que YouTube genera solo) de los últimos videos largos del canal.
  2. Detecta caras con YuNet (OpenCV, modelo incluido en /modelos, licencia BSD-3).
  3. Reconoce si es la MISMA persona con SFace (OpenCV, Apache 2.0; se descarga sola la primera vez).
  4. Si la misma cara aparece en muchos videos → hay un creador a cámara (marca personal).
     Si no hay caras, o son caras distintas (personajes del tema, celebridades, fotos de archivo) → sin rostro.
Sin el reconocedor (sin internet la primera vez) usa solo la detección: % de fotogramas con una cara grande.
"""
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .config import BASE, DATOS, ajustes
from .utils import log, read_json, read_json_cache, write_json

MODELOS = BASE / "modelos"
YUNET = MODELOS / "yunet_s_640_640.onnx"
SFACE = MODELOS / "face_recognition_sface_2021dec.onnx"
SFACE_SHA = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
SFACE_URLS = [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
]
RESULTADOS = DATOS / "rostros.json"
VIGENCIA_DIAS = 30
MISMA_PERSONA = 0.40          # similitud coseno de SFace (OpenCV recomienda 0.363)
_local = threading.local()
_lock = threading.RLock()
_descarga = {"estado": "pendiente", "error": ""}
_CV = {"listo": False}
_POOL = {"p": None}


def cv():
    """Importa OpenCV una vez y baja su nivel de registro: OpenCV 5 avisa (WARN) cada vez que se crea un modelo
    («Targets are not supported by the new graph engine») aunque funciona bien. Los errores reales se siguen viendo."""
    import cv2
    if not _CV["listo"]:
        try:
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        except Exception:  # noqa: BLE001
            try:
                cv2.setLogLevel(2)
            except Exception:  # noqa: BLE001
                pass
        _CV["listo"] = True
    return cv2


def pool() -> ThreadPoolExecutor:
    """Hilos de imágenes que se REUTILIZAN: cada hilo crea su detector una sola vez (antes se recreaba en cada tanda)."""
    with _lock:
        if _POOL["p"] is None:
            _POOL["p"] = ThreadPoolExecutor(max_workers=12, thread_name_prefix="nf-img")
        return _POOL["p"]


# ---------------- modelos ----------------

def opencv_ok() -> bool:
    try:
        cv()
        return True
    except ImportError:
        return False


def estado_modelos() -> dict:
    return {"opencv": opencv_ok(), "detector": YUNET.exists(), "reconocedor": SFACE.exists(),
            "descarga": _descarga["estado"], "error": _descarga["error"]}


def descargar_reconocedor() -> bool:
    """Descarga SFace (una sola vez, ~37 MB) y verifica que sea el archivo original."""
    if SFACE.exists():
        return True
    with _lock:
        if SFACE.exists():
            return True
        _descarga.update(estado="descargando", error="")
        for url in SFACE_URLS:
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200 and len(r.content) > 1_000_000 and hashlib.sha256(r.content).hexdigest() == SFACE_SHA:
                    MODELOS.mkdir(exist_ok=True)
                    tmp = SFACE.with_suffix(".tmp")
                    tmp.write_bytes(r.content)
                    tmp.replace(SFACE)
                    _descarga.update(estado="listo")
                    log("Reconocedor facial SFace descargado.")
                    return True
            except Exception as e:  # noqa: BLE001
                _descarga["error"] = str(e)[:120]
        _descarga.update(estado="error", error=_descarga["error"] or "No se pudo descargar (¿sin internet?).")
        return False


def _detector():
    cv2 = cv()
    if not hasattr(_local, "det"):
        _local.det = cv2.FaceDetectorYN.create(str(YUNET), "", (320, 320), 0.75, 0.3, 20)
    return _local.det


def _reconocedor():
    cv2 = cv()
    if not SFACE.exists():
        return None
    if not hasattr(_local, "rec"):
        _local.rec = cv2.FaceRecognizerSF.create(str(SFACE), "")
    return _local.rec


# ---------------- imágenes ----------------

def _bajar(url: str):
    cv2 = cv()
    import numpy as np
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    try:
        r = _local.s.get(url, timeout=12)
        if r.status_code != 200 or len(r.content) < 2500:          # 404 o imagen gris de "no disponible"
            return None
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        return img if img is not None and img.shape[0] >= 90 else None
    except Exception:  # noqa: BLE001
        return None


def _caras(img) -> list:
    det = _detector()
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, caras = det.detect(img)
    out = []
    for f in (caras if caras is not None else []):
        x, y, cw, ch, score = f[0], f[1], f[2], f[3], f[-1]
        if min(cw, ch) < 22:            # caras diminutas (gente al fondo, multitudes): no cuentan
            continue
        out.append({"fila": f, "area": float(cw * ch) / (w * h), "score": float(score)})
    return out


def _huella(img, cara):
    rec = _reconocedor()
    if rec is None:
        return None
    try:
        return rec.feature(rec.alignCrop(img, cara["fila"])).flatten()
    except Exception:  # noqa: BLE001
        return None


def _similitud(a, b) -> float:
    import numpy as np
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1))


# ---------------- verificación de un canal ----------------

def verificar(a: dict, max_videos: int = 6) -> dict:
    """Mira miniatura + 3 fotogramas de los últimos videos largos y decide si hay un creador a cámara."""
    if not opencv_ok() or not YUNET.exists():
        return {"veredicto": "sin_verificar", "motivo": "Falta OpenCV (ejecuta instalar_actualizar.bat)."}
    if not SFACE.exists() and _descarga["estado"] == "pendiente":
        descargar_reconocedor()
    vids = sorted([v for v in a.get("videos_lista", []) if not v.get("es_short")], key=lambda v: v.get("publicado", ""), reverse=True)[:max_videos]
    if not vids:
        return {"veredicto": "sin_verificar", "motivo": "Sin videos largos para mirar."}
    tareas = []
    for v in vids:
        tareas.append((v["id"], "miniatura", f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg"))
        for k in (1, 2, 3):
            tareas.append((v["id"], "fotograma", f"https://i.ytimg.com/vi/{v['id']}/hq{k}.jpg"))

    def procesar(t):
        vid, tipo, url = t
        img = _bajar(url)
        if img is None:
            return None
        caras = _caras(img)
        return {"vid": vid, "tipo": tipo, "url": url, "caras": [{"area": c["area"], "huella": _huella(img, c)} for c in caras[:4]]}

    res = [r for r in pool().map(procesar, tareas) if r]
    if not res:
        return {"veredicto": "sin_verificar", "motivo": "No pude descargar las imágenes (¿sin internet?)."}
    fotogramas = [r for r in res if r["tipo"] == "fotograma"]
    miniaturas = [r for r in res if r["tipo"] == "miniatura"]
    pct_frames = sum(1 for r in fotogramas if r["caras"]) / (len(fotogramas) or 1)
    pct_frames_grande = sum(1 for r in fotogramas if any(c["area"] >= 0.03 for c in r["caras"])) / (len(fotogramas) or 1)
    pct_minis = sum(1 for r in miniaturas if r["caras"]) / (len(miniaturas) or 1)
    n_videos = len({r["vid"] for r in res})

    # agrupar caras por identidad (misma persona)
    grupos = []                    # [{"huella":…, "videos": set, "fotogramas": set, "urls": [...]}]
    con_reconocimiento = _reconocedor() is not None
    if con_reconocimiento:
        for r in res:
            for c in r["caras"]:
                if c["huella"] is None:
                    continue
                g = next((g for g in grupos if _similitud(g["huella"], c["huella"]) >= MISMA_PERSONA), None)
                if g is None:
                    g = {"huella": c["huella"], "videos": set(), "en_fotogramas": set(), "urls": [], "frames_por_video": {}}
                    grupos.append(g)
                g["videos"].add(r["vid"])
                if r["tipo"] == "fotograma":
                    g["en_fotogramas"].add(r["vid"])
                    g["frames_por_video"][r["vid"]] = g["frames_por_video"].get(r["vid"], 0) + 1
                if len(g["urls"]) < 4 and r["url"] not in g["urls"]:
                    g["urls"].append(r["url"])
    creador = max(grupos, key=lambda g: (len(g["videos"]), len(g["en_fotogramas"])), default=None)
    rep_videos = len(creador["videos"]) if creador else 0
    rep_frames = len(creador["en_fotogramas"]) if creador else 0

    # quien está a cámara sale en la mayoría de los fotogramas de cada video; un famoso del tema, de vez en cuando
    cobertura = (sum(creador["frames_por_video"].values()) / (3 * max(1, len(creador["frames_por_video"])))) if creador and creador["frames_por_video"] else 0
    if con_reconocimiento:
        if rep_videos >= max(3, round(0.5 * n_videos)) and rep_frames >= 2 and cobertura >= 0.45:
            veredicto, motivo = "con_rostro", (f"La misma persona aparece en {rep_videos} de {n_videos} videos y dentro del video en "
                                               f"{round(100 * cobertura)} % de los fotogramas: está a cámara.")
        elif rep_videos >= max(3, round(0.5 * n_videos)) and rep_frames <= 1:
            veredicto, motivo = "dudoso", (f"La misma cara está en {rep_videos} de {n_videos} miniaturas pero casi nunca dentro del video: "
                                           "puede ser el creador solo en la miniatura o un personaje del nicho.")
        elif pct_frames <= 0.25 and rep_videos <= 2:
            veredicto, motivo = "sin_rostro", f"Casi no hay caras dentro de los videos ({round(100 * pct_frames)} % de los fotogramas) y ninguna persona se repite."
        elif rep_videos <= 2:
            veredicto, motivo = "sin_rostro", f"Aparecen caras, pero son personas distintas en cada video ({len(grupos)} identidades): rostros del tema, no un creador."
        else:
            veredicto, motivo = "dudoso", f"Una persona se repite en {rep_videos} de {n_videos} videos: podría ser el creador o un personaje recurrente del nicho."
        confianza = "alta" if n_videos >= 5 and len(fotogramas) >= 10 else "media"
    else:
        if pct_frames_grande >= 0.55:
            veredicto, motivo = "con_rostro", f"Hay una cara grande en el {round(100 * pct_frames_grande)} % de los fotogramas (típico de alguien a cámara)."
        elif pct_frames <= 0.2:
            veredicto, motivo = "sin_rostro", f"Casi no hay caras dentro de los videos ({round(100 * pct_frames)} % de los fotogramas)."
        else:
            veredicto, motivo = "dudoso", "Hay caras en algunos fotogramas; sin el reconocedor no sé si es la misma persona."
        confianza = "media" if veredicto != "dudoso" else "baja"
    ejemplos = (creador["urls"] if creador and veredicto in ("con_rostro", "dudoso") else
                [r["url"] for r in res if r["caras"]][:4] or [r["url"] for r in fotogramas[:4]])
    return {"veredicto": veredicto, "motivo": motivo, "confianza": confianza,
            "modo": "reconocimiento facial" if con_reconocimiento else "solo detección",
            "videos": n_videos, "imagenes": len(res), "pct_fotogramas_con_cara": round(100 * pct_frames),
            "pct_miniaturas_con_cara": round(100 * pct_minis), "identidades": len(grupos),
            "creador_en_videos": rep_videos, "ejemplos": ejemplos[:4], "fecha": datetime.now().isoformat(timespec="seconds")}


# ---------------- caché y lotes ----------------

def resultado(cid: str) -> dict | None:
    r = (read_json_cache(RESULTADOS, {}) or {}).get(cid)
    if r and r.get("fecha") and datetime.now() - datetime.fromisoformat(r["fecha"]) < timedelta(days=VIGENCIA_DIAS):
        return r
    return None


def guardar(resultados: dict):
    if not resultados:
        return
    with _lock:
        d = read_json(RESULTADOS, {}) or {}
        d.update(resultados)
        limite = datetime.now() - timedelta(days=VIGENCIA_DIAS)
        d = {k: v for k, v in d.items() if v.get("fecha") and datetime.fromisoformat(v["fecha"]) >= limite}
        write_json(RESULTADOS, d)


def verificar_canal(cid: str, forzar: bool = False) -> dict | None:
    from . import motor
    if not forzar:
        r = resultado(cid)
        if r:
            return r
    a = motor.canal_crudo(cid)
    if not a:
        return None
    r = verificar(a)
    if r.get("veredicto") != "sin_verificar":
        guardar({cid: r})
    return r


def verificar_lote(ids: list, al_avanzar=None, forzar: bool = False) -> dict:
    """Verifica muchos canales en paralelo. al_avanzar(hechos, total) para mostrar progreso."""
    from . import motor
    pendientes = [c for c in dict.fromkeys(ids) if forzar or not resultado(c)]
    if not pendientes or not opencv_ok():
        return {}
    if not SFACE.exists():
        descargar_reconocedor()
    hechos, out, t0 = {"n": 0}, {}, time.time()

    def uno(cid):
        a = motor.canal_crudo(cid)
        r = verificar(a) if a else None
        hechos["n"] += 1
        if al_avanzar:
            al_avanzar(hechos["n"], len(pendientes))
        return cid, r
    with ThreadPoolExecutor(max_workers=4) as ex:
        for cid, r in ex.map(uno, pendientes):
            if r and r.get("veredicto") != "sin_verificar":
                out[cid] = r
    guardar(out)
    log(f"Rostros: {len(out)} canales verificados en {time.time() - t0:.0f} s.")
    return out


# ---------------- aplicar al análisis ----------------

def aplicar(a: dict) -> dict:
    """Ajusta "¿es automatizado?" con lo que se VIO en las imágenes (prevalece sobre las pistas de texto)."""
    r = resultado(a["id"])
    if not r:
        return a
    out = {**a, "rostro": r}
    senales = list(a.get("auto_senales") or [])
    score = a.get("auto_score") or 0
    if r["veredicto"] == "con_rostro":
        out["auto_score"] = min(score, 25)
        out["auto_tipo"] = "marca"
        senales.insert(0, f"➖ Verificado en imágenes: {r['motivo']}")
    elif r["veredicto"] == "sin_rostro":
        out["auto_score"] = max(min(98, score + 20), 65 if r["confianza"] == "alta" else score)
        out["auto_tipo"] = "automatizado" if out["auto_score"] >= 65 else "posible"
        senales.insert(0, f"➕ Verificado en imágenes: {r['motivo']}")
    else:
        senales.insert(0, f"❓ Imágenes: {r['motivo']}")
    out["auto_senales"] = senales
    return out
