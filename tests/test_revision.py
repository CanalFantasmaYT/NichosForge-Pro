"""Pruebas de los hallazgos de la revisión de código (23-oct-2026). Ejecutar: python -m unittest discover -s tests"""
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _punto(dias_atras, v, ahora):
    return {"t": (ahora - timedelta(days=dias_atras)).isoformat(timespec="seconds"), "v": v}


class P1_PeticionesDeOtroOrigen(unittest.TestCase):
    """Hallazgo 1: las rutas de escritura no deben aceptar peticiones de otro origen."""

    @classmethod
    def setUpClass(cls):
        import server
        from core import motor
        from http.server import ThreadingHTTPServer
        cls.llamadas = []
        motor.borrar_todo = lambda: cls.llamadas.append(1)          # no borra nada de verdad
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        html = urllib.request.urlopen(cls.base + "/").read().decode()
        cls.token = re.search(r'name="nf-token" content="([^"]+)"', html).group(1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _post(self, **cab):
        req = urllib.request.Request(self.base + "/api/borrar_todo", data=b"{}", method="POST", headers=cab)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_ataque_de_la_revision_bloqueado(self):
        antes = len(self.llamadas)
        self.assertEqual(self._post(**{"Content-Type": "text/plain", "Origin": "https://unrelated.example"}), 403)
        self.assertEqual(len(self.llamadas), antes, "no debe ejecutar la operación")

    def test_sin_token_o_con_origen_ajeno_bloqueado(self):
        self.assertEqual(self._post(**{"Content-Type": "application/json"}), 403)
        self.assertEqual(self._post(**{"Content-Type": "application/json", "X-NF-Token": self.token, "Origin": "https://evil.example"}), 403)
        self.assertEqual(self._post(**{"Content-Type": "application/json", "X-NF-Token": self.token, "Host": "evil.example"}), 403)

    def test_panel_legitimo_permitido(self):
        antes = len(self.llamadas)
        self.assertEqual(self._post(**{"Content-Type": "application/json", "X-NF-Token": self.token, "Origin": self.base}), 200)
        self.assertEqual(len(self.llamadas), antes + 1)


class P1_VentanaDe24Horas(unittest.TestCase):
    """Hallazgo 2: 7 días de visitas no pueden presentarse como 24 horas medidas."""

    def test_hueco_de_siete_dias_es_promedio_aproximado(self):
        from core import seguimiento as S
        ahora = datetime.now()
        r = S._ventana([_punto(7, 0, ahora), _punto(0, 7000, ahora)], 1)
        self.assertEqual(r["tipo"], "promedio")
        self.assertTrue(r["proyectado"])
        self.assertEqual(r["ganadas"], 1000)

    def test_fotos_cada_6_horas_es_medicion(self):
        from core import seguimiento as S
        ahora = datetime.now()
        r = S._ventana([_punto(1 - h / 24, 1000 * h, ahora) for h in range(0, 25, 6)], 1)
        self.assertEqual(r["tipo"], "medido")
        self.assertFalse(r["proyectado"])


class P2_ProyeccionNoEsReal(unittest.TestCase):
    """Hallazgo 3: con 1 día medido, el mes es una proyección, no un dato real."""

    def test_un_dia_no_es_real(self):
        from core import seguimiento as S
        orig = S.metricas
        try:
            S.metricas = lambda cid: {"d1": {"ganadas": 1000}, "d7": None, "d30": None, "mes": 30000, "mes_medido": 1.0,
                                      "mes_proyectado": True, "mes_tipo": "proyectado", "crecimiento": None}
            a = S.enriquecer({"id": "x", "visitas_mes": 5000, "rpm": 3})
            self.assertFalse(a["real"])
            self.assertTrue(a["medido"])
            self.assertIn("PROYECCIÓN", a["metodo_mes"])
        finally:
            S.metricas = orig

    def test_rpm_por_nicho_se_presenta_como_estimado(self):
        from core import cerebro
        for fila in cerebro.rpm_nichos():
            self.assertTrue(fila["estimado"])
            self.assertNotIn("real", fila["fuente"])


class P2_MonetizacionSinFalsaCerteza(unittest.TestCase):
    """Hallazgo 4: menos de 1.000 suscriptores no es «no monetizado, confirmado»."""

    def test_750_suscriptores_no_es_confirmado(self):
        from core import monetizado
        r = monetizado.evaluar({"suscriptores": 750, "videos_lista": []})
        self.assertNotEqual(r["confianza"], "confirmado")
        self.assertIn("fans", r["motivo"])

    def test_confirmado_solo_con_prueba_directa(self):
        from core import monetizado
        r = monetizado.evaluar({"suscriptores": 750, "videos_lista": []}, {"leida": True, "unirse": True})
        self.assertEqual(r["confianza"], "confirmado")


class P2_ProgramadorPorCanal(unittest.TestCase):
    """Hallazgo 5: una foto reciente de un canal no debe posponer a los demás."""

    def test_canal_vencido_se_detecta(self):
        from core import seguimiento as S
        from core.utils import write_json
        ahora = datetime.now()
        orig_fotos, orig_ids = S.FOTOS, S.ids_seguidos
        with tempfile.TemporaryDirectory() as d:
            try:
                S.FOTOS = Path(d) / "fotos.json"
                write_json(S.FOTOS, {"A": [_punto(3, 100, ahora)], "B": [_punto(0.003, 200, ahora)]})
                S.ids_seguidos = lambda: {"A": "guardado", "B": "guardado"}
                self.assertTrue(S.toca_foto())
                self.assertEqual(S.vencidos(), ["A"])
            finally:
                S.FOTOS, S.ids_seguidos = orig_fotos, orig_ids


if __name__ == "__main__":
    unittest.main(verbosity=2)
