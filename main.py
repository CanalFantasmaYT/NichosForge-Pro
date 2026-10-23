"""NichosForge Pro - analiza tu canal, encuentra nichos y referentes de YouTube.

Lo normal es usar el PANEL:   python main.py panel      (o doble clic en iniciar_panel.bat)
"""
import argparse
import os
import sys

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # sin la avalancha de avisos de OpenCV 5 en la consola

try:
    import dotenv, requests  # noqa: F401,E401
except ImportError as _e:
    sys.exit(f"Falta la librería '{_e.name}'. Ejecuta instalar_actualizar.bat "
             f"o en esta carpeta: python -m pip install -r requirements.txt")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main():
    ap = argparse.ArgumentParser(description="NichosForge Pro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("panel", help="abre el panel web local")
    p.add_argument("--puerto", type=int, default=0)
    p.add_argument("--no-abrir", action="store_true")
    sub.add_parser("limpiar", help="borra búsquedas, canales analizados, guardados y caché")
    a = ap.parse_args()
    if a.cmd == "panel":
        from server import serve
        serve(a.puerto, abrir=not a.no_abrir)
    elif a.cmd == "limpiar":
        from core import motor
        motor.borrar_todo()
        print("Listo: NichosForge Pro quedó en limpio (se conservan tus ajustes y claves).")


if __name__ == "__main__":
    main()
