"""IA opcional de NichosForge Pro, con varios proveedores y respaldo automático.

Proveedores (todos opcionales):
  gemini      Google AI Studio · GEMINI_API_KEY · plan gratis (recomendado)
  freellmapi  Proxy local FreeLLMAPI (github.com/tashfeenahmed/freellmapi) · FREELLMAPI_KEY
              Junta varias APIs gratis detrás de un solo endpoint y cambia de proveedor si uno se agota.
  groq        GROQ_API_KEY · plan gratis, muy rápido
  claude      ANTHROPIC_API_KEY · de pago
  openai      OPENAI_API_KEY · de pago

En modo "auto" se prueba en el orden de Ajustes: si uno falla (límite, caída, clave mala) pasa al siguiente.
Gemini, Groq, FreeLLMAPI y OpenAI se llaman con el formato compatible con OpenAI usando solo 'requests'.
"""
import requests

from .config import ajustes, clave
from .utils import extract_json, log

PROVEEDORES = {
    "gemini": {"nombre": "Gemini (Google)", "clave": "GEMINI_API_KEY", "gratis": True,
               "base": "https://generativelanguage.googleapis.com/v1beta/openai", "modelo": "ia_modelo_gemini",
               "respaldo": "gemini-2.5-flash"},
    "freellmapi": {"nombre": "FreeLLMAPI (local)", "clave": "FREELLMAPI_KEY", "gratis": True,
                   "base": None, "modelo": "ia_modelo_freellmapi", "respaldo": "freellmapi/auto"},
    "groq": {"nombre": "Groq", "clave": "GROQ_API_KEY", "gratis": True,
             "base": "https://api.groq.com/openai/v1", "modelo": "ia_modelo_groq", "respaldo": "llama-3.1-8b-instant"},
    "claude": {"nombre": "Claude (Anthropic)", "clave": "ANTHROPIC_API_KEY", "gratis": False, "modelo": "ia_modelo_claude"},
    "openai": {"nombre": "OpenAI", "clave": "OPENAI_API_KEY", "gratis": False,
               "base": "https://api.openai.com/v1", "modelo": "ia_modelo_openai"},
}
ORDEN_DEFECTO = ["gemini", "freellmapi", "groq", "claude", "openai"]
# Direcciones donde suele quedar FreeLLMAPI (la app de escritorio usa 31415; la guía de GitHub, 3001)
FREELLMAPI_CANDIDATAS = ["http://127.0.0.1:31415/v1", "http://127.0.0.1:3001/v1"]

ultimo = {"proveedor": None, "errores": []}


def _orden() -> list:
    aj = ajustes()
    elegido = aj.get("ia_proveedor") or "auto"
    if elegido != "auto":
        return [elegido] if elegido in PROVEEDORES else []
    orden = [p.strip() for p in str(aj.get("ia_orden") or "").split(",") if p.strip() in PROVEEDORES]
    return orden + [p for p in ORDEN_DEFECTO if p not in orden]


def configurados() -> list:
    return [p for p in _orden() if clave(PROVEEDORES[p]["clave"])]


def proveedor() -> str:
    c = configurados()
    return c[0] if c else ""


def disponible() -> bool:
    return bool(configurados())


def nombre(p: str) -> str:
    return PROVEEDORES.get(p, {}).get("nombre", p or "ninguno")


def _normalizar_url(u: str) -> str:
    u = (u or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.startswith("http"):
        u = "http://" + u
    u = u.replace("://localhost", "://127.0.0.1")  # en Windows 'localhost' puede ir por IPv6 y no conectar
    if not u.endswith("/v1"):
        u += "/v1"
    return u


def _base(p: str) -> str:
    if p == "freellmapi":
        return _normalizar_url(ajustes().get("freellmapi_url")) or FREELLMAPI_CANDIDATAS[0]
    return PROVEEDORES[p]["base"]


def _post(base: str, p: str, cuerpo: dict):
    return requests.post(f"{base}/chat/completions", timeout=120, json=cuerpo,
                         headers={"Authorization": f"Bearer {clave(PROVEEDORES[p]['clave'])}", "Content-Type": "application/json"})


def _una_llamada(p: str, msgs: list, max_tokens: int, modelo: str, modo_json: bool = False) -> tuple:
    cuerpo = {"model": modelo, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.4 if modo_json else 0.7}
    if modo_json:
        cuerpo["response_format"] = {"type": "json_object"}
    base = _base(p)
    try:
        r = _post(base, p, cuerpo)
    except requests.ConnectionError as e:
        if p != "freellmapi":
            raise RuntimeError(f"no se pudo conectar con {base}.") from e
        r = None
        for alt in [u for u in FREELLMAPI_CANDIDATAS if u != base]:  # busca FreeLLMAPI en sus puertos habituales
            try:
                r = _post(alt, p, cuerpo)
            except requests.ConnectionError:
                continue
            from .config import guardar_ajustes
            guardar_ajustes({"freellmapi_url": alt})
            log(f"FreeLLMAPI encontrado en {alt} (guardado en Ajustes).")
            break
        if r is None:
            raise RuntimeError(f"no se pudo conectar con {base}. ¿Está abierto FreeLLMAPI? Copia en Ajustes la dirección "
                               "que muestra su página Agentes (ej. http://127.0.0.1:31415).") from e
    if r.status_code == 400 and modo_json and "response_format" in r.text:
        cuerpo.pop("response_format", None)                    # el proveedor no acepta modo JSON: sin él
        r = _post(base, p, cuerpo)
    if r.status_code != 200:
        msg = None
        try:
            e = r.json()
            e = e[0] if isinstance(e, list) and e else e
            err = e.get("error") if isinstance(e, dict) else None
            msg = err.get("message") if isinstance(err, dict) else (err or (e.get("message") if isinstance(e, dict) else None))
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"error {r.status_code}: {str(msg or r.text)[:240]}")
    d = r.json()
    ch = (d.get("choices") or [{}])[0]
    return (ch.get("message") or {}).get("content") or "", ch.get("finish_reason") or ""


