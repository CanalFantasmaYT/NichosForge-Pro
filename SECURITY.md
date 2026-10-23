# Security / Seguridad

## API keys / Claves
- Keys are stored only in your local `.env` file, which is git-ignored. / Las claves solo están en tu `.env` local, que Git ignora.
- If a key was ever exposed (screenshot, commit, chat), **revoke it and create a new one** in Google Cloud Console / AI Studio / your provider.
  Si una clave se expuso, **revócala y crea otra**.
- If you accidentally committed a key: rotate it first, then remove it from history (`git filter-repo` or GitHub's guide on removing sensitive data).

## Local server / Servidor local
- The panel listens on `127.0.0.1` only (not reachable from your network). Do not expose port 8767 to the internet.
- El panel solo escucha en `127.0.0.1`. No expongas el puerto 8767 a internet.

## Reporting a vulnerability / Reportar una vulnerabilidad
Please open a private security advisory on GitHub (Security → Advisories) instead of a public issue.
