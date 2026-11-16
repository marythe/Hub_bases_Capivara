# Motor genérico de conexão com APIs.
#
# Cada site é descrito em config/fontes.yml (URL base, autenticação,
# endpoints e paginação). Este arquivo lê essa configuração, faz as
# requisições e grava os dados em disco.

suppressPackageStartupMessages({
  library(httr2)
  library(jsonlite)
  library(yaml)
})

`%||%` <- function(a, b) if (is.null(a)) b else a

# ---------------------------------------------------------------- config ----

ler_config <- function(arquivo = "config/fontes.yml") {
  if (!file.exists(arquivo)) {
    stop("Arquivo de configuração não encontrado: ", arquivo, call. = FALSE)
  }
  linhas <- readLines(arquivo, encoding = "UTF-8", warn = FALSE)
  config <- yaml::yaml.load(paste(linhas, collapse = "\n"))
  validar_config(config)
  config
}

validar_config <- function(config) {
  fontes <- config$fontes
  if (!is.list(fontes) || length(fontes) == 0 || is.null(names(fontes))) {
    stop("A configuração precisa de uma seção 'fontes' com ao menos um site.",
         call. = FALSE)
  }
  for (nome in names(fontes)) {
    fonte <- fontes[[nome]]
    if (!is.character(fonte$base_url) || !nzchar(fonte$base_url)) {
      stop("Fonte '", nome, "': falta 'base_url'.", call. = FALSE)
    }
    if (!is.list(fonte$endpoints) || length(fonte$endpoints) == 0) {
      stop("Fonte '", nome, "': falta ao menos um item em 'endpoints'.",
           call. = FALSE)
    }
    tipo_auth <- fonte$auth$tipo %||% "nenhuma"
    if (!tipo_auth %in% c("nenhuma", "bearer", "api_key", "basic")) {
      stop("Fonte '", nome, "': auth.tipo desconhecido: '", tipo_auth,
           "'. Use nenhuma, bearer, api_key ou basic.", call. = FALSE)
    }
    for (nome_ep in names(fonte$endpoints)) {
      ep <- fonte$endpoints[[nome_ep]]
      onde <- paste0("Fonte '", nome, "', endpoint '", nome_ep, "': ")
      if (!is.character(ep$caminho)) {
        stop(onde, "falta 'caminho'.", call. = FALSE)
      }
      tipo_pag <- ep$paginacao$tipo %||% "nenhuma"
      if (!tipo_pag %in% c("nenhuma", "pagina", "offset", "cursor")) {
        stop(onde, "paginacao.tipo desconhecido: '", tipo_pag,
             "'. Use nenhuma, pagina, offset ou cursor.", call. = FALSE)
      }
      if (tipo_pag == "cursor" && is.null(ep$paginacao$campo_proximo)) {
        stop(onde, "paginação por cursor exige 'campo_proximo'.", call. = FALSE)
      }
      formato <- ep$formato_resposta %||% "json"
      if (!formato %in% c("json", "csv")) {
        stop(onde, "formato_resposta deve ser json ou csv.", call. = FALSE)
      }
    }
  }
  invisible(TRUE)
}

# Segredos nunca ficam no YAML: a configuração guarda só o NOME da variável
# de ambiente (definida no arquivo .Renviron).
ler_segredo <- function(variavel, fonte) {
  if (is.null(variavel) || !nzchar(variavel)) {
    stop("Fonte '", fonte, "': a autenticação não indica a variável de ",
         "ambiente com a credencial.", call. = FALSE)
  }
  valor <- Sys.getenv(variavel, unset = "")
  if (!nzchar(valor)) {
    stop("Fonte '", fonte, "': a variável de ambiente '", variavel,
         "' está vazia. Defina-a no arquivo .Renviron.", call. = FALSE)
  }
  valor
}

# ------------------------------------------------------------ requisição ----

aplicar_auth <- function(req, auth, fonte) {
  tipo <- auth$tipo %||% "nenhuma"
  if (tipo == "bearer") {
    req <- req_auth_bearer_token(req, ler_segredo(auth$token_env, fonte))
  } else if (tipo == "basic") {
    req <- req_auth_basic(req,
                          ler_segredo(auth$usuario_env, fonte),
                          ler_segredo(auth$senha_env, fonte))
  } else if (tipo == "api_key") {
    chave <- ler_segredo(auth$chave_env, fonte)
    nome <- auth$nome %||% "X-API-Key"
    if (identical(auth$onde %||% "header", "query")) {
      req <- req_url_query(req, !!!stats::setNames(list(chave), nome))
    } else {
      prefixo <- auth$prefixo
      if (!is.null(prefixo)) chave <- paste(prefixo, chave)
      req <- req_headers(req, !!!stats::setNames(list(chave), nome),
                         .redact = nome)
    }
  }
  req
}

