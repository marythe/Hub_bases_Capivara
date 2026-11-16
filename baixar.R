#!/usr/bin/env Rscript
# Baixa os dados das APIs configuradas em config/fontes.yml.
#
#   Rscript baixar.R                 # todas as fontes
#   Rscript baixar.R bcb             # só a fonte "bcb"
#   Rscript baixar.R bcb selic       # só o endpoint "selic" da fonte "bcb"
#   Rscript baixar.R --listar        # mostra o que está configurado

source("R/conectores.R")

args <- commandArgs(trailingOnly = TRUE)
config <- ler_config(Sys.getenv("FONTES_CONFIG", "config/fontes.yml"))

if ("--listar" %in% args) {
  for (nome in names(config$fontes)) {
    fonte <- config$fontes[[nome]]
    cat(nome, " - ", fonte$descricao %||% fonte$base_url, "\n", sep = "")
    cat("   endpoints: ", paste(names(fonte$endpoints), collapse = ", "),
        "\n", sep = "")
  }
  quit(status = 0)
}

fontes <- if (length(args) >= 1) args[1] else NULL
endpoints <- if (length(args) >= 2) args[-1] else NULL

resumo <- baixar_tudo(config, fontes, endpoints)
erros <- sum(resumo$status == "erro")
cat("\n", nrow(resumo) - erros, " endpoint(s) baixado(s), ", erros,
    " com erro.\n", sep = "")
quit(status = if (erros > 0) 1 else 0)
