"""Testes com um site falso rodando localmente (sem acessar a internet).

    python -m unittest discover tests
"""

import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from plataforma import conectores as con
from plataforma.armazenamento import Armazenamento
from plataforma.servidor import criar_servidor


class SiteFalso(BaseHTTPRequestHandler):
    pedidos = []

    def log_message(self, *args):
        pass

    def responder(self, dado, status=200, tipo="application/json"):
        corpo = dado if isinstance(dado, bytes) else json.dumps(dado).encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        SiteFalso.pedidos.append((url.path, q, dict(self.headers)))
        base = f"http://127.0.0.1:{self.server.server_port}"
        ids = list(range(1, 6))
        if url.path == "/lista":
            self.responder([{"id": 1, "nome": "ação"}, {"id": 2, "nome": "b"}])
        elif url.path == "/paginas":
            p, n = int(q["p"]), int(q["n"])
            self.responder({"data": {"itens": [
                {"id": i} for i in ids[(p - 1) * n:p * n]]}})
        elif url.path == "/offset":
            o, n = int(q["offset"]), int(q["limit"])
            self.responder([{"id": i} for i in ids[o:o + n]])
        elif url.path == "/cursor":
            passo = {None: 1, "abc": 2}.get(q.get("c"), 3)
            if "pg" in q:
                passo = 3
            prox = {1: "abc", 2: f"{base}/cursor?pg=3", 3: None}[passo]
            self.responder({"resultados": [{"id": passo}],
                            "meta": {"prox": prox}})
        elif url.path == "/infinito":
            self.responder([{"id": 1}])
        elif url.path == "/sidra":
            self.responder([{"V": "Valor", "D1N": "Local"},
                            {"V": "0.5", "D1N": "Brasil"}])
        elif url.path == "/aninhado":
            self.responder([{"id": 1, "regiao": {"sigla": "N"},
                             "tags": ["a", "b"]},
                            {"id": 2, "extra": True}])
        elif url.path == "/arquivo.csv":
            self.responder("Município;Preço\nSão Luís;5,99\n".encode("latin1"),
                           tipo="text/csv")
        elif url.path == "/protegido":
            ok = (self.headers.get("Authorization") == "Bearer segredo")
            self.responder([{"ok": True}] if ok else {"erro": "x"},
                           200 if ok else 401)
        elif url.path == "/html":
            self.responder(b"<html>oi</html>", tipo="text/html")
        else:
            self.responder({"erro": "nada"}, 404)


def subir(servidor):
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{servidor.server_port}"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = ThreadingHTTPServer(("127.0.0.1", 0), SiteFalso)
        cls.url = subir(cls.site)

    @classmethod
    def tearDownClass(cls):
        cls.site.shutdown()
        cls.site.server_close()

    def setUp(self):
        SiteFalso.pedidos.clear()
        self.fonte = {"base_url": self.url + "/", "tentativas": 1}

    def baixar(self, endpoint, segredos=None, **kw):
        return con.baixar_endpoint(self.fonte, endpoint, segredos, "site", **kw)


