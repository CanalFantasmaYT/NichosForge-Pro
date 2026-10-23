"""El "cerebro" de Nichi: análisis previo para que razone y ELIJA con datos.

Antes de cada respuesta, NichosForge arma:
  • una tabla de nichos con un Índice de Oportunidad (demanda, viralidad, monetización, facilidad de producción,
    competencia en español, validación con referentes jóvenes, crecimiento real y riesgo);
  • un ranking de canales para replicar;
  • la fase del usuario (según lo que ganan sus canales) y su siguiente meta.
La IA recibe todo esto y lo usa para decidir. Sin IA, Nichi responde con este mismo análisis.
"""
import math
import re
import statistics
from collections import Counter, defaultdict

from .config import ajustes
from .utils import read_json_cache

FASES = [
    (0, "Fase 1 · Sin ingresos", "Guiones con IA, tú haces miniaturas, narras y editas. Meta: monetizar (1.000 suscriptores + 4.000 horas)."),
    (1, "Fase 2 · Primeros ingresos", "Guiones con IA, voz con IA, sigues editando y haciendo miniaturas. Meta: $1.000 USD/mes."),
    (1000, "Fase 3 · Canal rentable", "Delegar la edición y sostener 1 video diario. Meta: $3.000 USD/mes y abrir el segundo canal."),
    (3000, "Fase 4 · Automatización total", "Escritor, diseñador y editor contratados; escalar a varios canales. Meta: $10.000 USD/mes."),
]


def _c(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _prom(xs, d=None):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else d


# ---------------- canales ----------------

def _todos_los_canales() -> list:
    from . import motor
    crudos = read_json_cache(motor.CANALES, {}) or {}
    mios = motor.ids_mis_canales()
    out = []
    for cid in crudos:
        if cid in mios:
            continue
        a = motor.canal(cid)
        if a:
            out.append(a)
    return out


def ranking_canales(n: int = 12, canales: list | None = None) -> list:
    """Los mejores canales para replicar, con puntaje y razones."""
    cs = canales if canales is not None else _todos_los_canales()
    filas = []
    for a in cs:
        rv = (a.get("rostro") or {}).get("veredicto")
        if a.get("riesgos") or rv == "con_rostro":
            continue
        vm = a.get("visitas_mes") or 0
        edad = a.get("edad_dias") or 9999
        p = (_c((math.log10(vm + 1) - 4) / 3) * 30 + (25 if edad <= 365 else 12 if edad <= 730 else 0)
             + {"automatizado": 20, "posible": 10}.get(a.get("auto_tipo"), 0) + (10 if a.get("es_referente") else 0)
             + _c((a.get("rpm") or 0) / 8) * 10 + (5 if a.get("real") and (a.get("crecimiento") or 0) > 0 else 0)
             + (8 if rv == "sin_rostro" else 0))
        razones = []
        crec = f" ({a['crecimiento']:+d}% semanal)" if a.get("crecimiento") is not None else ""
        if a.get("real"):
            razones.append(f"{_n(vm)} visitas/mes medidas en 30 días{crec}")
        elif a.get("medido"):
            razones.append(f"~{_n(vm)} visitas/mes (proyección de lo medido){crec}")
        else:
            razones.append(f"~{_n(vm)} visitas/mes (estimado)")
        if edad <= 365:
            razones.append(f"canal joven ({edad} días)")
        if rv == "sin_rostro":
            razones.append("sin rostro VERIFICADO en sus fotogramas")
        elif a.get("auto_tipo") == "automatizado":
            razones.append(f"automatizado ({a.get('auto_score')}%, aún sin verificar en imágenes)")
        if a.get("es_referente"):
            razones.append("cumple como referente")
        filas.append({"id": a["id"], "canal": a.get("canal"), "nicho": a.get("nicho") or a.get("categoria"), "idioma": a.get("idioma"),
                      "puntaje": round(p), "visitas_mes": vm, "real": bool(a.get("real")), "edad_dias": edad,
                      "tipo": a.get("auto_tipo"), "rpm": a.get("rpm"), "ganancia_mes": a.get("ingreso_mes"), "razones": razones})
    filas.sort(key=lambda x: -x["puntaje"])
    return filas[:n]


def _n(x) -> str:
    x = x or 0
    return f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}K" if x >= 1e3 else str(int(x))


