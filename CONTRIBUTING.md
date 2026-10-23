# Contributing / Cómo contribuir

Thanks for helping! / ¡Gracias por ayudar!

## Setup / Preparación
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py panel
```

## Guidelines / Normas
- **Never commit secrets**: `.env`, API keys, the `datos/` folder or screenshots that show keys. / **Nunca subas claves** ni la carpeta `datos/`.
- Keep the project **dependency-light** and **local-first** (standard library HTTP server, JSON storage, vanilla JS).
- UI texts are in **Spanish** (neutral, "tú"). Code comments may be in Spanish or English.
- Respect YouTube's terms: prefer the official Data API; anything that reads public pages must be **opt-in**.
- Before opening a PR: `python -m compileall -q main.py server.py core` must pass, and the panel must load without errors in the browser console.

## Pull requests
1. Fork and create a branch: `git checkout -b feature/my-change`.
2. Describe **what** and **why**, with a screenshot if the UI changes.
3. Update `CHANGELOG.md` and, if relevant, both READMEs.

## Reporting bugs / Reportar errores
Use the issue templates. Include the message from the black console window (`[hh:mm:ss] ERROR | …`) and the steps to reproduce. **Remove any key** from logs or screenshots.
