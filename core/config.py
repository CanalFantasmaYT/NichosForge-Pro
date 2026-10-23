"""Configuración de NichosForge Pro.

Todo lo que se edita desde el panel vive en datos/ajustes.json (se crea solo).
Las claves de API se leen del .env igual que en VideoForge (se releen en cada llamada).
"""
import copy
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from .utils import read_json, write_json

BASE = Path(__file__).resolve().parent.parent
DATOS = BASE / "datos"
DATOS.mkdir(exist_ok=True)
load_dotenv(BASE / ".env")
AJUSTES = DATOS / "ajustes.json"
PUERTO = 8767  # VideoForge 8765 · NichosForge 8766 · NichosForge Pro 8767

CATEGORIAS = {"1": "Cine y animación", "2": "Autos y vehículos", "10": "Música", "15": "Mascotas y animales",
              "17": "Deportes", "19": "Viajes y eventos", "20": "Videojuegos", "22": "Personas y blogs", "23": "Comedia",
              "24": "Entretenimiento", "25": "Noticias y política", "26": "Consejos y estilo", "27": "Educación",
              "28": "Ciencia y tecnología", "29": "ONG y activismo"}

# CPM orientativo (USD que paga el anunciante por 1000 impresiones) para audiencia de EE. UU.
CPM_DEFECTO = {"1": 6.0, "2": 11.0, "10": 3.0, "15": 6.0, "17": 6.5, "19": 8.0, "20": 4.5, "22": 6.5, "23": 5.0,
               "24": 6.0, "25": 8.0, "26": 9.0, "27": 12.0, "28": 12.0, "29": 6.0}

# Cuánto vale la audiencia de cada país frente a EE. UU. (1.0)
FACTOR_PAIS = {"US": 1.0, "CA": 0.85, "AU": 0.85, "GB": 0.8, "NZ": 0.75, "DE": 0.75, "CH": 0.85, "NO": 0.8, "DK": 0.75,
               "SE": 0.7, "NL": 0.7, "FR": 0.6, "IE": 0.75, "JP": 0.6, "ES": 0.4, "IT": 0.45, "PT": 0.35, "MX": 0.25,
               "CL": 0.25, "AR": 0.2, "CO": 0.2, "PE": 0.2, "EC": 0.2, "VE": 0.1, "BR": 0.25, "IN": 0.1, "PH": 0.1}

# CPM orientativo por NICHO (USD, audiencia EE. UU.). Tiene prioridad sobre el de la categoría de YouTube.
CPM_NICHO = {
    "Negocios y marcas": 15.0, "Tecnología e IA": 12.0, "Old money y lujo": 11.0, "Autos, camiones y máquinas": 11.0,
    "Salud y cuerpo humano": 10.5, "Ciencia y espacio": 10.0, "Ingeniería y megaproyectos": 10.0, "Estafas y fraudes": 9.0,
    "Militar y aviación": 9.0, "Psicología y estoicismo": 9.0, "Historia antigua y medieval": 8.0, "Guerras e historia moderna": 8.0,
    "Geografía y países": 8.0, "Historias para adultos mayores": 7.5, "Lugares abandonados y arquitectura": 7.0, "Comida y cocina": 7.0,
    "Crimen real": 7.0, "Misterios sin resolver": 6.5, "Supervivencia y aventura": 6.5, "Deportes y leyendas": 6.5,
    "Curiosidades y datos": 6.5, "Celebridades y Hollywood": 6.0, "Animales y naturaleza": 6.0, "Mitología y religión": 6.0,
    "Desastres y accidentes": 6.0, "Historias de venganza y drama familiar": 5.5, "Terror y paranormal": 5.0,
    "Historias de Reddit narradas": 4.5,
}

