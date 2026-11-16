# Rodar a partir da raiz do projeto:  Rscript tests/testthat.R
library(testthat)
if (!isTRUE(l10n_info()[["UTF-8"]])) Sys.setlocale("LC_ALL", "C.UTF-8")
source("R/conectores.R")
test_dir("tests/testthat", env = globalenv(), stop_on_failure = TRUE)
