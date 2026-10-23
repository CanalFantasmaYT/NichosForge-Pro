"""Utilidades comunes: log en consola y lectura/escritura JSON segura.

En Windows, reemplazar un archivo mientras otro hilo lo está leyendo da "[WinError 5] Acceso denegado".
Por eso lecturas y escrituras comparten un candado y se reintenta unas veces antes de rendirse.
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

_lock = threading.RLock()


def log(msg: str, nivel: str = "INFO"):
    linea = f"[{datetime.now().strftime('%H:%M:%S')}] {nivel:5} | {msg}"
    try:
        print(linea, flush=True)
    except UnicodeEncodeError:
        print(linea.encode("ascii", "replace").decode(), flush=True)


def _copia(d):
    return json.loads(json.dumps(d)) if d is not None else None


_mem = {}   # ruta -> (mtime, tamaño, datos)  para archivos grandes que se leen muchas veces


def read_json_cache(path, defecto=None):
    """Como read_json pero sin releer el archivo si no cambió. OJO: devuelve el MISMO objeto (no lo modifiques)."""
    p = Path(path)
    with _lock:
        try:
            st = p.stat()
        except FileNotFoundError:
            return _copia(defecto)
        hit = _mem.get(str(p))
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
        datos = read_json(p, defecto)
        try:
            st = p.stat()
            _mem[str(p)] = (st.st_mtime_ns, st.st_size, datos)
        except FileNotFoundError:
            pass
        return datos


def read_json(path, defecto=None):
    p = Path(path)
    for intento in range(8):
        with _lock:
            if not p.exists():
                return _copia(defecto)
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except PermissionError:
                pass                      # antivirus o Windows lo tiene ocupado: reintentar
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                return _copia(defecto)
        time.sleep(0.05 * (intento + 1))
    return _copia(defecto)


def write_json(path, data):
    p = Path(path)
    texto = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with _lock:
        tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(texto, encoding="utf-8")
        for intento in range(15):
            try:
                os.replace(tmp, p)
                _mem.pop(str(p), None)
                return
            except PermissionError:
                time.sleep(0.05 * (intento + 1))
        try:                              # último recurso: escribir directo encima
            p.write_text(texto, encoding="utf-8")
            _mem.pop(str(p), None)
        finally:
            tmp.unlink(missing_ok=True)


def extract_json(texto: str) -> dict:
    """Saca el JSON aunque venga con ```json, texto antes/después o comas de más."""
    import re
    t = (texto or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    ini = t.find("{")
    if ini == -1:
        raise ValueError("La IA no devolvió JSON.")
    nivel, en_texto, esc = 0, False, False
    for i, ch in enumerate(t[ini:], ini):           # busca la llave que cierra la primera
        if en_texto:
            esc = (ch == "\\" and not esc)
            if ch == '"' and not esc:
                en_texto = False
            continue
        if ch == '"':
            en_texto = True
        elif ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
            if nivel == 0:
                bloque = re.sub(r",\s*([}\]])", r"\1", t[ini:i + 1])
                return json.loads(bloque)
    raise ValueError("La IA no devolvió JSON completo (se cortó).")
