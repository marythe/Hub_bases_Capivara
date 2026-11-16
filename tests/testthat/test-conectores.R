resposta_json <- function(x) {
  httr2::response(
    status_code = 200,
    headers = list("Content-Type" = "application/json"),
    body = charToRaw(as.character(jsonlite::toJSON(x, auto_unbox = TRUE)))
  )
}

config_teste <- function(endpoint, auth = NULL, pasta = tempfile()) {
  list(
    saida = list(pasta = pasta, formatos = c("csv", "rds")),
    fontes = list(site = list(
      base_url = "https://api.teste.local/v1/",
      auth = auth,
      endpoints = list(itens = endpoint)
    ))
  )
}

test_that("baixa lista simples sem paginação", {
  config <- config_teste(list(caminho = "/itens"))
  urls <- character()
  tabela <- with_mocked_responses(function(req) {
    urls <<- c(urls, req$url)
    resposta_json(list(list(id = 1, nome = "a"), list(id = 2, nome = "b")))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(nrow(tabela), 2)
  expect_equal(tabela$nome, c("a", "b"))
  expect_equal(urls, "https://api.teste.local/v1/itens")
})

test_that("paginação por número de página para na página incompleta", {
  config <- config_teste(list(
    caminho = "itens", registros = "data.itens",
    paginacao = list(tipo = "pagina", param = "p", param_tamanho = "n",
                     tamanho = 2)
  ))
  paginas <- list(
    "1" = list(list(id = 1), list(id = 2)),
    "2" = list(list(id = 3), list(id = 4)),
    "3" = list(list(id = 5))
  )
  pedidas <- character()
  tabela <- with_mocked_responses(function(req) {
    q <- httr2::url_parse(req$url)$query
    pedidas <<- c(pedidas, q$p)
    expect_equal(q$n, "2")
    resposta_json(list(data = list(itens = paginas[[q$p]])))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(tabela$id, 1:5)
  expect_equal(pedidas, c("1", "2", "3"))
})

test_that("paginação por offset avança pelo número de registros", {
  config <- config_teste(list(
    caminho = "itens",
    paginacao = list(tipo = "offset", tamanho = 2)
  ))
  todos <- 1:5
  offsets <- character()
  tabela <- with_mocked_responses(function(req) {
    q <- httr2::url_parse(req$url)$query
    offsets <<- c(offsets, q$offset)
    ini <- as.integer(q$offset) + 1
    ids <- todos[seq(ini, length.out = 2)]
    ids <- ids[!is.na(ids)]
    resposta_json(lapply(ids, function(i) list(id = i)))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(tabela$id, 1:5)
  expect_equal(offsets, c("0", "2", "4"))
})

test_that("paginação por cursor segue token e URL completa", {
  config <- config_teste(list(
    caminho = "itens", registros = "resultados",
    paginacao = list(tipo = "cursor", param = "c", campo_proximo = "meta.prox")
  ))
  urls <- character()
  tabela <- with_mocked_responses(function(req) {
    urls <<- c(urls, req$url)
    n <- length(urls)
    prox <- switch(n, "abc", "https://api.teste.local/v1/itens?pg=3", NULL)
    resposta_json(list(resultados = list(list(id = n)),
                       meta = list(prox = prox)))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(tabela$id, 1:3)
  expect_match(urls[2], "c=abc")
  expect_equal(urls[3], "https://api.teste.local/v1/itens?pg=3")
})

test_that("max_paginas limita o download e avisa", {
  config <- config_teste(list(
    caminho = "itens",
    paginacao = list(tipo = "pagina", max_paginas = 2)
  ))
  expect_warning(
    tabela <- with_mocked_responses(function(req) {
      resposta_json(list(list(id = 1)))
    }, baixar_endpoint(config, "site", "itens")),
    "limite de 2"
  )
  expect_equal(nrow(tabela), 2)
})

test_that("autenticação usa variáveis de ambiente", {
  withr::local_envvar(TESTE_TOKEN = "segredo", TESTE_CHAVE = "k123",
                      TESTE_USU = "ana", TESTE_SENHA = "pw")
  fonte <- list(base_url = "https://x.local")
  ep <- list(caminho = "/a")

  fonte$auth <- list(tipo = "bearer", token_env = "TESTE_TOKEN")
  req <- montar_requisicao(fonte, ep, "site")
  expect_equal(req$headers$Authorization, "Bearer segredo")

  fonte$auth <- list(tipo = "api_key", chave_env = "TESTE_CHAVE",
                     nome = "X-Chave")
  req <- montar_requisicao(fonte, ep, "site")
  expect_equal(req$headers[["X-Chave"]], "k123")

  fonte$auth <- list(tipo = "api_key", chave_env = "TESTE_CHAVE",
                     nome = "api_key", onde = "query")
  req <- montar_requisicao(fonte, ep, "site")
  expect_match(req$url, "api_key=k123")

  fonte$auth <- list(tipo = "basic", usuario_env = "TESTE_USU",
                     senha_env = "TESTE_SENHA")
  req <- montar_requisicao(fonte, ep, "site")
  expect_equal(req$headers$Authorization,
               paste("Basic", jsonlite::base64_enc("ana:pw")))
})

test_that("credencial ausente gera erro claro", {
  withr::local_envvar(NAO_EXISTE_XYZ = NA)
  fonte <- list(base_url = "https://x.local",
                auth = list(tipo = "bearer", token_env = "NAO_EXISTE_XYZ"))
  expect_error(montar_requisicao(fonte, list(caminho = "/a"), "site"),
               "NAO_EXISTE_XYZ")
})

test_that("resposta em CSV é lida", {
  config <- config_teste(list(caminho = "x", formato_resposta = "csv",
                              separador = ";"))
  tabela <- with_mocked_responses(function(req) {
    httr2::response(200, body = charToRaw("id;nome\n1;a\n2;b\n"))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(tabela$nome, c("a", "b"))
})

test_that("CSV em latin1 é convertido", {
  config <- config_teste(list(caminho = "x", formato_resposta = "csv",
                              separador = ";", codificacao = "latin1"))
  tabela <- with_mocked_responses(function(req) {
    httr2::response(200, body = as.raw(c(charToRaw("nome\nS"), 0xe3,
                                         charToRaw("o\n"))))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(enc2utf8(tabela$nome), "S\u00e3o")
})

test_that("primeira linha pode ser usada como cabeçalho", {
  config <- config_teste(list(caminho = "x", primeira_linha_cabecalho = TRUE))
  tabela <- with_mocked_responses(function(req) {
    resposta_json(list(list(V = "Valor", D1N = "Local"),
                       list(V = "0.5", D1N = "Brasil"),
                       list(V = "0.4", D1N = "Brasil")))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(names(tabela), c("Valor", "Local"))
  expect_equal(tabela$Valor, c("0.5", "0.4"))
})

test_that("objetos aninhados e colunas diferentes são tratados", {
  config <- config_teste(list(caminho = "x"))
  tabela <- with_mocked_responses(function(req) {
    resposta_json(list(
      list(id = 1, regiao = list(sigla = "N"), tags = list("a", "b")),
      list(id = 2, regiao = list(sigla = "S"), tags = list())
    ))
  }, baixar_endpoint(config, "site", "itens"))
  expect_equal(tabela$regiao.sigla, c("N", "S"))
  csv <- achatar_para_csv(tabela)
  expect_type(csv$tags, "character")
})

test_that("baixar_tudo grava arquivos, registra e não para em erros", {
  pasta <- tempfile()
  config <- config_teste(list(caminho = "ok"), pasta = pasta)
  config$fontes$site$endpoints$quebrado <- list(caminho = "falha")
  resumo <- suppressMessages(with_mocked_responses(function(req) {
    if (grepl("falha", req$url)) return(httr2::response(500))
    resposta_json(list(list(id = 1, nome = "ação")))
  }, baixar_tudo(config)))
  expect_equal(resumo$status, c("ok", "erro"))
  expect_equal(resumo$linhas[1], 1)
  lido <- readLines(file.path(pasta, "site", "itens.csv"), encoding = "UTF-8")
  expect_equal(enc2utf8(lido[2]), enc2utf8("1,\"ação\""))
  expect_equal(readRDS(file.path(pasta, "site", "itens.rds"))$id, 1)
  registro <- read.csv(file.path(pasta, "_registro.csv"))
  expect_equal(nrow(registro), 2)
  expect_false(file.exists(file.path(pasta, "site", "quebrado.csv")))
})

test_that("configuração inválida é recusada com mensagem clara", {
  expect_error(validar_config(list()), "fontes")
  expect_error(validar_config(list(fontes = list(a = list(
    endpoints = list(x = list(caminho = "/")))))), "base_url")
  expect_error(validar_config(list(fontes = list(a = list(
    base_url = "https://x", auth = list(tipo = "oauth"),
    endpoints = list(x = list(caminho = "/")))))), "auth.tipo")
  expect_error(validar_config(list(fontes = list(a = list(
    base_url = "https://x",
    endpoints = list(x = list(caminho = "/",
                              paginacao = list(tipo = "cursor"))))))),
    "campo_proximo")
})

test_that("o arquivo de exemplo config/fontes.yml é válido", {
  config <- ler_config(file.path("..", "..", "config", "fontes.yml"))
  expect_true(all(c("bcb", "ibge", "anp") %in% names(config$fontes)))
})