AJUSTES_DEFECTO = {
    "nombre": "",                 # cómo te saluda el panel
    "mi_canal": "",               # @handle, link o ID de tu canal
    "cpm_categoria": CPM_DEFECTO,
    "cpm_nicho": CPM_NICHO,
    "temporada": True,            # el CPM sube en oct-dic (navidad) y baja en enero-febrero
    "factor_audiencia": {"mayores": 1.15, "general": 1.0, "jovenes": 0.8},
    "factor_pais": FACTOR_PAIS,
    "factor_idioma": {"en": 0.9, "es": 0.3, "otro": 0.4},   # si el canal no declara país
    "reparto_youtube": 0.55,      # parte del CPM que recibe el creador
    "vistas_monetizadas": 0.65,   # porción de visitas que muestran anuncio
    "factor_shorts": 0.06,        # los Shorts pagan muchísimo menos
    "bonus_largos": 1.2,          # videos de 8+ min permiten mid-rolls
    # Criterios de la metodología para marcar referentes
    "edad_max_canal_dias": 365,
    "visitas_mes_min": 1000000,
    "minutos_video_largo": 8,
    "videos_por_canal": 30,
    "cache_horas": 24,
    "seguimiento_dias": 35,
    "verificar_rostros": True,
    "leer_paginas_youtube": False,  # leer la página pública del canal para CONFIRMAR monetización (botón Unirse / Super Thanks).
                                    # Apagado por defecto: los términos de YouTube restringen el acceso automatizado a sus páginas.
    "radar_miniaturas_auto": True,
    "alertas": True,                # revisa cada día tus canales y nichos seguidos
    "alertas_nichos": True,         # también busca canales jóvenes en tus nichos seguidos (~102 unidades por nicho)
    "alertas_cada_horas": 24,
    "alerta_outlier_x": 3,          # un video nuevo es outlier si va 3x más rápido que lo normal en su canal  # cada 6 h lee las tendencias para saber qué miniaturas funcionan ahora (~40 unidades)
    "radar_mercado": "ambos",       # en | es | ambos    # mira miniaturas y fotogramas en tu PC para confirmar "sin rostro" (gratis, sin API)       # días de fotos guardadas para medir visitas reales (política de YouTube: ~30)
    # IA opcional (mascota Nichi, frases en inglés y subnichos)
    "ia_proveedor": "auto",       # auto | gemini | freellmapi | groq | claude | openai
    "ia_orden": "gemini,freellmapi,groq,claude,openai",   # orden de respaldo en modo auto
    "ia_modelo_gemini": "gemini-flash-latest",
    "ia_modelo_groq": "llama-3.3-70b-versatile",
    "ia_modelo_freellmapi": "auto",
    "freellmapi_url": "http://127.0.0.1:31415/v1",
    "ia_modelo_claude": "claude-sonnet-5-5",
    # Interfaz y Nichi
    "tema": "claro",              # claro | oscuro
    "nichi_skin": "auto",         # auto (según el calendario de EE. UU.) | ninja | fantasma | navidad | ...
    "nichi_datos": True,          # Nichi suelta datos y consejos solo
    # Investigación (buscador de videos de canales automatizados)
    "inv_vistas_min": 10000,
    "inv_solo_automatizados": True,
    "ia_modelo_openai": "gpt-4o-mini",
}


def ajustes() -> dict:
    a = copy.deepcopy(AJUSTES_DEFECTO)
    guardado = read_json(AJUSTES, {}) or {}
    for k, v in guardado.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            a[k].update(v)
        else:
            a[k] = v
    return a


def guardar_ajustes(cambios: dict) -> dict:
    a = ajustes()
    for k, v in cambios.items():
        if k not in AJUSTES_DEFECTO:
            continue
        defecto = AJUSTES_DEFECTO[k]
        if isinstance(defecto, dict):
            a[k] = {str(kk): float(vv) for kk, vv in (v or {}).items() if str(vv).strip() != ""}
        elif isinstance(defecto, bool):
            a[k] = bool(v)
        elif isinstance(defecto, (int, float)):
            a[k] = type(defecto)(float(v or 0))
        else:
            a[k] = str(v or "").strip()
    write_json(AJUSTES, a)
    return a