# ---------------- nichos ----------------

PESOS = {"demanda": 25, "competencia": 20, "rpm": 20, "jovenes": 20, "tendencia": 15}
NOMBRES = {"demanda": "Demanda en inglés", "competencia": "Poca competencia en español", "rpm": "RPM del nicho",
           "jovenes": "Canales jóvenes que crecen", "tendencia": "Tendencia"}


def _videos_por_nicho(canales_por_id: dict) -> dict:
    """Videos con fecha y visitas/hora de investigaciones, búsquedas y el radar de miniaturas, agrupados por nicho."""
    from . import motor
    out = defaultdict(list)
    vistos = set()

    def agregar(v, nicho):
        if not nicho or nicho == "Sin clasificar" or v.get("id") in vistos or not v.get("vph"):
            return
        vistos.add(v.get("id"))
        out[nicho].append({"vph": v.get("vph") or 0, "dias": v.get("dias") or _dias_desde(v.get("publicado")), "outlier": v.get("outlier")})
    for r in (read_json_cache(motor.INVESTIGACIONES, []) or [])[:8]:
        for v in r.get("videos", []):
            agregar(v, v.get("nicho"))
    for b in (read_json_cache(motor.BUSQUEDAS, []) or [])[:15]:
        for v in b.get("virales", []):
            a = canales_por_id.get(v.get("canal_id")) or {}
            agregar(v, a.get("nicho"))
    try:
        from . import miniaturas
        for k, v in miniaturas.corpus().items():
            agregar({**v, "id": k}, v.get("nicho"))
    except Exception:  # noqa: BLE001
        pass
    return out


def _dias_desde(publicado):
    from datetime import datetime
    try:
        return max(1, (datetime.now() - datetime.fromisoformat(str(publicado)[:10])).days)
    except Exception:  # noqa: BLE001
        return 9999


def _tendencia(vids: list, ratio_global: float, crec_real: float | None) -> float | None:
    """% de subida/bajada: visitas/hora de los videos de ≤30 días frente a los de 31-180 días, comparado con el
    mismo cociente de todos los nichos, más el crecimiento real medido de sus canales."""
    rec = [v["vph"] for v in vids if v["dias"] <= 30]
    ant = [v["vph"] for v in vids if 30 < v["dias"] <= 180]
    partes = []
    if len(rec) >= 3 and len(ant) >= 3 and ratio_global:
        r = (statistics.median(rec) / (statistics.median(ant) or 1)) / ratio_global
        partes.append(max(-100, min(100, (r - 1) * 100)))
    if crec_real is not None:
        partes.append(max(-100, min(100, crec_real)))
    return round(statistics.mean(partes)) if partes else None