class TesteConectores(Base):
    def test_lista_simples(self):
        linhas, aviso = self.baixar({"caminho": "/lista"})
        self.assertEqual([l["nome"] for l in linhas], ["ação", "b"])
        self.assertIsNone(aviso)
        self.assertEqual(len(SiteFalso.pedidos), 1)

    def test_params_vao_na_url(self):
        self.baixar({"caminho": "lista", "params": {"data": "01/01/2020"}})
        self.assertEqual(SiteFalso.pedidos[0][1], {"data": "01/01/2020"})

    def test_paginacao_por_pagina(self):
        linhas, _ = self.baixar({
            "caminho": "/paginas", "registros": "data.itens",
            "paginacao": {"tipo": "pagina", "param": "p",
                          "param_tamanho": "n", "tamanho": 2}})
        self.assertEqual([l["id"] for l in linhas], [1, 2, 3, 4, 5])
        self.assertEqual([p[1]["p"] for p in SiteFalso.pedidos],
                         ["1", "2", "3"])

    def test_paginacao_por_offset(self):
        linhas, _ = self.baixar({
            "caminho": "/offset",
            "paginacao": {"tipo": "offset", "tamanho": 2}})
        self.assertEqual([l["id"] for l in linhas], [1, 2, 3, 4, 5])
        self.assertEqual([p[1]["offset"] for p in SiteFalso.pedidos],
                         ["0", "2", "4"])

    def test_paginacao_por_cursor_e_url(self):
        linhas, _ = self.baixar({
            "caminho": "/cursor", "registros": "resultados",
            "paginacao": {"tipo": "cursor", "param": "c",
                          "campo_proximo": "meta.prox"}})
        self.assertEqual([l["id"] for l in linhas], [1, 2, 3])
        self.assertEqual(SiteFalso.pedidos[1][1], {"c": "abc"})
        self.assertEqual(SiteFalso.pedidos[2][1], {"pg": "3"})

    def test_limite_de_paginas_avisa(self):
        linhas, aviso = self.baixar({
            "caminho": "/infinito",
            "paginacao": {"tipo": "pagina", "max_paginas": 3}})
        self.assertEqual(len(linhas), 3)
        self.assertIn("Limite de 3", aviso)

    def test_primeira_linha_cabecalho(self):
        linhas, _ = self.baixar({"caminho": "/sidra",
                                 "primeira_linha_cabecalho": True})
        self.assertEqual(linhas, [{"Valor": "0.5", "Local": "Brasil"}])

    def test_aninhado_e_colunas_diferentes(self):
        linhas, _ = self.baixar({"caminho": "/aninhado"})
        self.assertEqual(linhas[0]["regiao.sigla"], "N")
        self.assertEqual(linhas[0]["tags"], '["a", "b"]')
        self.assertEqual(con.colunas_de(linhas),
                         ["id", "regiao.sigla", "tags", "extra"])

    def test_csv_latin1(self):
        linhas, _ = self.baixar({
            "caminho": "/arquivo.csv", "formato_resposta": "csv",
            "separador": ";", "codificacao": "latin1"})
        self.assertEqual(linhas, [{"Município": "São Luís", "Preço": "5,99"}])

    def test_auth_bearer(self):
        self.fonte["auth"] = {"tipo": "bearer"}
        linhas, _ = self.baixar({"caminho": "/protegido"},
                                {"token": "segredo"})
        self.assertEqual(linhas, [{"ok": True}])
        with self.assertRaisesRegex(con.ErroDownload, "401"):
            self.baixar({"caminho": "/protegido"}, {"token": "errado"})
        with self.assertRaisesRegex(con.ErroConfig, "token"):
            self.baixar({"caminho": "/protegido"}, {})

    def test_auth_api_key_e_basic(self):
        self.fonte["auth"] = {"tipo": "api_key", "nome": "X-Chave"}
        self.baixar({"caminho": "/lista"}, {"chave": "k1"})
        self.assertEqual(SiteFalso.pedidos[-1][2]["X-Chave"], "k1")
        self.fonte["auth"] = {"tipo": "api_key", "nome": "key",
                              "onde": "query"}
        self.baixar({"caminho": "/lista"}, {"chave": "k1"})
        self.assertEqual(SiteFalso.pedidos[-1][1], {"key": "k1"})
        self.fonte["auth"] = {"tipo": "basic"}
        self.baixar({"caminho": "/lista"}, {"usuario": "ana", "senha": "pw"})
        self.assertEqual(SiteFalso.pedidos[-1][2]["Authorization"],
                         "Basic " + base64.b64encode(b"ana:pw").decode())

    def test_erros_tem_mensagem_clara(self):
        with self.assertRaisesRegex(con.ErroDownload, "404"):
            self.baixar({"caminho": "/nao_existe"})
        with self.assertRaisesRegex(con.ErroDownload, "JSON"):
            self.baixar({"caminho": "/html"})
        self.fonte["base_url"] = "http://127.0.0.1:1"
        with self.assertRaisesRegex(con.ErroDownload, "conectar"):
            self.baixar({"caminho": "/lista"})

    def test_validacao(self):
        ok = {"base_url": "https://x.com",
              "endpoints": {"a": {"caminho": "/"}}}
        con.validar_fonte("site_1", ok)
        casos = [
            ("Site X", ok, "identificador"),
            ("../x", ok, "identificador"),
            ("s", {"base_url": "ftp://x"}, "URL base"),
            ("s", dict(ok, auth={"tipo": "oauth"}), "autenticação"),
            ("s", dict(ok, endpoints={"A b": {}}), "identificador"),
            ("s", dict(ok, endpoints={"a": {"paginacao": {"tipo": "cursor"}}}),
             "campo_proximo"),
            ("s", dict(ok, endpoints={"a": {"formato_resposta": "xml"}}),
             "formato"),
        ]
        for nome, fonte, trecho in casos:
            with self.assertRaisesRegex(con.ErroConfig, trecho):
                con.validar_fonte(nome, fonte)

    def test_config_de_exemplo_e_valida(self):
        with open("config/fontes.json", encoding="utf-8") as f:
            fontes = json.load(f)["fontes"]
        for nome, fonte in fontes.items():
            con.validar_fonte(nome, fonte)
        self.assertLessEqual({"ibge", "anp", "bcb"}, set(fontes))


