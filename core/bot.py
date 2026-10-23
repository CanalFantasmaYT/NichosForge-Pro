"""Nichi: estratega experto en monetización de YouTube con canales automatizados.

Cómo piensa:
  1. NichosForge calcula antes un análisis (core/cerebro.py): índice de oportunidad por nicho, ranking de canales para
     replicar, fase del usuario y crecimiento real medido.
  2. La IA recibe ese análisis + lo que hay abierto en el panel + la conversación + la metodología Aprende a Monetizar,
     razona con un marco de decisión y ELIGE (no se queda en "depende").
  3. Puede proponer acciones que el panel convierte en botones: [[buscar:…]], [[investigar:…]], [[canal:…]],
     [[guardar:…]], [[seguir:…]], [[ir:…]].
Sin IA, responde con el mismo análisis (cerebro.respuesta_sin_ia) o con la guía de la metodología.
"""
import json

from . import academia, cerebro, llm

SISTEMA = """Eres **Nichi**, estratega senior de monetización de YouTube especializado en canales AUTOMATIZADOS (sin rostro:
narración, IA, stock) que replican en español lo que ya funciona en inglés. Trabajas dentro de NichosForge Pro y aplicas
la metodología «Aprende a Monetizar» (abajo) junto con tu experiencia del ecosistema de YouTube.

## Cómo piensas (hazlo internamente antes de escribir)
1. **Objetivo real**: qué decisión necesita tomar el usuario y en qué fase está (te la doy en los datos).
2. **Evidencia**: revisa el análisis de NichosForge (índice de oportunidad por nicho, ranking de canales, crecimiento
   real medido, patrones) y lo que tiene abierto. Prefiere datos MEDIDOS («real») sobre estimados.
3. **Opciones**: considera 2 o 3 alternativas concretas.
4. **Criterios** para comparar: demanda (visitas/mes), viralidad (outliers), monetización (CPM/RPM del nicho y país),
   facilidad de producirlo automatizado (sin rostro, edición simple, audiencia mayor), competencia en español,
   validación (≥5 referentes en inglés de ≤1 año con ~1M visitas/mes), si el «sin rostro» está VERIFICADO en imágenes
   (campo rostro: sin_rostro / con_rostro / dudoso; un canal con_rostro NO es replicable como automatizado),
   si está MONETIZADO (campo monetizado: veredicto si/no/probable/aun_no y su confianza; solo «confirmado» es 100 % seguro), evergreen vs. trendy, riesgo de políticas y
   tiempo hasta monetizar (1.000 suscriptores + 4.000 horas de reproducción pública en 12 meses).
5. **Decide**: elige UNA opción y defiéndela con números. Si los datos no alcanzan, dilo, elige lo más probable y
   propone la acción exacta para confirmarlo.
6. **Plan**: pasos concretos para esta semana, adaptados a su fase (Fase 1 sin dinero → Fase 4 automatización total).

## Lo que sabes como experto (úsalo cuando aplique)
- Ingresos = visitas × RPM. El RPM sube con nichos de CPM alto (finanzas, negocios, tecnología, salud, lujo), audiencias
  de EE. UU./Canadá/Europa, audiencias mayores, videos de 8+ min (mid-rolls) y en el 4.º trimestre (oct-dic); baja en enero.
- Riesgo de desmonetización: el «contenido no original / inauténtico» (resubir, recopilar o leer textos sin aportar,
  plantillas repetidas casi iguales) y los derechos de autor. Replicar = tomar la IDEA validada y crear un guion, voz y
  montaje propios; nunca resubir material ajeno. El contenido realista hecho con IA debe declararse en YouTube Studio.
- El 70 % del tráfico viene de Inicio y Sugeridos: manda la combinación título + miniatura (CTR) y la retención
  (gancho fuerte en los primeros 30 s). Las pruebas A/B de miniaturas de YouTube ayudan a elegir.
- Consistencia: banco de 15 videos antes de publicar, 1 video diario o al menos 3-4 por semana al inicio.
- Escalar = varios canales del mismo sistema; cada canal con su Gmail, branding y nicho claro. Las pistas de audio en otros
  idiomas pueden multiplicar el alcance de un video que ya funciona.
- Sé honesto con las estimaciones: las cifras sin «real» son aproximadas.

## Cómo respondes
- Español neutro, cercano y directo; tutea. Nada de relleno ni repetir la pregunta.
- **Empieza con la decisión o la respuesta en una frase en negrita.**
- Luego, según haga falta: «#### Por qué» (3-5 viñetas con números de los datos), «#### Plan» (pasos numerados, máx. 6),
  «#### Ojo con» (riesgos, solo si importan). Máximo ~220 palabras salvo que pidan más detalle.
- Al final, si aporta, añade hasta 3 acciones con esta sintaxis exacta (el panel las convierte en botones):
  [[buscar:frase en inglés]] [[investigar:tema]] [[canal:Nombre exacto del canal]] [[guardar:Nombre exacto]]
  [[seguir:Nombre exacto]] [[ir:inicio|micanal|seguimiento|investigacion|explorar|guardados|academia|ajustes]]
- Después de las acciones, una sección «### Cómo lo decidí» con 2-4 líneas de tu razonamiento (criterios y por qué
  descartaste las alternativas). El panel la muestra plegada.
- Nunca inventes datos que no estén en el contexto. Usa los nombres de canales y nichos tal como aparecen.

## Metodología «Aprende a Monetizar»
""" + academia.conocimiento_texto()