# ---------- claves de API (igual que VideoForge) ----------

def archivos_env() -> list:
    return [BASE / ".env", BASE / ".env.txt", BASE / "env.txt", BASE.parent / ".env", BASE.parent / ".env.txt"]


def _limpiar(v) -> str:
    return str(v or "").strip().strip('"').strip("'").strip()


def buscar_clave(nombre: str):
    for f in archivos_env():
        if f.is_file():
            try:
                vals = dotenv_values(f, encoding="utf-8-sig")
            except Exception:  # noqa: BLE001
                continue
            v = _limpiar(vals.get(nombre))
            if v:
                return v, f.name if f.parent == BASE else f"../{f.name}"
    v = _limpiar(os.getenv(nombre))
    return (v, "variable de entorno") if v else ("", None)


def clave(nombre: str) -> str:
    return buscar_clave(nombre)[0]


def guardar_clave(nombre: str, valor: str):
    f = BASE / ".env"
    lineas = f.read_text(encoding="utf-8-sig").splitlines() if f.exists() else []
    nueva = f"{nombre}={valor.strip()}"
    for i, l in enumerate(lineas):
        if l.split("=", 1)[0].strip() == nombre:
            lineas[i] = nueva
            break
    else:
        lineas.append(nueva)
    f.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.environ[nombre] = valor.strip()


# ---------- varias claves de YouTube (si una se queda sin cuota, sigue la otra) ----------

def _valores_env() -> dict:
    vals = {}
    for f in archivos_env():
        if f.is_file():
            try:
                for k, v in dotenv_values(f, encoding="utf-8-sig").items():
                    if k not in vals and _limpiar(v):
                        vals[k] = _limpiar(v)
            except Exception:  # noqa: BLE001
                continue
    return vals


def claves_youtube() -> list:
    """YOUTUBE_API_KEY, YOUTUBE_API_KEY_2 … _20 y YOUTUBE_API_KEYS (separadas por coma), sin repetir."""
    vals = _valores_env()
    out = []
    for nombre in ["YOUTUBE_API_KEY"] + [f"YOUTUBE_API_KEY_{i}" for i in range(2, 21)]:
        v = vals.get(nombre) or _limpiar(os.getenv(nombre))
        if v:
            out.append(v)
    extra = vals.get("YOUTUBE_API_KEYS") or _limpiar(os.getenv("YOUTUBE_API_KEYS"))
    out += [x.strip() for x in (extra or "").split(",") if x.strip()]
    return list(dict.fromkeys(out))


def guardar_claves_youtube(lista: list):
    """Reescribe en .env YOUTUBE_API_KEY, YOUTUBE_API_KEY_2, … con la lista dada."""
    lista = list(dict.fromkeys(x.strip() for x in lista if x and x.strip()))
    f = BASE / ".env"
    lineas = f.read_text(encoding="utf-8-sig").splitlines() if f.exists() else []
    nombres = {"YOUTUBE_API_KEYS", "YOUTUBE_API_KEY"} | {f"YOUTUBE_API_KEY_{i}" for i in range(2, 21)}
    lineas = [l for l in lineas if l.split("=", 1)[0].strip() not in nombres]
    for i, v in enumerate(lista):
        nombre = "YOUTUBE_API_KEY" if i == 0 else f"YOUTUBE_API_KEY_{i + 1}"
        lineas.append(f"{nombre}={v}")
        os.environ[nombre] = v
    for nombre in nombres:
        if nombre != "YOUTUBE_API_KEY" and nombre not in [("YOUTUBE_API_KEY" if i == 0 else f"YOUTUBE_API_KEY_{i + 1}") for i in range(len(lista))]:
            os.environ.pop(nombre, None)
    if not lista:
        os.environ.pop("YOUTUBE_API_KEY", None)
    f.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def load_global() -> dict:
    """Compatibilidad con core/youtube.py (usa cache_horas)."""
    return {"cache_horas": ajustes()["cache_horas"]}
