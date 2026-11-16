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
import ssl
import time
import urllib.error
import urllib.request
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

NOME_VALIDO = re.compile(r"^[a-z0-9_]+$")
TIPOS_AUTH = ("nenhuma", "bearer", "api_key", "basic")
TIPOS_PAGINACAO = ("nenhuma", "pagina", "offset", "cursor")
TIPOS_CONJUNTO = ("tabela", "arquivo", "pagina", "ckan")
TIPOS_ARQUIVO = ("arquivo", "pagina", "ckan")
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
    tipo_conjunto = ep.get("tipo", "tabela")
    if tipo_conjunto not in TIPOS_CONJUNTO:
        raise ErroConfig(onde + f"tipo desconhecido: '{tipo_conjunto}'.")
    if tipo_conjunto == "ckan" and not ep.get("dataset"):
        raise ErroConfig(onde + "informe o identificador do conjunto no "
                         "portal CKAN (campo 'dataset').")
    if ep.get("metodo", "GET") not in ("GET", "POST"):
        raise ErroConfig(onde + "o método deve ser GET ou POST.")
    for campo in ("corpo", "filtro", "dataset"):
        if not isinstance(ep.get(campo) or "", str):
            raise ErroConfig(onde + f"'{campo}' deve ser um texto.")
    maximo = ep.get("max_arquivos")
    if maximo is not None and (not isinstance(maximo, int)
                               or isinstance(maximo, bool) or maximo < 1):
        raise ErroConfig(onde + "'max_arquivos' deve ser um número inteiro.")
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
    if not isinstance(base, str) or not re.match(r"^(https?|ftp)://[^/\s]+",
                                                 base):
        raise ErroConfig(onde + "informe o endereço (URL base) começando com "
                         "http://, https:// ou ftp://.")
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


_MARCADOR_DATA = re.compile(r"\{(AAAA-MM|AAAAMM|AAAA|MM)(?::(-?\d+))?\}")


def preencher_datas(texto, hoje=None):
    """Troca marcadores pela data do dia do download, para endereços que
    mudam todo mês: {AAAA}, {MM}, {AAAA-MM}, {AAAAMM}. Um número depois de
    ':' desloca em meses (ou anos, no caso de {AAAA}): {AAAA-MM:-1} é o mês
    passado."""
    hoje = hoje or date.today()

    def trocar(m):
        formato, desloc = m.group(1), int(m.group(2) or 0)
        if formato == "AAAA":
            return str(hoje.year + desloc)
        meses = hoje.year * 12 + hoje.month - 1 + desloc
        ano, mes = divmod(meses, 12)
        return {"AAAA-MM": f"{ano}-{mes + 1:02d}", "AAAAMM": f"{ano}{mes + 1:02d}",
                "MM": f"{mes + 1:02d}"}[formato]

    return _MARCADOR_DATA.sub(trocar, texto)


def montar_url(fonte, endpoint):
    base = fonte["base_url"].rstrip("/")
    caminho = preencher_datas((endpoint.get("caminho") or "").lstrip("/"))
    url = f"{base}/{caminho}" if caminho else base
    params = {k: preencher_datas(str(v))
              for k, v in (endpoint.get("params") or {}).items()}
    return com_params(url, params)


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


def abrir(req, timeout=60, verificar_ssl=True):
    """urlopen com a opção de aceitar certificados que o Python não
    reconhece (comum em alguns sites do governo)."""
    contexto = None
    if not verificar_ssl:
        contexto = ssl.create_default_context()
        contexto.check_hostname = False
        contexto.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(req, timeout=timeout, context=contexto)


def explicar_erro(e):
    motivo = getattr(e, "reason", e)
    if isinstance(motivo, ssl.SSLCertVerificationError):
        return ("o certificado de segurança do site não foi reconhecido. "
                "Se o endereço estiver correto, marque a opção 'Aceitar "
                "certificado não reconhecido' no cadastro do site")
    return str(motivo)


def requisitar(url, cabecalhos, timeout=60, tentativas=3, espera=1.0,
               metodo="GET", corpo=None, verificar_ssl=True):
    """Requisição com novas tentativas em falhas temporárias. Devolve os
    bytes da resposta."""
    ultimo_erro = None
    dados = None
    if metodo == "POST":
        dados = (corpo or "").encode("utf-8")
        cabecalhos = dict({"Content-Type": "application/json"}, **cabecalhos)
    for tentativa in range(1, max(1, tentativas) + 1):
        req = urllib.request.Request(url, data=dados, headers=cabecalhos,
                                     method=metodo)
        try:
            with abrir(req, timeout, verificar_ssl) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            ultimo_erro = ErroDownload(
                f"O site respondeu com erro HTTP {e.code} ({e.reason}).")
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            ultimo_erro = ErroDownload(
                f"Não foi possível conectar ao site: {explicar_erro(e)}.")
        if tentativa < tentativas:
            time.sleep(espera * tentativa)
    raise ultimo_erro


# -------------------------------------------------------------- resposta ----

def pegar_caminho(dado, caminho):
    """Navega no JSON por um caminho com pontos, ex.: 'data.items'."""
    if not caminho:
        return dado
    for parte in caminho.split("."):
        if isinstance(dado, list) and parte.isdigit():
            dado = dado[int(parte)] if int(parte) < len(dado) else None
        elif isinstance(dado, dict):
            dado = dado.get(parte)
        else:
            return None
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
            if tamanho and pag.get("param_tamanho"):
                extras[pag["param_tamanho"]] = tamanho
        elif tipo == "offset":
            extras[pag.get("param") or "offset"] = deslocamento
            if tamanho and pag.get("param_tamanho"):
                extras[pag["param_tamanho"]] = tamanho
        elif tipo == "cursor" and cursor is not None:
            extras[pag.get("param") or "cursor"] = cursor
        url = com_params(url, extras)
        url, cab = aplicar_auth(url, cabecalhos, fonte, segredos, nome_fonte)

        corpo, novas = ler_resposta(
            requisitar(url, cab, timeout=timeout, tentativas=tentativas,
                       metodo=endpoint.get("metodo", "GET"),
                       corpo=endpoint.get("corpo"),
                       verificar_ssl=fonte.get("verificar_ssl", True)),
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