PANEL = [
    (("mapa", "competencia directa", "competencia indirecta", "mi competencia"), "🎯 En «Mapa de mi canal» pones tu canal y te muestro tres grupos: "
     "referentes en inglés (mismo nicho, ya validados), competencia directa (mismo nicho en español) y competencia indirecta (nichos vecinos o temas "
     "que se cruzan con los tuyos), además de los temas que funcionan en inglés y aún no tocas."),
    (("rpm más alto", "rpm mas alto", "nicho que más paga", "nicho que mas paga", "mejor pagado"), "💵 En Oportunidad → «Nichos con RPM más alto» ves "
     "cuánto gana el creador por cada 1.000 visitas en cada nicho, con el RPM real de los canales que ya analicé."),
    (("monetizado", "monetizada", "monetizacion activa", "socio", "ypp"), "💰 En la ficha de cada canal verás «¿Está monetizado?». Digo «confirmado» solo con "
     "una prueba segura: el botón «Unirse» o «Super Thanks» (solo existen en canales del Programa de Socios) o menos de 1.000 suscriptores (no puede "
     "ganar con anuncios). Si no, te digo si cumple los requisitos (1.000 suscriptores + 4.000 horas, o 10 M visitas en Shorts) y con qué confianza. "
     "Nadie fuera de YouTube Studio puede saberlo al 100 % en todos los casos."),
    (("alerta", "avisame", "avísame", "notifica"), "🔔 Cada día reviso tus canales (los tuyos, los guardados ☆ y los que sigues 👁) y tus nichos seguidos. "
     "Te aviso cuando sale un outlier nuevo (un video que va varias veces más rápido que lo normal en su canal) o cuando un canal joven explota. "
     "Mira la campana de arriba; en Ajustes cambias el umbral y la frecuencia."),
    (("índice de oportunidad", "indice de oportunidad", "oportunidad"), "🏆 El índice de oportunidad (0-100) combina demanda en inglés, competencia en español, "
     "RPM del nicho, canales jóvenes que crecen y la tendencia (subiendo o bajando). Puedes cambiar el peso de cada criterio y seguir un nicho con 🔔."),
    (("patrón de miniatura", "patrones de miniatura", "patron de miniatura", "por miniatura", "radar"), "En 🎨 Miniaturas analizo en tu PC el diseño de cada miniatura (cara y su posición, texto y su color, colores, "
     "flechas o círculos rojos, pantalla dividida), agrupo las que se parecen y mido cuál rinde más AHORA con el radar de tendencias. "
     "Toca una miniatura para ver las parecidas y los canales que usan ese estilo, o pulsa «🌐 Buscar canales así»."),
    (("rostro", "cara", "a cámara", "a camara", "sin rostro"), "Para confirmar si un canal es **sin rostro** miro, en tu PC y sin API, la miniatura y 3 fotogramas de dentro de sus "
     "últimos videos. Detecto caras con YuNet y, con el reconocedor SFace, compruebo si es **la misma persona** en muchos videos: si lo es y sale "
     "en la mayoría de los fotogramas, hay un creador a cámara. Si las caras cambian (celebridades, personajes del tema) o casi no hay caras, "
     "el canal es sin rostro. Verás «✅ Sin rostro (verificado)», «🙂 Con rostro» o «❓ Dudoso» en la ficha de cada canal."),
    (("seguimiento", "visitas reales", "medid"), "En 📈 Seguimiento mido las visitas de verdad: cada 6 h tomo una foto de las visitas, suscriptores y videos "
     "de tus canales, los guardados (☆) y los que sigues (👁). Con eso calculo lo ganado en 24 h, 7 y 30 días y el crecimiento semanal, "
     "y reemplazo las visitas estimadas por las reales en todo el programa (verás la etiqueta «real»). Cuesta 1 unidad de cuota por cada 50 canales."),
    (("investigaci", "sorpréndeme", "sorprendeme", "investigar"), "En 🔭 Investigación reviso cientos de videos LARGOS (sin Shorts) de tendencias y búsquedas amplias "
     "con categorías, países y fechas al azar —sin depender de nichos—, detecto qué canales son automatizados (sin rostro) y le pongo un nicho a cada video. "
     "Toca la etiqueta 🏷 de un video para corregir el nicho: lo aprendo. Guarda videos y canales con ☆."),
    (("disfraz", "skin", "halloween", "navidad", "ninja"), "Soy Nichi ninja 🥷. Me disfrazo según el calendario de EE. UU.: Año Nuevo, San Valentín, San Patricio, Pascua, "
     "Día de las Madres, 4 de Julio, Halloween (¡fantasma! 👻), Acción de Gracias y Navidad. Cámbialo con 🎨 en el chat o en Ajustes."),
    (("varias claves", "otra clave", "claves de youtube", "rotar"), "En Ajustes → Claves de YouTube puedes agregar varias. Cada una tiene 10.000 unidades al día; "
     "cuando una se agota sigo con la siguiente sin detener la búsqueda."),
    (("outlier", "viral", "x su canal", "x mediana"), "Un outlier es un video con muchas más visitas que la mediana de su canal (por ejemplo, 10x). "
     "Señala que el TEMA funcionó: es el mejor candidato para los pasos 2 y 3 de la metodología (filtrar virales y sacar guiones)."),
    (("cuota", "unidades"), "La API de YouTube da 10.000 unidades gratis al día por clave. Cada búsqueda gasta 100 y cada canal analizado unas 2. "
     "Todo queda en caché 24 h, así que repetir una búsqueda no gasta."),
    (("color", "verde", "rojo", "amarillo", "naranja", "morado"), "Cambio de color según lo que miras: 💚 verde = rentable, 💠 turquesa = prometedor, "
     "🟡 ámbar = dudoso, ❤️ rojo = peligroso (temas que espantan anunciantes) y 💜 morado = estoy pensando. Pasa el mouse por un canal y lo verás."),
]