montar_requisicao <- function(fonte, endpoint, nome_fonte) {
  url <- paste0(sub("/+$", "", fonte$base_url), "/",
                sub("^/+", "", endpoint$caminho))
  req <- request(url)
  req <- req_user_agent(req, "conector-apis-R")
  req <- req_timeout(req, fonte$timeout_segundos %||% 60)
  req <- req_retry(req, max_tries = fonte$tentativas %||% 3)

  cabecalhos <- c(fonte$cabecalhos, endpoint$cabecalhos)
  if (length(cabecalhos) > 0) req <- req_headers(req, !!!cabecalhos)

  params <- endpoint$params
  if (length(params) > 0) req <- req_url_query(req, !!!params)

  aplicar_auth(req, fonte$auth, nome_fonte)
}

# -------------------------------------------------------------- resposta ----

# Navega no JSON por um caminho com pontos, ex.: "data.items".
pegar_caminho <- function(x, caminho) {
  if (is.null(caminho) || !nzchar(caminho)) return(x)
  for (parte in strsplit(caminho, ".", fixed = TRUE)[[1]]) {
    if (is.null(x) || !is.list(x) || is.null(names(x))) return(NULL)
    x <- x[[parte]]
  }
  x
}

para_tabela <- function(x) {
  if (is.null(x) || length(x) == 0) return(data.frame())
  if (is.data.frame(x)) return(jsonlite::flatten(x))
  if (is.atomic(x)) return(data.frame(valor = x, stringsAsFactors = FALSE))
  if (is.list(x) && !is.null(names(x))) {
    # Um único objeto: vira uma linha; campos aninhados viram texto JSON.
    linha <- lapply(x, function(v) {
      if (is.null(v)) NA
      else if (is.atomic(v) && length(v) == 1) v
      else as.character(jsonlite::toJSON(v, auto_unbox = TRUE))
    })
    return(as.data.frame(linha, stringsAsFactors = FALSE, check.names = FALSE))
  }
  # Lista de objetos com formatos diferentes: converte um a um.
  empilhar(lapply(x, para_tabela))
}

# Junta páginas mesmo que as colunas não sejam idênticas entre elas.
empilhar <- function(tabelas) {
  tabelas <- Filter(function(t) nrow(t) > 0, tabelas)
  if (length(tabelas) == 0) return(data.frame())
  colunas <- unique(unlist(lapply(tabelas, names)))
  tabelas <- lapply(tabelas, function(t) {
    for (col in setdiff(colunas, names(t))) t[[col]] <- NA
    t[colunas]
  })
  resultado <- do.call(rbind, tabelas)
  rownames(resultado) <- NULL
  resultado
}

ler_resposta <- function(resp, endpoint) {
  texto <- resp_body_string(resp, encoding = endpoint$codificacao %||% "UTF-8")
  if (identical(endpoint$formato_resposta %||% "json", "csv")) {
    tabela <- utils::read.csv(text = texto, sep = endpoint$separador %||% ",",
                              stringsAsFactors = FALSE, check.names = FALSE)
    return(list(corpo = NULL, registros = tabela))
  }
  corpo <- jsonlite::fromJSON(texto, simplifyVector = TRUE)
  registros <- para_tabela(pegar_caminho(corpo, endpoint$registros))
  # Algumas APIs (ex.: SIDRA/IBGE) mandam os nomes das colunas como 1ª linha.
  if (isTRUE(endpoint$primeira_linha_cabecalho) && nrow(registros) > 0) {
    names(registros) <- make.unique(as.character(unlist(registros[1, ])))
    registros <- registros[-1, , drop = FALSE]
    rownames(registros) <- NULL
  }
  list(corpo = corpo, registros = registros)
}

# ------------------------------------------------------------- download ----

baixar_endpoint <- function(config, nome_fonte, nome_endpoint) {
  fonte <- config$fontes[[nome_fonte]]
  if (is.null(fonte)) {
    stop("Fonte não configurada: ", nome_fonte, call. = FALSE)
  }
  endpoint <- fonte$endpoints[[nome_endpoint]]
  if (is.null(endpoint)) {
    stop("Endpoint '", nome_endpoint, "' não existe na fonte '", nome_fonte,
         "'.", call. = FALSE)
  }

  req_base <- montar_requisicao(fonte, endpoint, nome_fonte)
  pag <- endpoint$paginacao %||% list()
  tipo <- pag$tipo %||% "nenhuma"
  max_paginas <- pag$max_paginas %||% 1000
  tamanho <- pag$tamanho

  pagina <- pag$inicio %||% 1
  deslocamento <- 0
  cursor <- NULL
  proxima_url <- NULL
  tabelas <- list()

  for (i in seq_len(max_paginas)) {
    req <- req_base
    extras <- list()
    if (tipo == "pagina") {
      extras[[pag$param %||% "page"]] <- pagina
      if (!is.null(tamanho)) extras[[pag$param_tamanho %||% "per_page"]] <- tamanho
    } else if (tipo == "offset") {
      extras[[pag$param %||% "offset"]] <- deslocamento
      if (!is.null(tamanho)) extras[[pag$param_tamanho %||% "limit"]] <- tamanho
    } else if (tipo == "cursor") {
      if (!is.null(proxima_url)) {
        req <- req_url(req, proxima_url)
      } else if (!is.null(cursor)) {
        extras[[pag$param %||% "cursor"]] <- cursor
      }
    }
    if (length(extras) > 0) req <- req_url_query(req, !!!extras)

    lido <- ler_resposta(req_perform(req), endpoint)
    n <- nrow(lido$registros)
    tabelas[[i]] <- lido$registros

    if (tipo == "nenhuma" || n == 0) break
    if (tipo == "pagina") {
      if (!is.null(tamanho) && n < tamanho) break
      pagina <- pagina + 1
    } else if (tipo == "offset") {
      if (!is.null(tamanho) && n < tamanho) break
      deslocamento <- deslocamento + n
    } else if (tipo == "cursor") {
      proximo <- pegar_caminho(lido$corpo, pag$campo_proximo)
      if (is.null(proximo) || length(proximo) != 1 || is.na(proximo) ||
          !nzchar(as.character(proximo))) break
      proximo <- as.character(proximo)
      if (grepl("^https?://", proximo)) {
        proxima_url <- proximo
      } else {
        cursor <- proximo
      }
    }
    if (i == max_paginas) {
      warning("'", nome_fonte, "/", nome_endpoint, "': limite de ",
              max_paginas, " páginas atingido; pode haver mais dados.",
              call. = FALSE)
    }
  }

  empilhar(tabelas)
}

