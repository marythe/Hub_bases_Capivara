"""Motor genérico de conexão com APIs.

Recebe a configuração de um site (URL base, autenticação) e de um conjunto
de dados (caminho, parâmetros, paginação), faz as requisições e devolve as
linhas como uma lista de dicionários. Usa apenas a biblioteca padrão.
"""

import base64
import csv
import io
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

NOME_VALIDO = re.compile(r"^[a-z0-9_]+$")
TIPOS_AUTH = ("nenhuma", "bearer", "api_key", "basic")
TIPOS_PAGINACAO = ("nenhuma", "pagina", "offset", "cursor")
CAMPOS_SEGREDO = {
    "nenhuma": (),
    "bearer": ("token",),
    "api_key": ("chave",),
    "basic": ("usuario", "senha"),
}
MAX_PAGINAS_PADRAO = 1000


class ErroConfig(ValueError):
    """Configuração inválida; a mensagem é mostrada ao usuário."""


class ErroDownload(RuntimeError):
    """Falha ao baixar ou interpretar os dados de um site."""


# ---------------------------------------------------------------- config ----

def validar_nome(nome, o_que):
    if not isinstance(nome, str) or not NOME_VALIDO.match(nome):
        raise ErroConfig(
            f"{o_que}: o identificador '{nome}' é inválido. Use apenas letras "
            "minúsculas, números e '_' (ex.: ibge_sidra).")


def validar_endpoint(nome, ep, onde=""):
    validar_nome(nome, f"{onde}Conjunto de dados")
    onde = f"{onde}conjunto '{nome}': "
    if not isinstance(ep, dict):
        raise ErroConfig(onde + "configuração inválida.")
    if not isinstance(ep.get("caminho", ""), str):
        raise ErroConfig(onde + "'caminho' deve ser um texto.")
    if not isinstance(ep.get("params") or {}, dict):
        raise ErroConfig(onde + "'params' deve ser uma lista de chave e valor.")
    if ep.get("formato_resposta", "json") not in ("json", "csv"):
        raise ErroConfig(onde + "o formato da resposta deve ser json ou csv.")
    pag = ep.get("paginacao") or {}
    tipo = pag.get("tipo", "nenhuma")
    if tipo not in TIPOS_PAGINACAO:
        raise ErroConfig(onde + f"tipo de paginação desconhecido: '{tipo}'.")
    if tipo == "cursor" and not pag.get("campo_proximo"):
        raise ErroConfig(onde + "a paginação por cursor exige o campo "
                         "'campo_proximo'.")
    for campo in ("tamanho", "inicio", "max_paginas"):
        valor = pag.get(campo)
        if valor is not None and (not isinstance(valor, int)
                                  or isinstance(valor, bool) or valor < 0):
            raise ErroConfig(onde + f"'{campo}' deve ser um número inteiro.")


def validar_fonte(nome, fonte):
    validar_nome(nome, "Site")
    onde = f"Site '{nome}': "
    if not isinstance(fonte, dict):
        raise ErroConfig(onde + "configuração inválida.")
    base = fonte.get("base_url")
    if not isinstance(base, str) or not re.match(r"^https?://[^/\s]+", base):
        raise ErroConfig(onde + "informe o endereço (URL base) começando com "
                         "http:// ou https://.")
    tipo = (fonte.get("auth") or {}).get("tipo", "nenhuma")
    if tipo not in TIPOS_AUTH:
        raise ErroConfig(onde + f"tipo de autenticação desconhecido: '{tipo}'.")
    endpoints = fonte.get("endpoints") or {}
    if not isinstance(endpoints, dict):
        raise ErroConfig(onde + "'endpoints' inválido.")
    for nome_ep, ep in endpoints.items():
        validar_endpoint(nome_ep, ep, onde)


# ------------------------------------------------------------ requisição ----

def com_params(url, extras):
    """Acrescenta (ou substitui) parâmetros na query string de uma URL."""
    if not extras:
        return url
    partes = urlsplit(url)
    extras = {str(k): str(v) for k, v in extras.items()}
    atuais = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
              if k not in extras]
    query = urlencode(atuais + list(extras.items()))
    return urlunsplit(partes._replace(query=query))


