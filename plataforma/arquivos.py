"""Download de arquivos "como estão" (ZIP, XLSX, CSV, TXT...).

Três formas de encontrar os arquivos de um conjunto:
  arquivo  um endereço fixo;
  pagina   todos os links de arquivo de uma página HTML (com filtro);
  ckan     os recursos de um conjunto num portal CKAN (com filtro).
"""

import hashlib
import json
import re
import urllib.error
import urllib.request
from email.message import Message
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from . import conectores as con

EXTENSOES = (".csv", ".zip", ".xlsx", ".xls", ".ods", ".txt", ".7z", ".rar",
             ".gz", ".json", ".xml", ".parquet", ".dbc", ".dbf", ".tsv")
MAX_ARQUIVOS_PADRAO = 20
BLOCO = 1024 * 1024


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._atual = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._atual = [href, ""]

    def handle_data(self, data):
        if self._atual is not None:
            self._atual[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._atual is not None:
            self.links.append((self._atual[0], " ".join(self._atual[1].split())))
            self._atual = None


def url_segura(url):
    """Codifica espaços e acentos que alguns sites deixam nos links."""
    p = urlsplit(url.strip())
    return urlunsplit(p._replace(path=quote(p.path, safe="/%:@+,;=~()!*'$&"),
                                 query=quote(p.query, safe="=&%:@+,;/?~()!*'$")))


def extrair_links(html, url_pagina):
    leitor = _Links()
    leitor.feed(html)
    vistos, links = set(), []
    for href, texto in leitor.links:
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = url_segura(urljoin(url_pagina, href))
        if url.startswith(("http://", "https://")) and url not in vistos:
            vistos.add(url)
            links.append({"url": url, "texto": texto})
    return links


def parece_arquivo(url):
    caminho = urlsplit(url).path.lower()
    caminho = re.sub(r"/(view|@@download(/file)?|download)$", "", caminho)
    return caminho.endswith(EXTENSOES)


def passa_no_filtro(filtro, *textos):
    """Filtro: termos separados por vírgula; basta um deles aparecer.
    Dentro de um termo, palavras separadas por espaço devem aparecer todas."""
    termos = [t.strip().lower() for t in (filtro or "").split(",") if t.strip()]
    if not termos:
        return True
    alvo = " ".join(unquote(t or "") for t in textos).lower()
    return any(all(p in alvo for p in termo.split()) for termo in termos)


def nome_de_arquivo(url, content_disposition=None):
    nome = None
    if content_disposition:
        msg = Message()
        msg["content-disposition"] = content_disposition
        nome = msg.get_filename()
    if not nome:
        partes = [p for p in urlsplit(url).path.split("/")
                  if p and p not in ("view", "@@download", "file", "download")]
        nome = unquote(partes[-1]) if partes else ""
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", nome).strip("._")
    return nome[:150] or "arquivo"


def _cabecalhos(fonte):
    cab = {"User-Agent": "plataforma-de-dados", "Accept": "*/*"}
    cab.update(fonte.get("cabecalhos") or {})
    return cab


def listar_candidatos(fonte, endpoint, segredos=None, nome_fonte=""):
    """Devolve [{'url', 'nome', 'texto'}] dos arquivos do conjunto."""
    tipo = endpoint.get("tipo")
    filtro = endpoint.get("filtro")
    timeout = fonte.get("timeout_segundos") or 60
    verificar = fonte.get("verificar_ssl", True)
    url = con.montar_url(fonte, endpoint)
    url, cab = con.aplicar_auth(url, _cabecalhos(fonte), fonte, segredos,
                                nome_fonte)

    if tipo == "arquivo":
        return [{"url": url_segura(url), "nome": nome_de_arquivo(url),
                 "texto": ""}]

    if tipo == "pagina":
        bruto = con.requisitar(url, cab, timeout=timeout,
                               tentativas=fonte.get("tentativas") or 3,
                               verificar_ssl=verificar)
        html = bruto.decode(endpoint.get("codificacao") or "utf-8",
                            errors="replace")
        achados = []
        for link in extrair_links(html, url):
            if filtro:
                ok = passa_no_filtro(filtro, link["url"], link["texto"])
            else:
                ok = parece_arquivo(link["url"])
            if ok:
                link["nome"] = nome_de_arquivo(link["url"])
                achados.append(link)
        return achados

    if tipo == "ckan":
        base = fonte["base_url"].rstrip("/")
        api = con.com_params(base + "/api/3/action/package_show",
                             {"id": endpoint.get("dataset") or ""})
        bruto = con.requisitar(api, cab, timeout=timeout,
                               tentativas=fonte.get("tentativas") or 3,
                               verificar_ssl=verificar)
        try:
            recursos = json.loads(bruto)["result"]["resources"]
        except (ValueError, KeyError, TypeError):
            raise con.ErroDownload(
                "O portal não respondeu como um catálogo CKAN.") from None
        achados = []
        for r in recursos:
            if not r.get("url"):
                continue
            texto = f"{r.get('name') or ''} [{r.get('format') or ''}]"
            if passa_no_filtro(filtro, r["url"], texto):
                achados.append({"url": url_segura(r["url"]), "texto": texto,
                                "nome": nome_de_arquivo(r["url"])})
        return achados

    raise con.ErroConfig(f"Tipo de conjunto desconhecido: '{tipo}'.")


def candidatos_em_ordem(fonte, endpoint, segredos=None, nome_fonte=""):
    achados = listar_candidatos(fonte, endpoint, segredos, nome_fonte)
    if endpoint.get("mais_novos_no_fim"):
        achados.reverse()
    return achados


def assinatura(url, cabecalhos, timeout=60, verificar_ssl=True):
    """Identifica a versão do arquivo sem baixá-lo (HEAD). '' se o site
    não informar nada útil."""
    if not url.startswith(("http://", "https://")):
        return ""
    req = urllib.request.Request(url, headers=cabecalhos, method="HEAD")
    try:
        with con.abrir(req, timeout, verificar_ssl) as resp:
            partes = [resp.headers.get(c) or "" for c in
                      ("ETag", "Last-Modified", "Content-Length")]
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return ""
    return "|".join(partes) if any(partes[:2]) or partes[2] not in ("", "0") \
        else ""


def baixar_para(url, cabecalhos, destino, timeout=60, limite_bytes=None,
                verificar_ssl=True):
    """Grava o conteúdo de 'url' em 'destino' sem carregar tudo na memória.
    Devolve (sha256, tamanho, nome_sugerido)."""
    req = urllib.request.Request(url, headers=cabecalhos, method="GET")
    resumo = hashlib.sha256()
    tamanho = 0
    try:
        with con.abrir(req, timeout, verificar_ssl) as resp, \
                open(destino, "wb") as f:
            nome = nome_de_arquivo(url,
                                   resp.headers.get("Content-Disposition"))
            while True:
                bloco = resp.read(BLOCO)
                if not bloco:
                    break
                tamanho += len(bloco)
                if limite_bytes and tamanho > limite_bytes:
                    raise con.ErroDownload(
                        "O arquivo passou do tamanho máximo configurado "
                        f"({limite_bytes // (1024 * 1024)} MB).")
                resumo.update(bloco)
                f.write(bloco)
    except urllib.error.HTTPError as e:
        raise con.ErroDownload(
            f"O site respondeu com erro HTTP {e.code} ({e.reason}).") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise con.ErroDownload(
            f"Não foi possível baixar o arquivo: {con.explicar_erro(e)}."
        ) from None
    return resumo.hexdigest(), tamanho, nome
