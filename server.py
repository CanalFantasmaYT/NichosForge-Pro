"""Panel web local de NichosForge Pro (solo accesible desde tu PC: 127.0.0.1).

    python main.py panel      ->  http://127.0.0.1:8767
"""
import json
import mimetypes
import threading
import hmac
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from core import academia, alertas, bot, cerebro, exportar, llm, miniaturas, monetizado, motor, patrones, rostros, seguimiento
from core import youtube as yt
from core.analisis import ligero
from core.config import BASE, PUERTO, ajustes, buscar_clave, claves_youtube, guardar_ajustes, guardar_clave

TOKEN = secrets.token_urlsafe(32)        # token de sesión: cambia cada vez que arranca el panel

CLAVES = ["GEMINI_API_KEY", "GROQ_API_KEY", "FREELLMAPI_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
UI = BASE / "ui"


def _lineas(x):
    return [l.strip() for l in x.splitlines() if l.strip()] if isinstance(x, str) else [str(l).strip() for l in (x or []) if str(l).strip()]


def _resumen_busqueda(b: dict) -> dict:
    cs = [motor.canal(c) for c in b["canales"]]
    cs = [c for c in cs if c]
    return {"id": b["id"], "titulo": b["titulo"], "tipo": b["tipo"], "fecha": b["fecha"], "canales": len(cs),
            "referentes": sum(1 for c in cs if c["es_referente"]), "virales": len(b.get("virales", [])),
            "automatizados": sum(1 for c in cs if c.get("auto_tipo") == "automatizado"),
            "avatares": [c["avatar"] for c in sorted(cs, key=lambda c: -c["score"])[:4]]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, code=200, extra=None):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass          # recargaste o cerraste la página antes de recibir la respuesta: no es un error

    def _json(self, data, code=200):
        self._send(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8", code)

    # ---------- seguridad: solo el propio panel puede pedir cambios ----------
    def _host_valido(self) -> bool:
        """Protege contra 'DNS rebinding': el Host debe ser el propio panel local."""
        host = (self.headers.get("Host") or "").lower()
        return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def _escritura_permitida(self) -> str | None:
        """None si la petición viene del panel; si no, el motivo del rechazo."""
        if not self._host_valido():
            return "Host no permitido."
        origen = self.headers.get("Origin")
        if origen and origen.lower().rstrip("/") not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            return "Origen no permitido."
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return "Tipo de contenido no permitido."
        if not hmac.compare_digest(self.headers.get("X-NF-Token") or "", TOKEN):
            return "Token de sesión inválido. Recarga el panel."
        return None

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _descarga(self, res):
        (datos, ext, mime), nombre = res
        archivo = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in nombre)[:60].strip() or "datos"
        self._send(datos, mime, extra={"Content-Disposition": f"attachment; filename=\"NichosForge - {archivo}.{ext}\"; "
                                                                f"filename*=UTF-8''{quote('NichosForge - ' + archivo + '.' + ext)}"})

    # ---------- GET ----------
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if not self._host_valido():
                return self._json({"error": "Host no permitido."}, 403)
            if u.path in ("/", "/index.html"):
                html = (UI / "index.html").read_text(encoding="utf-8").replace(
                    "<head>", f'<head>\n<meta name="nf-token" content="{TOKEN}">', 1)
                self._send(html.encode("utf-8"), "text/html; charset=utf-8",
                           extra={"Cache-Control": "no-store", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
            elif u.path.startswith("/vendor/") or u.path.startswith("/img/"):
                f = (UI / u.path.lstrip("/")).resolve()
                if UI.resolve() not in f.parents or not f.is_file():
                    return self._json({"error": "no encontrado"}, 404)
                self._send(f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream",
                           extra={"Cache-Control": "max-age=86400"})
            elif u.path == "/api/estado":
                aj = ajustes()
                mc = motor.mi_canal()
                self._json({"nombre": aj["nombre"], "mi_canal_ref": aj["mi_canal"], "cuota_hoy": yt.cuota_hoy(),
                            "tema": aj.get("tema"), "nichi_skin": aj.get("nichi_skin"), "nichi_datos": aj.get("nichi_datos"),
                            "mis_canales": motor.mis_canales(), "claves_yt": len(yt.estado_claves()),
                            "investigaciones": motor.investigaciones()[:6], "videos_guardados": len(motor.videos_guardados()),
                            "ids_videos": list(motor.videos_guardados()), "ids_canales": list(motor.guardados()),
                            "con_api": bool(claves_youtube()), "con_ia": llm.disponible(), "ia_nombre": llm.nombre(llm.proveedor()),
                            "trabajo": {k: v for k, v in motor.estado().items() if k != "log"},
                            "mi_canal": ligero(mc["analisis"]) | {"actualizado": mc["actualizado"],
                                                                  "serie": [{"f": v["publicado"], "v": v["vistas"], "l": v["likes"], "t": v["titulo"]}
                                                                            for v in mc["analisis"]["videos_lista"]]} if mc else None,
                            "busquedas": [_resumen_busqueda(b) for b in motor.busquedas()[:12]],
                            "guardados": len(motor.guardados()), "top_referentes": motor.top_referentes(5),
                            "visitas_mes_min": aj["visitas_mes_min"]})
            elif u.path == "/api/academia":
                self._json({"secciones": academia.SECCIONES, "preguntas": academia.PREGUNTAS, "tips": academia.TIPS,
                            "categorias": list(academia.SEMILLAS)})
            elif u.path == "/api/token":
                self._json({"token": TOKEN})                 # otras webs no pueden leerlo: sin CORS y Host validado
            elif u.path == "/api/investigaciones":
                self._json({"lista": motor.investigaciones(), "costos": {k: motor.costo_investigacion(k) for k in motor.PROFUNDIDAD}})
            elif u.path == "/api/investigacion":
                self._json(motor.investigacion(q.get("id")) or {})
            elif u.path == "/api/videos_guardados":
                self._json({"videos": list(motor.videos_guardados().values()), "categorias": motor.categorias()})
            elif u.path == "/api/categorias":
                self._json({"categorias": motor.categorias()})
            elif u.path == "/api/sugerencias":
                self._json(motor.sugerencias(False))
            elif u.path == "/api/mis_canales":
                self._json({"canales": motor.mis_canales()})
            elif u.path == "/api/claves_youtube":
                self._json({"claves": yt.estado_claves(), "cuota_hoy": yt.cuota_hoy()})
            elif u.path == "/descargar/investigacion":
                self._descarga(exportar.investigacion(q.get("id")))
            elif u.path == "/descargar/videos":
                self._descarga(exportar.videos_guardados())
            elif u.path == "/api/patrones":
                tipo, rid = q.get("tipo", "investigacion"), q.get("id", "")
                if tipo == "busqueda":
                    vids = motor.busqueda(rid).get("virales", [])
                else:
                    r_ = motor.investigacion(rid or None) or {}
                    rid, vids = r_.get("id", ""), r_.get("videos", [])
                if not vids:
                    raise ValueError("No hay videos para analizar.")
                self._json(patrones.analizar(f"{tipo}_{rid}", vids, q.get("miniaturas", "1") == "1", q.get("forzar") == "1"))
            elif u.path == "/api/seguimiento":
                origen = seguimiento.ids_seguidos()
                filas = []
                for cid, org in origen.items():
                    a = motor.ligero_de(cid)
                    if a:
                        filas.append({**a, "origen": org})
                self._json({"canales": filas, "ultima_foto": seguimiento.ultima_foto(), "intervalo_horas": seguimiento.INTERVALO_HORAS,
                            "dias_retencion": ajustes().get("seguimiento_dias", 35), "seguidos": seguimiento.seguidos_extra()})
            elif u.path == "/api/rpm_nichos":
                self._json({"nichos": cerebro.rpm_nichos()})
            elif u.path == "/api/outliers_referentes":
                self._json(motor.outliers_referentes(int(q.get("dias") or 90), float(q.get("omin") or 2), q.get("nicho") or "", q.get("idioma") or ""))
            elif u.path == "/api/mapa":
                self._json({"mapa": motor.mapa(q.get("id")), "lista": [{"id": m["id"], "canal": m["yo"]["canal"], "fecha": m["fecha"]} for m in motor.mapas()]})
            elif u.path == "/api/oportunidad":
                self._json({"nichos": cerebro.tabla_nichos(40), "pesos": cerebro.PESOS, "nombres": cerebro.NOMBRES,
                            "seguidos": alertas.nichos_seguidos()})
            elif u.path == "/api/alertas":
                self._json({"alertas": alertas.lista(q.get("nuevas") == "1"), **alertas.estado()})
            elif u.path == "/api/miniaturas/patrones":
                self._json({**miniaturas.patrones(int(q.get("dias") or 30), q.get("idioma") or ""), "disponible": miniaturas.disponible()})
            elif u.path == "/api/miniaturas/parecidas":
                vec = miniaturas.vector_patron(q["patron"]) if q.get("patron") else (miniaturas.huella_de(q["id"]) or {}).get("v")
                if not vec:
                    raise ValueError("No pude leer esa miniatura.")
                self._json(miniaturas.parecidas(vec, excluir=q.get("id", "")))
            elif u.path == "/api/rostros/estado":
                self._json(rostros.estado_modelos())
            elif u.path == "/api/trabajo":
                self._json({**motor.estado(), "fondo": motor.fondo(), "alertas": alertas.estado()})
            elif u.path == "/api/mi_canal":
                mc = motor.mi_canal()
                self._json(mc or {})
            elif u.path == "/api/busqueda":
                b = motor.busqueda(q["id"])
                g = motor.guardados()
                cs = [motor.ligero_de(c) for c in b["canales"]]
                self._json({**b, "canales": [c | {"guardado": c["id"] in g} for c in cs if c]})
            elif u.path == "/api/canal":
                a = motor.canal(q["id"])
                if not a:
                    raise ValueError("Canal no analizado")
                self._json(a | {"guardado": motor.guardados().get(q["id"])})
            elif u.path == "/api/guardados":
                self._json({"filas": motor.lista_guardados(), "etapas": motor.ETAPAS})
            elif u.path == "/api/ajustes":
                claves = {}
                for k in CLAVES:
                    v, origen = buscar_clave(k)
                    claves[k] = {"ok": bool(v), "origen": origen, "vista": (v[:6] + "…" + v[-4:]) if len(v) > 12 else ("✓" if v else "")}
                self._json({"ajustes": ajustes(), "claves": claves, "carpeta": str(BASE), "ia": llm.estado()})
            elif u.path == "/descargar/canal":
                self._descarga(exportar.canal(q["id"]))
            elif u.path == "/descargar/busqueda":
                self._descarga(exportar.busqueda(q["id"]))
            elif u.path == "/descargar/guardados":
                self._descarga(exportar.guardados())
            else:
                self._json({"error": "no encontrado"}, 404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 400)

    # ---------- POST ----------
    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        motivo = self._escritura_permitida()
        if motivo:                                   # se rechaza ANTES de leer o ejecutar nada
            return self._json({"error": motivo}, 403)
        try:
            d = self._body()
            r = {"ok": True}
            if u.path == "/api/mi_canal/analizar":
                if d.get("mi_canal"):
                    guardar_ajustes({"mi_canal": d["mi_canal"]})
                motor.analizar_mi_canal(d.get("mi_canal") or None)
            elif u.path == "/api/mis_canales/activar":
                motor.activar_mi_canal(d["id"])
            elif u.path == "/api/mis_canales/quitar":
                motor.quitar_mi_canal(d["id"])
            elif u.path == "/api/mis_canales/actualizar":
                motor.actualizar_mis_canales()
            elif u.path == "/api/investigar":
                motor.investigar(d)
            elif u.path == "/api/investigacion/borrar":
                motor.borrar_investigacion(d["id"])
            elif u.path == "/api/video/guardar":
                motor.guardar_video(d.get("video") or {}, d.get("categoria") or "")
            elif u.path == "/api/video/editar":
                motor.editar_video(d["id"], d.get("cambios") or {})
            elif u.path == "/api/video/quitar":
                motor.quitar_video(d["id"])
            elif u.path == "/api/nicho":
                motor.nicho_manual(d.get("tipo") or "video", d["id"], d.get("nicho") or "", d.get("titulos") or [],
                                   d.get("canal_id") or "", bool(d.get("todo_canal")), [w.strip() for w in (d.get("palabras") or "").split(",") if w.strip()])
            elif u.path == "/api/sugerencias":
                r = motor.sugerencias(bool(d.get("forzar")))
            elif u.path == "/api/mapa":
                motor.mapa_canal(d)
            elif u.path == "/api/referentes/actualizar":
                motor.actualizar_referentes()
            elif u.path == "/api/alertas/revisar":
                alertas.en_fondo(True)
            elif u.path == "/api/alertas/leer":
                alertas.marcar_leidas(d.get("ids"))
            elif u.path == "/api/nichos/seguir":
                (alertas.dejar_nicho if d.get("dejar") else alertas.seguir_nicho)(d["nicho"])
            elif u.path == "/api/miniaturas/radar":
                motor.radar_miniaturas(d)
            elif u.path == "/api/miniaturas/buscar_canales":
                if d.get("patron"):
                    vec, etq, exc = miniaturas.vector_patron(d["patron"]), d["patron"], ""
                else:
                    h = miniaturas.huella_de(d["id"]) or {}
                    vec, etq, exc = h.get("v"), (h.get("titulo") or "esta miniatura")[:50], d["id"]
                if not vec:
                    raise ValueError("No pude leer esa miniatura.")
                motor.buscar_por_miniatura({"vec": vec, "etiqueta": etq, "excluir": exc})
            elif u.path == "/api/monetizado":
                r = monetizado.verificar(d["id"], bool(d.get("forzar")), d.get("leer_pagina")) or {"titulo": "Canal no analizado", "veredicto": "desconocido"}
            elif u.path == "/api/rostro":
                r = rostros.verificar_canal(d["id"], bool(d.get("forzar"))) or {"veredicto": "sin_verificar", "motivo": "Canal no analizado."}
            elif u.path == "/api/rostros/modelo":
                threading.Thread(target=rostros.descargar_reconocedor, daemon=True).start()
            elif u.path == "/api/seguimiento/foto":
                r = seguimiento.tomar_foto()
            elif u.path == "/api/seguimiento/seguir":
                cid = d.get("id") or yt.resolver_canal(d.get("ref") or "")
                if not cid:
                    raise ValueError("No encontré ese canal.")
                if not motor.canal_crudo(cid):
                    motor.analizar_uno(cid)                  # un canal: unas 3 unidades
                seguimiento.seguir(cid)
                seguimiento.tomar_foto([cid])
                r = {"ok": True, "id": cid}
            elif u.path == "/api/seguimiento/dejar":
                seguimiento.dejar(d["id"])
            elif u.path == "/api/claves_youtube":
                from core.config import guardar_claves_youtube
                guardar_claves_youtube(d.get("lista") or [])
            elif u.path == "/api/claves_youtube/agregar":
                from core.config import guardar_claves_youtube
                nueva = (d.get("clave") or "").strip()
                if len(nueva) < 20:
                    raise ValueError("Esa no parece una clave de YouTube válida.")
                guardar_claves_youtube(claves_youtube() + [nueva])
            elif u.path == "/api/claves_youtube/quitar":
                from core.config import guardar_claves_youtube
                lista = claves_youtube()
                i = int(d.get("indice", -1))
                if 0 <= i < len(lista):
                    lista.pop(i)
                guardar_claves_youtube(lista)
            elif u.path == "/api/claves_youtube/probar":
                r = {"ok": True, "resultados": yt.probar_claves()}
            elif u.path == "/api/mi_canal/sugerencias":
                r = motor.sugerencias_mi_canal(bool(d.get("traducir", True)))
            elif u.path == "/api/buscar":
                motor.buscar(d)
            elif u.path == "/api/descubrir":
                r = {"ok": True, "frases": motor.descubrir(d)}
            elif u.path == "/api/similares":
                r = {"ok": True, "frases": motor.similares(d.get("ids") or [], d.get("parametros") or {})}
            elif u.path == "/api/analizar_links":
                links = _lineas(d.get("links") or "")
                if not links:
                    raise ValueError("Pega al menos un canal.")
                motor.analizar_links(links)
            elif u.path == "/api/cancelar":
                motor.cancelar()
            elif u.path == "/api/busqueda/borrar":
                motor.borrar_busqueda(d["id"])
            elif u.path == "/api/guardar":
                motor.guardar(d.get("ids") or [], d.get("nicho") or "")
            elif u.path == "/api/guardado/editar":
                motor.editar_guardado(d["id"], d.get("cambios") or {})
            elif u.path == "/api/guardado/quitar":
                motor.quitar_guardados(d.get("ids") or [])
            elif u.path == "/api/top_historico":
                motor.top_historico(d["id"])
            elif u.path == "/api/ajustes":
                guardar_ajustes(d.get("cambios") or {})
            elif u.path == "/api/claves":
                for k, v in (d.get("claves") or {}).items():
                    if k in CLAVES and (v or "").strip():
                        guardar_clave(k, v)
            elif u.path == "/api/claves/probar":
                r = {"ok": True, "mensaje": yt.probar_clave()}
            elif u.path == "/api/ia/probar":
                r = {"ok": True, "resultados": llm.probar()}
            elif u.path == "/api/cache/limpiar":
                r = {"ok": True, "borrados": yt.limpiar_cache()}
            elif u.path == "/api/borrar_todo":
                motor.borrar_todo()
            elif u.path == "/api/bot":
                r = bot.responder(d.get("pregunta", ""), d.get("contexto"), d.get("historial"))
            else:
                return self._json({"error": "no encontrado"}, 404)
            self._json(r)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 400)


def serve(puerto: int = 0, abrir: bool = True):
    puerto = puerto or PUERTO
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Handler)
    url = f"http://127.0.0.1:{puerto}"
    print(f"\n  NichosForge Pro en {url}   (Ctrl+C para cerrar)\n", flush=True)
    seguimiento.iniciar_programador()
    if abrir:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Cerrando panel...")


if __name__ == "__main__":
    serve()
