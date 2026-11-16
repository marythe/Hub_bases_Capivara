"""Guarda a configuração dos sites, as credenciais e os dados baixados.

  config/fontes.json     sites e conjuntos de dados (vai para o Git)
  config/segredos.json   credenciais (NÃO vai para o Git)
  dados/<site>/<conjunto>.csv   dados baixados
  dados/_historico.csv   registro de cada download
"""

import csv
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from . import conectores as con

CAMPOS_HISTORICO = ["quando", "fonte", "endpoint", "status", "linhas",
                    "mensagem"]


class Armazenamento:
    def __init__(self, raiz="."):
        raiz = Path(raiz)
        self.arq_fontes = raiz / "config" / "fontes.json"
        self.arq_segredos = raiz / "config" / "segredos.json"
        self.pasta_dados = raiz / "dados"
        self.arq_historico = self.pasta_dados / "_historico.csv"
        self._trava = threading.Lock()

    # ------------------------------------------------------------ json ----

    @staticmethod
    def _ler_json(arquivo):
        if not arquivo.exists():
            return {}
        with open(arquivo, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _gravar_json(arquivo, dado, privado=False):
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        temp = arquivo.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if privado:
            os.chmod(temp, 0o600)
        os.replace(temp, arquivo)

    # ---------------------------------------------------------- fontes ----

    def fontes(self):
        return self._ler_json(self.arq_fontes).get("fontes", {})

    def segredos(self, nome_fonte):
        return self._ler_json(self.arq_segredos).get(nome_fonte, {})

    def segredos_definidos(self):
        """{site: [campos preenchidos]} — nunca devolve os valores."""
        return {nome: sorted(k for k, v in campos.items() if v)
                for nome, campos in self._ler_json(self.arq_segredos).items()}

    def salvar_fonte(self, nome, fonte, novos_segredos=None):
        con.validar_fonte(nome, fonte)
        with self._trava:
            config = self._ler_json(self.arq_fontes)
            config.setdefault("fontes", {})[nome] = fonte
            self._gravar_json(self.arq_fontes, config)

            # Campos em branco mantêm a credencial já guardada.
            tipo = (fonte.get("auth") or {}).get("tipo", "nenhuma")
            todos = self._ler_json(self.arq_segredos)
            atuais = todos.get(nome, {})
            atuais.update({k: v for k, v in (novos_segredos or {}).items()
                           if v})
            atuais = {k: v for k, v in atuais.items()
                      if k in con.CAMPOS_SEGREDO[tipo]}
            if atuais:
                todos[nome] = atuais
            else:
                todos.pop(nome, None)
            if todos or self.arq_segredos.exists():
                self._gravar_json(self.arq_segredos, todos, privado=True)

    def excluir_fonte(self, nome):
        with self._trava:
            config = self._ler_json(self.arq_fontes)
            config.get("fontes", {}).pop(nome, None)
            self._gravar_json(self.arq_fontes, config)
            todos = self._ler_json(self.arq_segredos)
            if todos.pop(nome, None) is not None:
                self._gravar_json(self.arq_segredos, todos, privado=True)

    # ----------------------------------------------------------- dados ----

    def caminho_csv(self, nome_fonte, nome_endpoint):
        con.validar_nome(nome_fonte, "Site")
        con.validar_nome(nome_endpoint, "Conjunto de dados")
        return self.pasta_dados / nome_fonte / f"{nome_endpoint}.csv"

    def salvar_linhas(self, nome_fonte, nome_endpoint, linhas):
        """Grava em CSV com ';' e UTF-8 com BOM (abre direto no Excel)."""
        arquivo = self.caminho_csv(nome_fonte, nome_endpoint)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        temp = arquivo.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=con.colunas_de(linhas),
                                      delimiter=";", restval="")
            escritor.writeheader()
            for linha in linhas:
                escritor.writerow({k: ("" if v is None else v)
                                   for k, v in linha.items()})
        os.replace(temp, arquivo)
        return arquivo

    def registrar(self, nome_fonte, nome_endpoint, status, linhas, mensagem):
        item = {
            "quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fonte": nome_fonte, "endpoint": nome_endpoint, "status": status,
            "linhas": "" if linhas is None else linhas,
            "mensagem": " ".join(str(mensagem or "").split()),
        }
        with self._trava:
            self.pasta_dados.mkdir(parents=True, exist_ok=True)
            novo = not self.arq_historico.exists()
            with open(self.arq_historico, "a", encoding="utf-8",
                      newline="") as f:
                escritor = csv.DictWriter(f, fieldnames=CAMPOS_HISTORICO)
                if novo:
                    escritor.writeheader()
                escritor.writerow(item)
        return item

    def historico(self, limite=200):
        if not self.arq_historico.exists():
            return []
        with open(self.arq_historico, encoding="utf-8", newline="") as f:
            itens = list(csv.DictReader(f))
        return itens[::-1][:limite]

    def arquivos(self):
        """Lista os CSVs baixados, com o nº de linhas do último download."""
        ultimo = {}
        for item in self.historico(limite=10 ** 9)[::-1]:
            if item["status"] == "ok":
                ultimo[(item["fonte"], item["endpoint"])] = item
        lista = []
        if self.pasta_dados.exists():
            for arq in sorted(self.pasta_dados.glob("*/*.csv")):
                chave = (arq.parent.name, arq.stem)
                info = arq.stat()
                lista.append({
                    "fonte": chave[0], "endpoint": chave[1],
                    "tamanho": info.st_size,
                    "modificado": datetime.fromtimestamp(
                        info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "linhas": ultimo.get(chave, {}).get("linhas", ""),
                })
        return lista

    def previa(self, nome_fonte, nome_endpoint, limite=50):
        arquivo = self.caminho_csv(nome_fonte, nome_endpoint)
        if not arquivo.exists():
            raise FileNotFoundError(arquivo)
        with open(arquivo, encoding="utf-8-sig", newline="") as f:
            leitor = csv.reader(f, delimiter=";")
            colunas = next(leitor, [])
            linhas = [linha for _, linha in zip(range(limite), leitor)]
        return {"colunas": colunas, "linhas": linhas}

    # -------------------------------------------------------- download ----

    def baixar(self, nome_fonte, nome_endpoint):
        """Baixa um conjunto, grava o CSV e registra no histórico."""
        try:
            fonte = self.fontes().get(nome_fonte)
            if fonte is None:
                raise con.ErroConfig(f"Site não configurado: {nome_fonte}")
            endpoint = (fonte.get("endpoints") or {}).get(nome_endpoint)
            if endpoint is None:
                raise con.ErroConfig(
                    f"O conjunto '{nome_endpoint}' não existe no site "
                    f"'{nome_fonte}'.")
            linhas, aviso = con.baixar_endpoint(
                fonte, endpoint, self.segredos(nome_fonte), nome_fonte)
            self.salvar_linhas(nome_fonte, nome_endpoint, linhas)
            return self.registrar(nome_fonte, nome_endpoint, "ok",
                                  len(linhas), aviso or "")
        except (con.ErroConfig, con.ErroDownload, OSError) as e:
            return self.registrar(nome_fonte, nome_endpoint, "erro", None, e)

    def baixar_tudo(self, nome_fonte=None, nome_endpoint=None):
        fontes = self.fontes()
        if nome_fonte is not None and nome_fonte not in fontes:
            raise con.ErroConfig(f"Site não configurado: {nome_fonte}")
        resultados = []
        for nome in ([nome_fonte] if nome_fonte else fontes):
            endpoints = list(fontes[nome].get("endpoints") or {})
            if nome_endpoint is not None:
                if nome_endpoint not in endpoints:
                    raise con.ErroConfig(
                        f"O conjunto '{nome_endpoint}' não existe no site "
                        f"'{nome}'.")
                endpoints = [nome_endpoint]
            for ep in endpoints:
                resultados.append(self.baixar(nome, ep))
        return resultados