# Colunas que ainda forem listas são gravadas como texto JSON no CSV.
achatar_para_csv <- function(tabela) {
  for (col in names(tabela)) {
    if (is.list(tabela[[col]])) {
      tabela[[col]] <- vapply(tabela[[col]], function(v) {
        if (is.null(v) || length(v) == 0) NA_character_
        else as.character(jsonlite::toJSON(v, auto_unbox = TRUE))
      }, character(1))
    }
  }
  tabela
}

salvar_dados <- function(tabela, nome_fonte, nome_endpoint, config) {
  pasta <- file.path(config$saida$pasta %||% "dados", nome_fonte)
  dir.create(pasta, recursive = TRUE, showWarnings = FALSE)
  formatos <- config$saida$formatos %||% c("csv", "rds")
  arquivos <- character()
  if ("csv" %in% formatos) {
    arq <- file.path(pasta, paste0(nome_endpoint, ".csv"))
    utils::write.csv(achatar_para_csv(tabela), arq, row.names = FALSE,
                     fileEncoding = "UTF-8", na = "")
    arquivos <- c(arquivos, arq)
  }
  if ("rds" %in% formatos) {
    arq <- file.path(pasta, paste0(nome_endpoint, ".rds"))
    saveRDS(tabela, arq)
    arquivos <- c(arquivos, arq)
  }
  arquivos
}

registrar <- function(config, linha) {
  pasta <- config$saida$pasta %||% "dados"
  dir.create(pasta, recursive = TRUE, showWarnings = FALSE)
  arq <- file.path(pasta, "_registro.csv")
  utils::write.table(linha, arq, sep = ",", row.names = FALSE,
                     col.names = !file.exists(arq), append = file.exists(arq),
                     qmethod = "double", fileEncoding = "UTF-8")
}

# Baixa todas as fontes (ou só as escolhidas). Uma falha em um site não
# interrompe os demais; o resultado de cada endpoint vai para
# dados/_registro.csv.
baixar_tudo <- function(config, fontes = NULL, endpoints = NULL) {
  fontes <- fontes %||% names(config$fontes)
  desconhecidas <- setdiff(fontes, names(config$fontes))
  if (length(desconhecidas) > 0) {
    stop("Fonte(s) não configurada(s): ",
         paste(desconhecidas, collapse = ", "), call. = FALSE)
  }

  resumo <- list()
  for (nome_fonte in fontes) {
    nomes_ep <- names(config$fontes[[nome_fonte]]$endpoints)
    if (!is.null(endpoints)) {
      faltando <- setdiff(endpoints, nomes_ep)
      if (length(faltando) > 0) {
        stop("Endpoint(s) inexistente(s) em '", nome_fonte, "': ",
             paste(faltando, collapse = ", "), call. = FALSE)
      }
      nomes_ep <- endpoints
    }
    for (nome_ep in nomes_ep) {
      message("-> ", nome_fonte, "/", nome_ep, " ...")
      linha <- data.frame(
        quando = format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
        fonte = nome_fonte, endpoint = nome_ep,
        status = "ok", linhas = NA_integer_, mensagem = "",
        stringsAsFactors = FALSE
      )
      tryCatch({
        tabela <- baixar_endpoint(config, nome_fonte, nome_ep)
        arquivos <- salvar_dados(tabela, nome_fonte, nome_ep, config)
        linha$linhas <- nrow(tabela)
        message("   ", nrow(tabela), " linhas em ",
                paste(arquivos, collapse = ", "))
      }, error = function(e) {
        linha$status <<- "erro"
        linha$mensagem <<- gsub("\\s+", " ", conditionMessage(e))
        message("   ERRO: ", linha$mensagem)
      })
      registrar(config, linha)
      resumo[[length(resumo) + 1]] <- linha
    }
  }
  invisible(do.call(rbind, resumo))
}