def tabla_nichos(n: int = 40) -> list:
    """Índice de oportunidad (0-100) por nicho con los 5 criterios. Cada componente va de 0 a 1."""
    from .analisis import CATEGORIAS  # noqa: F401
    aj = ajustes()
    cpm_nicho = aj.get("cpm_nicho") or {}
    reparto, monet = float(aj.get("reparto_youtube", .55)), float(aj.get("vistas_monetizadas", .65))
    canales = _todos_los_canales()
    por_id = {a["id"]: a for a in canales}
    por = defaultdict(list)
    for a in canales:
        if a.get("nicho"):
            por[a["nicho"]].append(a)
    vids = _videos_por_nicho(por_id)
    todos_rec = [v["vph"] for vs in vids.values() for v in vs if v["dias"] <= 30]
    todos_ant = [v["vph"] for vs in vids.values() for v in vs if 30 < v["dias"] <= 180]
    ratio_global = (statistics.median(todos_rec) / (statistics.median(todos_ant) or 1)) if len(todos_rec) >= 5 and len(todos_ant) >= 5 else None
    mes_min = int(aj["visitas_mes_min"])
    filas = []
    for nicho in set(por) | set(vids):
        cs, vs = por.get(nicho, []), vids.get(nicho, [])
        if len(cs) + len(vs) < 3:
            continue
        en = [a for a in cs if a.get("idioma") == "en"]
        es = [a for a in cs if a.get("idioma") == "es"]
        es_fuertes = [a for a in es if (a.get("visitas_mes") or 0) >= 100_000]
        vm_en = _prom([a.get("visitas_mes") for a in en]) if en else None
        demanda = _c((math.log10(vm_en + 1) - 4.5) / 2.5) if vm_en else (_c(math.log10(statistics.median([v["vph"] for v in vs]) + 1) / 4) * .6 if vs else 0)
        competencia = 1 - _c(len(es_fuertes) / 6)
        cpm = float(cpm_nicho.get(nicho) or _prom([a.get("cpm") for a in cs], 6.0))
        rpm = cpm * reparto * monet
        rpm_c = _c((rpm - 1.2) / 5)
        jovenes = [a for a in en if (a.get("edad_dias") or 9999) <= 365 and
                   ((a.get("visitas_mes") or 0) >= mes_min * .5 or (a.get("crecimiento") or 0) > 15)]
        jov_c = _c(len(jovenes) / 5)
        crec = _prom([a.get("crecimiento") for a in cs if a.get("crecimiento") is not None])
        tend = _tendencia(vs, ratio_global, crec)
        tend_c = .5 if tend is None else _c((tend + 50) / 100)
        riesgo = _prom([1 if a.get("riesgos") else 0 for a in cs], 0)
        comp = {"demanda": round(demanda, 3), "competencia": round(competencia, 3), "rpm": round(rpm_c, 3), "jovenes": round(jov_c, 3), "tendencia": round(tend_c, 3)}
        base = sum(comp[k] * w for k, w in PESOS.items()) / sum(PESOS.values())
        indice = round(100 * base * (1 - .6 * riesgo))
        muestras = len(cs) + len(vs) // 3
        filas.append({
            "nicho": nicho, "indice": indice, "componentes": comp, "riesgo": round(riesgo, 2),
            "confianza": "alta" if muestras >= 25 and en else "media" if muestras >= 10 else "baja",
            "datos": {"canales_en": len(en), "canales_es": len(es), "competidores_es": len(es_fuertes), "visitas_mes_en": round(vm_en) if vm_en else None,
                      "cpm": round(cpm, 2), "rpm": round(rpm, 2), "jovenes": len(jovenes), "tendencia": tend, "crecimiento_real": round(crec) if crec is not None else None,
                      "videos": len(vs)},
            "jovenes_top": [{"id": a["id"], "canal": a["canal"], "edad_dias": a.get("edad_dias"), "visitas_mes": a.get("visitas_mes")}
                            for a in sorted(jovenes, key=lambda x: -(x.get("visitas_mes") or 0))[:4]],
            "fuertes": [NOMBRES[k] for k in sorted(comp, key=lambda k: -comp[k])[:2] if comp[k] >= .6],
            "debiles": [NOMBRES[k] for k in sorted(comp, key=lambda k: comp[k])[:2] if comp[k] < .35]})
    filas.sort(key=lambda f: -f["indice"])
    return filas[:n]


# ---------------- usuario ----------------

