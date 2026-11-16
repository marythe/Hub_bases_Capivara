# Plataforma de conexão com APIs (R)

Uma única plataforma para baixar dados de vários sites (IBGE, ANP, Banco
Central e quantos mais forem necessários). Cada site é um bloco no arquivo
`config/fontes.yml`; um comando baixa tudo para a pasta `dados/`.

```
config/fontes.yml   -> onde cada site é configurado
baixar.R            -> comando que baixa os dados
R/conectores.R      -> motor (não precisa mexer para adicionar sites)
dados/              -> repositório de dados baixados (criado ao rodar)
```

## Instalação

Com o R instalado, uma única vez:

```r
install.packages(c("httr2", "jsonlite", "yaml"))
```

## Uso

No terminal, dentro da pasta do projeto:

```bash
Rscript baixar.R --listar        # mostra os sites configurados
Rscript baixar.R                 # baixa tudo
Rscript baixar.R ibge_sidra      # só um site
Rscript baixar.R bcb selic       # só um endpoint de um site
```

Ou de dentro do R/RStudio:

```r
source("R/conectores.R")
config <- ler_config()
baixar_tudo(config)                       # tudo
ipca <- baixar_endpoint(config, "ibge_sidra", "ipca_12_meses")  # direto na memória
```

Resultado:

- `dados/<site>/<endpoint>.csv` e `.rds` — os dados de cada endpoint
  (cada execução substitui o arquivo anterior);
- `dados/_registro.csv` — histórico de cada download (data, linhas, erro).

Se um site falhar, os outros continuam sendo baixados.

## Como adicionar um site novo

Acrescente um bloco em `config/fontes.yml`:

```yaml
fontes:
  nome_do_site:
    descricao: Texto livre
    base_url: https://api.site.com
    endpoints:
      nome_dos_dados:
        caminho: /rota/da/api
```

### Campos da fonte (site)

| Campo | Para que serve |
|---|---|
| `base_url` | Endereço base do site (obrigatório) |
| `descricao` | Texto livre |
| `auth` | Login, ver abaixo (omitir se a API é pública) |
| `cabecalhos` | Cabeçalhos HTTP extras, ex.: `Accept: application/json` |
| `timeout_segundos` | Tempo máximo por requisição (padrão 60) |
| `tentativas` | Tentativas em caso de falha temporária (padrão 3) |

### Campos do endpoint (cada conjunto de dados)

| Campo | Para que serve |
|---|---|
| `caminho` | Rota depois do `base_url` (obrigatório) |
| `params` | Parâmetros da URL (`?chave=valor`) |
| `registros` | Onde fica a lista dentro do JSON, ex.: `data.items`. Omitir se a resposta já é a lista |
| `formato_resposta` | `json` (padrão) ou `csv` (para sites que publicam arquivos, como a ANP) |
| `separador` | Separador do CSV (padrão `,`) |
| `codificacao` | Codificação do texto, ex.: `latin1` (padrão `UTF-8`) |
| `primeira_linha_cabecalho` | `true` quando a 1ª linha traz os nomes das colunas (SIDRA) |
| `paginacao` | Ver abaixo |

### Autenticação

As senhas **não** ficam no arquivo de configuração. Copie `.Renviron.example`
para `.Renviron`, preencha as credenciais e, no YAML, informe só o nome da
variável:

```yaml
auth: { tipo: bearer,  token_env: SITE_TOKEN }
auth: { tipo: api_key, chave_env: SITE_CHAVE, nome: X-API-Key, onde: header }  # ou onde: query
auth: { tipo: basic,   usuario_env: SITE_USUARIO, senha_env: SITE_SENHA }
```

### Paginação

Para APIs que entregam os dados em partes:

```yaml
paginacao: { tipo: pagina, param: page,   param_tamanho: per_page, tamanho: 100 }
paginacao: { tipo: offset, param: offset, param_tamanho: limit,    tamanho: 200 }
paginacao: { tipo: cursor, param: cursor, campo_proximo: meta.next }
```

No tipo `cursor`, `campo_proximo` é o campo da resposta com o próximo cursor
(ou com a URL completa da próxima página). `max_paginas` (padrão 1000) limita
o total de páginas.

## Testes

```bash
Rscript tests/testthat.R
```

Os testes usam respostas simuladas, sem acessar a internet.