AYUDA = ("Puedo ayudarte a **elegir nicho**, decidir **qué canal replicar**, armar tu **plan según tu fase** o explicarte cualquier parte de "
         "Aprende a Monetizar. Con una clave gratis de Gemini en Ajustes además razono a fondo con todos tus datos.")


def responder(pregunta: str, contexto: dict | None = None, historial: list | None = None) -> dict:
    q = (pregunta or "").strip()
    if not q:
        return {"texto": AYUDA, "ia": False}
    try:
        experto = cerebro.contexto_experto()
    except Exception as e:  # noqa: BLE001
        experto = {"error": str(e)}
    canales_ref = [{"id": c["id"], "canal": c["canal"]} for c in experto.get("canales_para_replicar", [])]
    if llm.disponible():
        hist = [{"role": m["role"], "content": str(m["content"])[:2500]} for m in (historial or [])[-8:]
                if m.get("role") in ("user", "assistant") and m.get("content")]
        datos = json.dumps({"analisis_nichosforge": experto, "panel": contexto or {}}, ensure_ascii=False, default=str)[:24000]
        prompt = f"DATOS (análisis de NichosForge y lo que el usuario tiene abierto):\n{datos}\n\nPREGUNTA DEL USUARIO: {q}"
        try:
            texto = llm.ask_text(prompt, SISTEMA, 2600, historial=hist)
            return {"texto": texto, "ia": True, "proveedor": llm.nombre(llm.ultimo.get("proveedor")), "canales": canales_ref}
        except Exception as e:  # noqa: BLE001
            return {"texto": f"No pude usar la IA ({str(e)[:160]}).\n\n" + _guia(q, contexto), "ia": False, "canales": canales_ref}
    return {"texto": _guia(q, contexto), "ia": False, "canales": canales_ref}


def _guia(q: str, contexto: dict | None) -> str:
    ql = q.lower()
    for claves, texto in PANEL:
        if any(c in ql for c in claves):
            return texto
    try:
        r = cerebro.respuesta_sin_ia(q)
        if r:
            return r
    except Exception:  # noqa: BLE001
        pass
    r = academia.responder_guia(q)
    return r or AYUDA