def fase_usuario() -> dict:
    from . import motor
    mis = motor.mis_canales()
    if not mis:
        return {"fase": FASES[0][1], "consejo": FASES[0][2], "canales": 0, "ganancia_mes": 0}
    total = sum(c.get("ingreso_mes") or 0 for c in mis)
    monetizable = any((c.get("suscriptores") or 0) >= 1000 for c in mis)
    idx = 0 if not monetizable else 1
    for i, (umbral, _, _) in enumerate(FASES):
        if total >= umbral and (i <= 1 or monetizable):
            idx = max(idx, i)
    return {"fase": FASES[idx][1], "consejo": FASES[idx][2], "canales": len(mis), "ganancia_mes": total,
            "visitas_mes": sum(c.get("visitas_mes") or 0 for c in mis), "medido_real": any(c.get("real") for c in mis),
            "detalle": [{"canal": c["canal"], "suscriptores": c.get("suscriptores"), "visitas_mes": c.get("visitas_mes"),
                         "ganancia_mes_estimada": c.get("ingreso_mes"), "nicho": c.get("nicho"), "visitas_mes_real": bool(c.get("real"))} for c in mis]}


def contexto_experto() -> dict:
    """Todo lo que Nichi necesita para pensar como un estratega."""
    nichos = tabla_nichos(10)
    canales = ranking_canales(12)
    try:
        from . import seguimiento as seg
        crecen = []
        for cid, origen in seg.ids_seguidos().items():
            m = seg.metricas(cid)
            if m and m.get("d7"):
                from . import motor
                a = motor.canal_crudo(cid) or {}
                crecen.append({"canal": a.get("canal", cid), "origen": origen, "visitas_7d": m["d7"]["ganadas"], "crecimiento": m.get("crecimiento")})
        crecen.sort(key=lambda x: -(x["visitas_7d"] or 0))
    except Exception:  # noqa: BLE001
        crecen = []
    return {"fase_usuario": fase_usuario(), "nichos_por_oportunidad": nichos, "canales_para_replicar": canales,
            "seguimiento_real_top": crecen[:8],
            "nota": "Índice de oportunidad 0-100 calculado por NichosForge; 'confianza' depende de cuántos datos hay de ese nicho."}


# ---------------- modo experto sin IA ----------------

def respuesta_sin_ia(q: str) -> str | None:
    ql = q.lower()
    if re.search(r"nicho|elig|recomiend|empez|cu[aá]l (tema|camino)", ql):
        t = tabla_nichos(5)
        if not t:
            return ("**Aún no tengo datos suficientes para elegir.** Haz una 🔭 Investigación al azar y guarda los canales que te gusten: "
                    "con eso armo un índice de oportunidad por nicho. [[ir:investigacion]]")
        g = t[0]
        out = [f"**Te recomiendo «{g['nicho']}»** (índice de oportunidad {g['indice']}/100, confianza {g['confianza']}).", "", "#### Por qué"]
        d = g["datos"]
        out += [f"- {x}." for x in g["fuertes"]] or ["- Es el mejor balance entre demanda, RPM y competencia."]
        out += [f"- {d['canales_en']} canales en inglés, {d['jovenes']} jóvenes que crecen, {d['competidores_es']} competidores fuertes en español, RPM ~${d['rpm']}."]
        if d.get("tendencia") is not None:
            out += [f"- Tendencia: {'subiendo' if d['tendencia'] > 10 else 'bajando' if d['tendencia'] < -10 else 'estable'} ({d['tendencia']:+d}%)."]
        if g["debiles"]:
            out += ["", "#### Ojo con", *[f"- {x}: bajo." for x in g["debiles"]]]
        if len(t) > 1:
            out += ["", "#### Alternativas", *[f"- **{x['nicho']}** · {x['indice']}/100" for x in t[1:3]]]
        out += ["", f"[[buscar:{g['nicho']}]] [[ir:seguimiento]]"]
        return "\n".join(out)
    if re.search(r"replic|copi|referente|qu[eé] canal", ql):
        r = ranking_canales(5)
        if not r:
            return "Todavía no he analizado canales. Haz una investigación o una búsqueda y te digo cuál replicar. [[ir:investigacion]]"
        c = r[0]
        out = [f"**Replica primero «{c['canal']}»** (puntaje {c['puntaje']}/100).", "", "#### Por qué", *[f"- {x[0].upper() + x[1:]}." for x in c["razones"]],
               "", "#### Plan", "1. Abre sus videos más vistos y filtra los outliers.", "2. Saca 15 guiones y adáptalos al español.",
               "3. Graba, edita y ten un banco de 15 videos antes de publicar.", "", f"[[canal:{c['canal']}]] [[guardar:{c['canal']}]]"]
        return "\n".join(out)
    if re.search(r"plan|fase|siguiente paso|qu[eé] hago|meta", ql):
        f = fase_usuario()
        return (f"**Estás en {f['fase']}.**\n\n{f['consejo']}\n\n#### Esta semana\n1. Elige o confirma tu nicho con el índice de oportunidad.\n"
                "2. Guarda 5 referentes y síguelos en 📈 Seguimiento.\n3. Prepara 15 guiones antes de publicar.\n\n[[ir:seguimiento]] [[ir:investigacion]]")
    return None