SIGUE = "Continúa exactamente donde te quedaste. No repitas nada, no saludes y no expliques: solo sigue el texto."


def _compatible_openai(p: str, prompt: str, system: str, max_tokens: int, modelo: str, modo_json: bool = False,
                       historial: list | None = None) -> str:
    """Si la respuesta se corta por largo, le pide a la IA que continúe (hasta 3 veces) y une las partes."""
    msgs = ([{"role": "system", "content": system}] if system else []) + list(historial or []) + [{"role": "user", "content": prompt}]
    texto, fin = _una_llamada(p, msgs, max_tokens, modelo, modo_json)
    if not texto.strip() and fin == "length":           # el modelo gastó todo "pensando": más margen
        texto, fin = _una_llamada(p, msgs, max_tokens * 3, modelo, modo_json)
    if modo_json:
        if fin == "length":                              # un JSON cortado no sirve: se pide de nuevo con más espacio
            texto, fin = _una_llamada(p, msgs, max_tokens * 2, modelo, modo_json)
    else:
        total, vueltas = texto, 0
        while fin == "length" and vueltas < 3 and texto.strip():
            msgs = msgs + [{"role": "assistant", "content": texto}, {"role": "user", "content": SIGUE}]
            texto, fin = _una_llamada(p, msgs, max_tokens, modelo, False)
            total += texto
            vueltas += 1
        texto = total
    if not texto.strip():
        raise RuntimeError("respondió vacío")
    return texto.strip()


def _llamar(p: str, prompt: str, system: str, max_tokens: int, modo_json: bool = False, historial: list | None = None) -> str:
    aj = ajustes()
    modelo = aj.get(PROVEEDORES[p]["modelo"]) or ""
    if p == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=clave("ANTHROPIC_API_KEY"))
        kw = {"model": modelo, "max_tokens": max_tokens, "messages": list(historial or []) + [{"role": "user", "content": prompt}]}
        if system:
            kw["system"] = system
        total = ""
        for _ in range(4):
            msg = client.messages.create(**kw)
            parte = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            total += parte
            if msg.stop_reason != "max_tokens" or modo_json or not parte.strip():
                break
            kw["messages"] = kw["messages"] + [{"role": "assistant", "content": parte}, {"role": "user", "content": SIGUE}]
        return total.strip()
    try:
        return _compatible_openai(p, prompt, system, max_tokens, modelo, modo_json, historial)
    except RuntimeError as e:
        respaldo = PROVEEDORES[p].get("respaldo")
        txt = str(e).lower()
        if respaldo and respaldo != modelo and ("404" in txt or "not found" in txt or ("400" in txt and "model" in txt)):
            return _compatible_openai(p, prompt, system, max_tokens, respaldo, modo_json, historial)  # el modelo cambió de nombre
        raise


def ask_text(prompt: str, system: str = "", max_tokens: int = 1500, modo_json: bool = False, historial: list | None = None) -> str:
    candidatos = configurados()
    if not candidatos:
        raise RuntimeError("No hay ninguna clave de IA. Agrega Gemini (gratis) en Ajustes.")
    errores = []
    for p in candidatos:
        try:
            # Gemini "piensa" antes de responder y eso consume tokens: se le da más margen
            texto = _llamar(p, prompt, system, max_tokens * 3 if p == "gemini" else max_tokens, modo_json, historial)
            if modo_json:
                extract_json(texto)          # si no es JSON válido, prueba con el siguiente proveedor
            ultimo.update(proveedor=p, errores=errores)
            if errores:
                log(f"IA: respondió {nombre(p)} tras fallar " + "; ".join(errores), "WARN")
            return texto
        except Exception as e:  # noqa: BLE001
            errores.append(f"{nombre(p)}: {e}")
    ultimo.update(proveedor=None, errores=errores)
    raise RuntimeError("Ningún proveedor de IA respondió. " + " | ".join(errores))


def ask_json(prompt: str, max_tokens: int = 3000) -> dict:
    return extract_json(ask_text(prompt + "\nResponde SOLO con un objeto JSON válido, sin texto antes ni después y sin ```.",
                                 max_tokens=max_tokens, modo_json=True))


def probar() -> list:
    """Prueba cada proveedor configurado por separado."""
    out = []
    for p in ORDEN_DEFECTO:
        if not clave(PROVEEDORES[p]["clave"]):
            out.append({"id": p, "nombre": nombre(p), "ok": None, "mensaje": "sin clave"})
            continue
        try:
            t = _llamar(p, "Responde solo con: OK, funciono.", "", 400 if p == "gemini" else 30)
            out.append({"id": p, "nombre": nombre(p), "ok": True, "mensaje": t[:80]})
        except Exception as e:  # noqa: BLE001
            out.append({"id": p, "nombre": nombre(p), "ok": False, "mensaje": str(e)[:200]})
    return out


def estado() -> dict:
    return {"activo": proveedor(), "activo_nombre": nombre(proveedor()), "configurados": configurados(),
            "modo": ajustes().get("ia_proveedor") or "auto",
            "proveedores": [{"id": p, "nombre": v["nombre"], "gratis": v["gratis"], "clave": v["clave"],
                             "configurado": bool(clave(v["clave"]))} for p, v in PROVEEDORES.items()]}