class TesteArmazenamento(Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.arm = Armazenamento(self.tmp.name)

    def test_baixar_grava_csv_e_historico(self):
        self.fonte["endpoints"] = {"lista": {"caminho": "/lista"},
                                   "ruim": {"caminho": "/nao_existe"}}
        self.arm.salvar_fonte("site", self.fonte)
        res = self.arm.baixar_tudo()
        self.assertEqual([r["status"] for r in res], ["ok", "erro"])
        self.assertEqual(res[0]["linhas"], 2)
        bruto = self.arm.caminho_csv("site", "lista").read_bytes()
        self.assertTrue(bruto.startswith(b"\xef\xbb\xbf"))
        self.assertIn("id;nome\r\n1;ação", bruto.decode("utf-8-sig"))
        self.assertFalse(self.arm.caminho_csv("site", "ruim").exists())
        hist = self.arm.historico()
        self.assertEqual([h["endpoint"] for h in hist], ["ruim", "lista"])
        self.assertIn("404", hist[0]["mensagem"])
        arquivos = self.arm.arquivos()
        self.assertEqual(len(arquivos), 1)
        self.assertEqual(arquivos[0]["linhas"], "2")
        previa = self.arm.previa("site", "lista")
        self.assertEqual(previa, {"colunas": ["id", "nome"],
                                  "linhas": [["1", "ação"], ["2", "b"]]})

    def test_segredos_ficam_separados_e_sao_mantidos(self):
        self.fonte["auth"] = {"tipo": "bearer"}
        self.fonte["endpoints"] = {"p": {"caminho": "/protegido"}}
        self.arm.salvar_fonte("site", self.fonte, {"token": "segredo"})
        self.assertNotIn("segredo", self.arm.arq_fontes.read_text("utf-8"))
        self.assertEqual(self.arm.segredos_definidos(), {"site": ["token"]})
        # Salvar de novo com o campo vazio mantém a credencial.
        self.arm.salvar_fonte("site", self.fonte, {"token": ""})
        self.assertEqual(self.arm.baixar("site", "p")["status"], "ok")
        # Trocar o tipo de login descarta a credencial antiga.
        self.fonte["auth"] = {"tipo": "nenhuma"}
        self.arm.salvar_fonte("site", self.fonte)
        self.assertEqual(self.arm.segredos_definidos(), {})

    def test_excluir_e_site_desconhecido(self):
        self.fonte["endpoints"] = {"lista": {"caminho": "/lista"}}
        self.arm.salvar_fonte("site", self.fonte)
        self.arm.excluir_fonte("site")
        self.assertEqual(self.arm.fontes(), {})
        self.assertEqual(self.arm.baixar("site", "lista")["status"], "erro")
        with self.assertRaises(con.ErroConfig):
            self.arm.baixar_tudo("nao_existe")
        with self.assertRaises(con.ErroConfig):
            self.arm.caminho_csv("..", "x")


class TesteServidor(Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.srv = criar_servidor(self.tmp.name, 0)
        self.app = subir(self.srv)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def pedir(self, caminho, corpo=None, cabecalhos=None):
        cab = {"Content-Type": "application/json"} if corpo is not None else {}
        cab.update(cabecalhos or {})
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(self.app + caminho, data=dados,
                                     headers=cab)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_fluxo_completo_pela_api(self):
        status, corpo, _ = self.pedir("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Plataforma de Dados", corpo)

        fonte = dict(self.fonte, auth={"tipo": "bearer"},
                     endpoints={"lista": {"caminho": "/lista"}})
        teste = {"nome": "site", "fonte": fonte,
                 "endpoint": {"caminho": "/protegido"},
                 "segredos": {"token": "segredo"}}
        status, corpo, _ = self.pedir("/api/testar", teste)
        self.assertEqual((status, json.loads(corpo)["linhas"]),
                         (200, [[True]]))

        status, _, _ = self.pedir("/api/fontes", {
            "nome": "site", "fonte": fonte, "segredos": {"token": "segredo"}})
        self.assertEqual(status, 200)
        estado = json.loads(self.pedir("/api/estado")[1])
        self.assertEqual(estado["segredos_definidos"], {"site": ["token"]})
        self.assertNotIn("segredo", json.dumps(estado["fontes"]))

        res = json.loads(self.pedir("/api/baixar", {
            "fonte": "site", "endpoint": "lista"})[1])
        self.assertEqual((res["status"], res["linhas"]), ("ok", 2))
        self.assertEqual(len(json.loads(self.pedir("/api/dados")[1])), 1)
        self.assertEqual(len(json.loads(self.pedir("/api/historico")[1])), 1)
        previa = json.loads(self.pedir(
            "/api/previa?fonte=site&endpoint=lista")[1])
        self.assertEqual(previa["colunas"], ["id", "nome"])
        status, corpo, cab = self.pedir("/arquivo?fonte=site&endpoint=lista")
        self.assertEqual(status, 200)
        self.assertIn("site_lista.csv", cab["Content-Disposition"])

        self.pedir("/api/fontes/excluir", {"nome": "site"})
        self.assertEqual(json.loads(self.pedir("/api/estado")[1])["fontes"], {})

    def test_erros_e_protecoes(self):
        status, corpo, _ = self.pedir("/api/fontes", {
            "nome": "Nome Ruim", "fonte": {"base_url": "https://x"}})
        self.assertEqual(status, 400)
        self.assertIn("identificador", json.loads(corpo)["erro"])
        self.assertEqual(self.pedir("/api/nada")[0], 404)
        self.assertEqual(
            self.pedir("/arquivo?fonte=..&endpoint=segredos")[0], 400)
        self.assertEqual(self.pedir("/api/previa?fonte=a&endpoint=b")[0], 404)
        # Pedido que não é JSON (ex.: formulário de outra página) é recusado.
        self.assertEqual(self.pedir("/api/fontes/excluir", {"nome": "a"},
                                    {"Content-Type": "text/plain"})[0], 415)
        # Acesso por outro nome de host é recusado.
        self.assertEqual(self.pedir("/api/estado",
                                    cabecalhos={"Host": "malicioso.com"})[0],
                         403)
        status, corpo, _ = self.pedir("/api/testar", {
            "nome": "s", "fonte": self.fonte,
            "endpoint": {"caminho": "/nao_existe"}})
        self.assertEqual(status, 400)
        self.assertIn("404", json.loads(corpo)["erro"])


if __name__ == "__main__":
    unittest.main()