def montar_url(fonte, endpoint):
    base = fonte["base_url"].rstrip("/")
    caminho = (endpoint.get("caminho") or "").lstrip("/")
    url = f"{base}/{caminho}" if caminho else base
    return com_params(url, endpoint.get("params") or {})


def _segredo(segredos, campo, nome_fonte):
    valor = (segredos or {}).get(campo)
    if not valor:
        raise ErroConfig(
            f"Site '{nome_fonte}': falta preencher a credencial '{campo}'.")
    return valor


def aplicar_auth(url, cabecalhos, fonte, segredos, nome_fonte=""):
    """Devolve (url, cabecalhos) com a autenticação do site aplicada."""
    auth = fonte.get("auth") or {}
    tipo = auth.get("tipo", "nenhuma")
    cabecalhos = dict(cabecalhos)
    if tipo == "bearer":
        token = _segredo(segredos, "token", nome_fonte)
        cabecalhos["Authorization"] = f"Bearer {token}"
    elif tipo == "basic":
        par = (f"{_segredo(segredos, 'usuario', nome_fonte)}:"
               f"{_segredo(segredos, 'senha', nome_fonte)}")
        cabecalhos["Authorization"] = (
            "Basic " + base64.b64encode(par.encode("utf-8")).decode("ascii"))
    elif tipo == "api_key":
        chave = _segredo(segredos, "chave", nome_fonte)
        nome = auth.get("nome") or "X-API-Key"
        if auth.get("onde", "header") == "query":
            url = com_params(url, {nome: chave})
        else:
            prefixo = auth.get("prefixo")
            cabecalhos[nome] = f"{prefixo} {chave}" if prefixo else chave
    return url, cabecalhos


