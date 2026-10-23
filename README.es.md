<div align="center">

<img src="docs/img/logo.png" width="120" alt="Nichi, la mascota ninja">

# NichosForge Pro

**Encuentra, valida y sigue nichos rentables para canales de YouTube automatizados (sin rostro), con datos reales y un estratega con IA.**

[English](README.md) · [Guía de uso (PDF)](docs/Guia_de_uso_NichosForge_Pro.pdf) · [Cambios](CHANGELOG.md)

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Plataforma](https://img.shields.io/badge/plataforma-Windows%20%7C%20macOS%20%7C%20Linux-informational)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)
![Local](https://img.shields.io/badge/funciona-100%25%20en%20tu%20PC-success)

<img src="docs/img/inicio.jpg" alt="Panel de NichosForge Pro" width="900">

</div>

---

## ¿Qué es?

NichosForge Pro es un **panel web local**: funciona en tu PC, en `http://127.0.0.1:8767`, y te ayuda a elegir el nicho correcto para un
canal de YouTube sin rostro.
- **Encuentra** canales en inglés que ya funcionan.
- **Estima y mide** cuánto ganan.
- **Comprueba** si de verdad son sin rostro y si están monetizados.
- **Reconoce** los patrones de miniatura que se están viralizando ahora.
- **Te dice** qué nicho replicar en español, siguiendo la metodología **Aprende a Monetizar**.

Incluye a **Nichi**, una mascota ninja que hace de estratega con IA: razona con tus datos, compara opciones, **elige una** y te da un plan concreto.

## Funciones

| | Función | Qué hace |
|---|---|---|
| 🔭 | **Investigación** | Revisa cientos de videos largos (sin Shorts) de tendencias y búsquedas amplias, detecta canales automatizados y le pone un nicho a cada video. |
| 🔎 | **Explorar** | Busca nichos por frases (en inglés encuentras referentes; en español, tu competencia) y analiza cada canal: tipo, rol, salud, audiencia, visitas y ganancias. |
| 🎯 | **Mapa de mi canal** | Pones tu canal y obtienes tus **referentes en inglés**, tu **competencia directa** (mismo nicho en español) y tu **competencia indirecta** (nichos vecinos o temas que se cruzan), con tus huecos de contenido. |
| 🏆 | **Índice de oportunidad** | Un puntaje de 0 a 100 por nicho que combina demanda en inglés, competencia en español, RPM, canales jóvenes que crecen y tendencia. Los pesos se pueden ajustar. |
| 💵 | **Nichos con RPM más alto** | Ranking por lo que gana el creador cada 1.000 visitas, con el RPM real de los canales analizados. |
| 🚀 | **Outliers de referentes** | Los videos que más superan a su propio canal entre tus referentes, con el análisis «¿Por qué funcionó?». |
| 📈 | **Seguimiento real** | Una "foto" cada 6 h para medir las visitas reales de 24 h, 7 días y 30 días y el crecimiento semanal. Reemplaza a las estimaciones. |
| 🎨 | **Patrones de miniatura** | Reconoce en tu PC el diseño de cada miniatura (cara, texto, colores, flechas, pantalla dividida), agrupa las parecidas en patrones con nombre y ordena lo que es viral **ahora**. Puedes buscar parecidas desde cualquier miniatura. |
| 👁 | **Sin rostro verificado** | Mira en tu PC la miniatura y 3 fotogramas de cada video (OpenCV, con YuNet y SFace) para confirmar si la misma persona sale a cámara. |
| 💰 | **Verificador de monetización** | Dice «confirmado» solo con una prueba segura (botón Unirse o Super Thanks, o menos de 1.000 suscriptores). Si no, da una probabilidad con sus motivos. |
| 🔔 | **Alertas automáticas** | Revisa cada día tus canales y nichos seguidos y te avisa de outliers nuevos y de canales jóvenes que explotan. |
| 🧬 | **Patrones** | Lo que se repite en los videos ganadores: fórmulas y tipos de título, ideas repetidas entre canales, etiquetas y SEO. |
| 🏷 | **Clasificador de nichos** | Clasifica primero el canal, usa reglas con pesos, la IA revisa solo los dudosos y un modelo local aprende de tus correcciones. |
| 🧠 | **Nichi (estratega con IA)** | Responde con una decisión, sus motivos, un plan, los riesgos y botones de acción. También funciona sin IA. |
| 🔑 | **Varias claves de YouTube** | Si una se queda sin cuota, pasa sola a la siguiente, y reintenta si se corta la conexión. |
| 🌗 | **Modo claro y oscuro** | Modo oscuro con tonos rojizos, disfraces de temporada para Nichi y animaciones. |

<details>
<summary><b>Capturas</b></summary>

| | |
|---|---|
| ![Investigación](docs/img/investigacion.jpg) | ![Mapa de mi canal](docs/img/mapa.jpg) |
| ![Índice de oportunidad](docs/img/oportunidad.jpg) | ![Patrones de miniatura](docs/img/miniaturas.jpg) |
| ![Seguimiento real](docs/img/seguimiento.jpg) | ![Nichi](docs/img/nichi.jpg) |
| ![Nichos con RPM más alto](docs/img/rpm.jpg) | ![Verificador de monetización](docs/img/monetizacion.jpg) |

</details>

## Inicio rápido

### Requisitos
- **Python 3.10 o superior** (probado con 3.12).
- Una clave gratis de **YouTube Data API v3**: [Google Cloud Console](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
- Opcional, pero recomendada: una clave gratis de IA. Puede ser **Gemini** ([AI Studio](https://aistudio.google.com/apikey)), **Groq** o tu **FreeLLMAPI** local. También acepta Claude y OpenAI.

### Windows
1. Descarga o clona el repositorio.
2. Doble clic en **`instalar_actualizar.bat`**: instala las dependencias, incluido OpenCV.
3. Doble clic en **`iniciar_panel.bat`**: el panel se abre en `http://127.0.0.1:8767`.
4. En **Ajustes** pega tu clave o claves de YouTube y, si quieres, una clave de IA.

### macOS / Linux
```bash
git clone https://github.com/<tu-usuario>/nichosforge-pro.git
cd nichosforge-pro
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # opcional: también puedes pegar las claves desde el panel
python main.py panel
```

### Comandos
```bash
python main.py panel                # abre el panel (puerto 8767)
python main.py panel --no-abrir     # arranca sin abrir el navegador
python main.py panel --puerto 9000  # usa otro puerto
python main.py limpiar              # borra los datos locales (conserva ajustes y claves)
```

## Configuración

Las claves se guardan en **`.env`**, que nunca se sube a GitHub. Mira el ejemplo en [`.env.example`](.env.example):

| Variable | Para qué |
|---|---|
| `YOUTUBE_API_KEY`, `YOUTUBE_API_KEY_2…` | Claves de YouTube Data API v3 (rotan solas) |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `FREELLMAPI_KEY` | IA gratis (si una falla, pasa a la siguiente) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | IA de pago (opcional) |

Todo lo demás (CPM por nicho, factores por país, umbrales de alertas, tema, etc.) se cambia en **Ajustes** y se guarda en `datos/ajustes.json`.

### Costo en cuota (10.000 unidades al día por clave)

| Acción | Unidades aprox. |
|---|---|
| Búsqueda en Explorar (por frase) | 100 + unas 2 por canal analizado |
| Investigación rápida / normal / profunda | ≈ 200 / 560 / 1.030 |
| Mapa de mi canal | ≈ 700-800 |
| Radar de miniaturas (automático cada 6 h) | ≈ 40 |
| Seguimiento real | 1 por cada 50 canales, cada 6 h |
| Alertas | 1 por canal seguido + 102 por nicho seguido, una vez al día |
| Rostros, miniaturas y patrones | **0** (se calculan en tu PC) |
| Repetir algo en menos de 24 h | **0** (caché) |

## Cómo funciona

- **Sin frameworks ni base de datos:** usa el servidor HTTP de la biblioteca estándar de Python y archivos JSON con caché en memoria.
- **Todo en tu PC:** tus datos y tus claves solo salen hacia YouTube y hacia el proveedor de IA que elijas.
- **Tareas de fondo:** la verificación de rostros, el catálogo de miniaturas y las alertas corren en segundo plano y no bloquean nuevas búsquedas.
- La arquitectura completa (qué hace cada módulo de `core/`) está en el [README en inglés](README.md#how-it-works).

## Estructura

```
nichosforge-pro/
├── main.py                 punto de entrada (python main.py panel)
├── server.py               servidor HTTP y endpoints
├── core/                   toda la lógica
├── ui/index.html           la aplicación (HTML + CSS + JS)
├── ui/vendor/chart.umd.js  Chart.js 4 (MIT), incluido para funcionar sin internet
├── modelos/                detector de caras YuNet (BSD-3); SFace se descarga la primera vez
├── datos/                  tus datos locales (no se suben a GitHub)
├── docs/                   guía de uso (PDF) y capturas
├── iniciar_panel.bat       abre el panel en Windows
└── instalar_actualizar.bat instala o actualiza en Windows
```

## Precisión, límites y notas honestas

- **Estimado y real:** las visitas y ganancias mensuales son estimaciones hasta que el seguimiento real tiene al menos un día de fotos. Desde ese momento llevan la marca «real» ✓. El RPM y el CPM son aproximaciones por nicho, país, audiencia, duración de los videos y temporada.
- **Monetización:** ningún dato público dice al 100 % si un canal está en el Programa de Socios de YouTube. El verificador solo dice «confirmado» con una prueba segura; si no, informa una probabilidad.
- **Sin rostro:** usa las miniaturas y los fotogramas públicos. En nichos de documentales, un famoso que aparece en muchos videos puede salir como «dudoso».
- **Nichos:** en nuestras pruebas, la clasificación por canal acierta casi siempre. Un título suelto puede ser ambiguo, por eso cada video hereda el nicho de su canal.

## Cumplimiento

- Usa la **YouTube Data API v3** oficial. Eres responsable de cumplir los [Términos de los Servicios de API de YouTube](https://developers.google.com/youtube/terms/api-services-terms-of-service). Las fotos del seguimiento real se guardan **35 días** por defecto.
- La lectura de **páginas** públicas de YouTube, que solo sirve para *confirmar* la monetización, está **desactivada por defecto**, porque los términos de servicio de YouTube restringen el acceso automatizado a su sitio web. Si la activas, es bajo tu responsabilidad.
- Las miniaturas se descargan del servidor público de imágenes de YouTube solo para analizarlas en tu PC.
- Este proyecto no está afiliado a YouTube ni a Google.

## Contribuir

Puedes abrir issues y pull requests: mira [CONTRIBUTING.md](CONTRIBUTING.md). Nunca incluyas claves, el archivo `.env` ni la carpeta `datos/`.

## Licencia

[MIT](LICENSE) © colaboradores de NichosForge Pro. Los componentes de terceros están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
