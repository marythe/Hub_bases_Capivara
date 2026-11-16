"""Servidor web local: entrega a tela (HTML) e a API usada por ela.

Só aceita conexões do próprio computador (127.0.0.1).
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import conectores as con
from .armazenamento import Armazenamento

PAGINA = Path(__file__).parent / "web" / "index.html"
HOSTS_LOCAIS = ("127.0.0.1", "localhost", "[::1]")
LINHAS_TESTE = 20


class ErroPedido(Exception):
    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.status = status


def criar_servidor(raiz=".", porta=8000, qualquer_host=False):
    arm = Armazenamento(raiz)

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "PlataformaDeDados"

        def log_message(self, formato, *args):
            pass

        # --------------------------------------------------- respostas ----

        def _enviar(self, status, corpo, tipo, extras=None):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for chave, valor in (extras or {}).items():
                self.send_header(chave, valor)
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, dado, status=200):
            corpo = json.dumps(dado, ensure_ascii=False).encode("utf-8")
            self._enviar(status, corpo, "application/json; charset=utf-8")

        def _corpo_json(self):
            # Exigir JSON impede que outra página envie formulários para cá.
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise ErroPedido("Envie o pedido como application/json.", 415)
            tamanho = int(self.headers.get("Content-Length") or 0)
            try:
                dado = json.loads(self.rfile.read(tamanho) or b"{}")
            except json.JSONDecodeError:
                raise ErroPedido("JSON inválido.") from None
            if not isinstance(dado, dict):
                raise ErroPedido("JSON inválido.")
            return dado

        def _host_ok(self):
            if qualquer_host:
                return True
            host = self.headers.get("Host", "")
            return host.rsplit(":", 1)[0] in HOSTS_LOCAIS

        def _atender(self, rotas):
            if not self._host_ok():
                return self._json({"erro": "Acesso permitido só neste "
                                           "computador."}, 403)
            url = urlsplit(self.path)
            consulta = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                rota = rotas.get(url.path)
                if rota is None:
                    raise ErroPedido("Endereço não encontrado.", 404)
                rota(consulta)
            except ErroPedido as e:
                self._json({"erro": str(e)}, e.status)
            except (con.ErroConfig, con.ErroDownload) as e:
                self._json({"erro": str(e)}, 400)
            except FileNotFoundError:
                self._json({"erro": "Arquivo não encontrado."}, 404)

        def do_GET(self):
            self._atender({
                "/": self.pagina,
                "/api/estado": self.estado,
                "/api/dados": lambda c: self._json(arm.arquivos()),
                "/api/historico": lambda c: self._json(arm.historico()),
                "/api/previa": self.previa,
                "/arquivo": self.arquivo,
            })

        def do_POST(self):
            self._atender({
                "/api/fontes": self.salvar_fonte,
                "/api/fontes/excluir": self.excluir_fonte,
                "/api/testar": self.testar,
                "/api/baixar": self.baixar,
            })

        # ------------------------------------------------------- rotas ----

        def pagina(self, consulta):
            self._enviar(200, PAGINA.read_bytes(), "text/html; charset=utf-8")

        def estado(self, consulta):
            self._json({"fontes": arm.fontes(),
                        "segredos_definidos": arm.segredos_definidos()})

        def previa(self, consulta):
            self._json(arm.previa(consulta.get("fonte"),
                                  consulta.get("endpoint")))

        def arquivo(self, consulta):
            caminho = arm.caminho_csv(consulta.get("fonte"),
                                      consulta.get("endpoint"))
            nome = f"{caminho.parent.name}_{caminho.name}"
            self._enviar(200, caminho.read_bytes(), "text/csv; charset=utf-8",
                         {"Content-Disposition":
                          f'attachment; filename="{nome}"'})

        def salvar_fonte(self, consulta):
            dado = self._corpo_json()
            arm.salvar_fonte(dado.get("nome"), dado.get("fonte"),
                             dado.get("segredos"))
            self._json({"ok": True})

        def excluir_fonte(self, consulta):
            dado = self._corpo_json()
            con.validar_nome(dado.get("nome"), "Site")
            arm.excluir_fonte(dado["nome"])
            self._json({"ok": True})

        def testar(self, consulta):
            """Busca só a 1ª página, sem gravar nada, para conferir."""
            dado = self._corpo_json()
            nome, fonte = dado.get("nome") or "teste", dado.get("fonte")
            endpoint = dado.get("endpoint")
            fonte_teste = dict(fonte or {}, endpoints={})
            con.validar_fonte(nome, fonte_teste)
            con.validar_endpoint("teste", endpoint)
            segredos = dict(arm.segredos(nome))
            segredos.update({k: v for k, v in
                             (dado.get("segredos") or {}).items() if v})
            linhas, _ = con.baixar_endpoint(fonte_teste, endpoint, segredos,
                                            nome, max_paginas=1)
            colunas = con.colunas_de(linhas)
            self._json({
                "total": len(linhas), "colunas": colunas,
                "linhas": [[linha.get(c) for c in colunas]
                           for linha in linhas[:LINHAS_TESTE]],
            })

        def baixar(self, consulta):
            dado = self._corpo_json()
            self._json(arm.baixar(dado.get("fonte"), dado.get("endpoint")))

    return ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