def requisitar(url, cabecalhos, timeout=60, tentativas=3, espera=1.0):
    """GET com novas tentativas em falhas temporárias. Devolve os bytes."""
    ultimo_erro = None
    for tentativa in range(1, max(1, tentativas) + 1):
        req = urllib.request.Request(url, headers=cabecalhos, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            ultimo_erro = ErroDownload(
                f"O site respondeu com erro HTTP {e.code} ({e.reason}).")
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            motivo = getattr(e, "reason", e)
            ultimo_erro = ErroDownload(
                f"Não foi possível conectar ao site: {motivo}.")
        if tentativa < tentativas:
            time.sleep(espera * tentativa)
    raise ultimo_erro


# -------------------------------------------------------------- resposta ----

def pegar_caminho(dado, caminho):
    """Navega no JSON por um caminho com pontos, ex.: 'data.items'."""
    if not caminho:
        return dado
    for parte in caminho.split("."):
        if not isinstance(dado, dict):
            return None
        dado = dado.get(parte)
    return dado


def achatar(registro, prefixo=""):
    """{'a': {'b': 1}} -> {'a.b': 1}; listas viram texto JSON."""
    linha = {}
    for chave, valor in registro.items():
        nome = f"{prefixo}{chave}"
        if isinstance(valor, dict):
            linha.update(achatar(valor, nome + "."))
        elif isinstance(valor, list):
            linha[nome] = json.dumps(valor, ensure_ascii=False)
        else:
            linha[nome] = valor
    return linha


def para_linhas(dado):
    if dado is None:
        return []
    if isinstance(dado, dict):
        return [achatar(dado)]
    if isinstance(dado, list):
        linhas = []
        for item in dado:
            if isinstance(item, dict):
                linhas.append(achatar(item))
            elif isinstance(item, list):
                linhas.append({f"coluna_{i + 1}": v for i, v in enumerate(item)})
            else:
                linhas.append({"valor": item})
        return linhas
    return [{"valor": dado}]


def ler_resposta(conteudo, endpoint):
    """Devolve (corpo_json_ou_None, linhas)."""
    codificacao = endpoint.get("codificacao") or "utf-8-sig"
    try:
        texto = conteudo.decode(codificacao)
    except (UnicodeDecodeError, LookupError):
        raise ErroDownload(
            f"Não foi possível ler a resposta com a codificação "
            f"'{codificacao}'. Tente 'latin1' ou 'utf-8'.") from None

    if endpoint.get("formato_resposta", "json") == "csv":
        leitor = csv.DictReader(io.StringIO(texto),
                                delimiter=endpoint.get("separador") or ",")
        linhas = [{k: v for k, v in linha.items() if k is not None}
                  for linha in leitor]
        return None, linhas

    try:
        corpo = json.loads(texto)
    except json.JSONDecodeError:
        raise ErroDownload(
            "A resposta do site não é um JSON válido. Se o site entrega um "
            "arquivo CSV, mude o formato da resposta para 'csv'.") from None
    linhas = para_linhas(pegar_caminho(corpo, endpoint.get("registros")))
    # Algumas APIs (ex.: SIDRA/IBGE) mandam os nomes das colunas na 1ª linha.
    if endpoint.get("primeira_linha_cabecalho") and linhas:
        titulos = {k: str(v) for k, v in linhas[0].items()}
        linhas = [{titulos.get(k, k): v for k, v in linha.items()}
                  for linha in linhas[1:]]
    return corpo, linhas


# ------------------------------------------------------------- download ----

def baixar_endpoint(fonte, endpoint, segredos=None, nome_fonte="",
                    max_paginas=None):
    """Baixa um conjunto de dados, seguindo a paginação.

    Devolve (linhas, aviso). 'aviso' é um texto quando o limite de páginas
    foi atingido e pode haver mais dados; senão, None.
    """
    pag = endpoint.get("paginacao") or {}
    tipo = pag.get("tipo", "nenhuma")
    limite = max_paginas or pag.get("max_paginas") or MAX_PAGINAS_PADRAO
    tamanho = pag.get("tamanho")
    timeout = fonte.get("timeout_segundos") or 60
    tentativas = fonte.get("tentativas") or 3

    cabecalhos = {"User-Agent": "plataforma-de-dados", "Accept": "*/*"}
    cabecalhos.update(fonte.get("cabecalhos") or {})
    url_base = montar_url(fonte, endpoint)

    pagina = pag.get("inicio", 1)
    deslocamento = 0
    cursor = None
    proxima_url = None
    linhas = []
    aviso = None

    for i in range(1, limite + 1):
        url = proxima_url or url_base
        extras = {}
        if tipo == "pagina":
            extras[pag.get("param") or "page"] = pagina
            if tamanho:
                extras[pag.get("param_tamanho") or "per_page"] = tamanho
        elif tipo == "offset":
            extras[pag.get("param") or "offset"] = deslocamento
            if tamanho:
                extras[pag.get("param_tamanho") or "limit"] = tamanho
        elif tipo == "cursor" and cursor is not None:
            extras[pag.get("param") or "cursor"] = cursor
        url = com_params(url, extras)
        url, cab = aplicar_auth(url, cabecalhos, fonte, segredos, nome_fonte)

        corpo, novas = ler_resposta(
            requisitar(url, cab, timeout=timeout, tentativas=tentativas),
            endpoint)
        linhas.extend(novas)

        if tipo == "nenhuma" or not novas:
            break
        if tipo == "pagina":
            if tamanho and len(novas) < tamanho:
                break
            pagina += 1
        elif tipo == "offset":
            if tamanho and len(novas) < tamanho:
                break
            deslocamento += len(novas)
        elif tipo == "cursor":
            proximo = pegar_caminho(corpo, pag.get("campo_proximo"))
            if proximo is None or proximo == "" or isinstance(proximo,
                                                               (dict, list)):
                break
            proximo = str(proximo)
            if re.match(r"^https?://", proximo):
                proxima_url, cursor = proximo, None
            else:
                cursor = proximo
        if i == limite:
            aviso = (f"Limite de {limite} página(s) atingido; pode haver "
                     "mais dados no site.")
    return linhas, aviso


def colunas_de(linhas):
    """União das colunas, na ordem em que aparecem."""
    colunas = {}
    for linha in linhas:
        for chave in linha:
            colunas.setdefault(chave, None)
    return list(colunas)
