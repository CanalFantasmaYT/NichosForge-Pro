# Changelog / Historial de cambios

All notable changes to this project. / Cambios importantes del proyecto.

## [13.1] — Monetization check no longer hangs / La verificación de monetización ya no se queda cargando
- One indicator with elapsed seconds, buttons locked while running, always cleaned up; errors shown inside the card.
- The panel renews its session token automatically after a restart (no more silent 403s in an old tab).
- Page reading: shorter timeouts, reason shown (timeout, cookie consent, HTTP code) and progress in the console.

## [13] — Code review fixes / Correcciones de la revisión de código
- **P1 · Security:** write endpoints now require a per-session token, local `Host`/`Origin` and `application/json` (CSRF / DNS rebinding). / **Seguridad**: token de sesión y validación de origen.
- **P1 · Tracking windows:** a 24 h window is “measured” only with a snapshot near its start; long gaps become a labeled daily **average**, short history a labeled **projection**. / Ventanas de 24 h honestas.
- **P2 · Labels:** “real” only for a fully measured month; projections are labeled as such; earnings and RPM always shown as **estimates**. / Etiquetas honestas.
- **P2 · Monetization:** < 1,000 subscribers is no longer “confirmed not monetized”; ads and fan funding (expanded YPP from 500 subs) reported separately. / Monetización sin falsa certeza.
- **P2 · Scheduler:** snapshot due-time is computed **per channel**. / Programador por canal.
- OpenCV 5 warning flood silenced; face detectors are created once per worker thread and reused (faster). / Sin avalancha de avisos de OpenCV.
- Regression tests in `tests/` run in CI. / Pruebas automáticas de cada hallazgo.

## [12] — Channel map, referent outliers, RPM by niche
- 🎯 **My channel map**: English referents + direct and indirect Spanish competition, comparison and content gaps. / **Mapa de mi canal**.
- 🚀 **Referent outliers** tab in Viral videos, with “Why did it work?”. / **Outliers de referentes**.
- 💵 **Highest-RPM niches** view in Opportunity. / **Nichos con RPM más alto**.

## [11] — Monetization checker / Verificador de monetización
- “Confirmed” only with hard proof (Join / Super Thanks, or < 1,000 subscribers); probability otherwise.
- Optional public-page reading, **off by default** (YouTube ToS).

## [10] — Accurate niches, opportunity index, alerts
- Rewritten niche classifier: whole words, weights, tie-breakers, channel-first, AI review of doubtful channels, local Naive Bayes that learns.
- 🎨 “Similar” button on any thumbnail. 🏆 Opportunity index (5 weighted criteria). 🔔 Daily automatic alerts + desktop notifications.

## [9] — Thumbnail patterns / Patrones de miniatura
- Local visual fingerprint (faces, MSER text detection, colors, red marks, split screen), visual clustering, trending radar, search channels by thumbnail.
- Background tasks that never block new searches.

## [8] — Faceless verification / Sin rostro verificado
- OpenCV YuNet + SFace on thumbnails and in-video frames; verdict overrides text heuristics.

## [7] — Expert Nichi + typography
- Decision framework, pre-computed analysis (opportunity index, referent ranking, user phase), conversation memory, actions, quick modes. Inter + Plus Jakarta Sans.

## [6] — Real view tracking / Seguimiento real
- Snapshots every 6 h, 24 h / 7 d / 30 d gains, weekly growth; real numbers replace estimates (35-day retention).

## [5] — Save from anywhere / Guardar desde cualquier parte

## [4] — Faster investigations, title/thumbnail/SEO patterns, both languages, CPM/RPM per channel and niche

## [3] — Investigation, multiple own channels, multiple YouTube keys, dark mode, seasonal mascot

## [1-2] — First panel: Explore, referents, funnel, Nichi, Aprende a Monetizar knowledge base