# ---------------- 💵 nichos con RPM más alto ----------------

def rpm_nichos() -> list:
    """RPM ESTIMADO por nicho: mediana del RPM estimado de los canales analizados (CPM del nicho × país, audiencia y duración) o, si aún no hay
    canales, el de la tabla de CPM con un canal típico (EE. UU., videos largos)."""
    from . import clasificador as clf
    aj = ajustes()
    cpm_nicho = aj.get("cpm_nicho") or {}
    reparto, monet = float(aj.get("reparto_youtube", .55)), float(aj.get("vistas_monetizadas", .65))
    canales = _todos_los_canales()
    por = defaultdict(list)
    for a in canales:
        if a.get("nicho") and a.get("rpm"):
            por[a["nicho"]].append(a)
    filas = []
    for nicho in sorted(set(cpm_nicho) | set(por)):
        cs = por.get(nicho, [])
        en = [a for a in cs if a.get("idioma") == "en"] or cs
        cpm = float(cpm_nicho.get(nicho) or _prom([a.get("cpm") for a in cs], 6.0))
        base = cpm * reparto * monet * 1.25                     # canal típico de EE. UU. con videos de 10-15 min
        if len(en) >= 2:
            rpms = sorted(a["rpm"] for a in en)
            rpm, bajo, alto, fuente = statistics.median(rpms), rpms[0], rpms[-1], f"estimado con {len(en)} canales"
        elif en:
            rpm, bajo, alto, fuente = en[0]["rpm"], en[0].get("rpm_bajo", en[0]["rpm"] * .7), en[0].get("rpm_alto", en[0]["rpm"] * 1.3), "estimado con 1 canal"
        else:
            rpm, bajo, alto, fuente = base, base * .7, base * 1.3, "tabla de CPM"
        vm = _prom([a.get("visitas_mes") for a in en])
        mejores = sorted(en, key=lambda a: -(a.get("ingreso_mes") or 0))[:3]
        filas.append({"nicho": nicho, "rpm": round(rpm, 2), "rpm_bajo": round(bajo, 2), "rpm_alto": round(alto, 2), "cpm": round(cpm, 2),
                      "por_millon": round(rpm * 1000), "fuente": fuente, "con_canales": bool(en), "estimado": True, "canales": len(cs), "visitas_mes_prom": round(vm) if vm else None,
                      "ingreso_mes_prom": round(_prom([a.get("ingreso_mes") for a in en]) or 0),
                      "ejemplos": [{"id": a["id"], "canal": a["canal"], "rpm": a["rpm"], "ingreso_mes": a.get("ingreso_mes")} for a in mejores],
                      "aprendido": nicho not in clf.TAX})
    filas.sort(key=lambda f: -f["rpm"])
    return filas
