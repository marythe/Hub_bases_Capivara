# Plataforma de Dados

Uma única plataforma, em Python, para conectar em vários sites (IBGE, ANP,
Banco Central e quantos mais forem necessários) e baixar os dados de todos
para um repositório local. Tudo é feito por uma tela no navegador.

## Como usar

Só precisa do Python 3.9 ou mais novo — não há nada para instalar.

```bash
python app.py
```

O navegador abre em `http://127.0.0.1:8000` com quatro abas:

| Aba | Para que serve |
|---|---|
| **Sites** | Cadastrar cada site e os conjuntos de dados que quer dele. "Testar conexão" mostra as primeiras linhas sem gravar nada. |
| **Dados baixados** | Ver, pré-visualizar e baixar os arquivos `.csv`. |
| **Histórico** | Registro de cada download, com data, nº de linhas e erros. |
| **Como funciona** | Resumo dentro da própria tela. |

O botão **Baixar tudo** busca todos os conjuntos de todos os sites. Se um
site falhar, os outros continuam.

## Como funciona

```
 navegador (tela)  <->  app.py (roda no seu computador)  <->  sites (IBGE, ANP, ...)
                              |
                              +-- config/fontes.json     sites cadastrados
                              +-- config/segredos.json   tokens e senhas (fora do Git)
                              +-- dados/<site>/<conjunto>.csv      tabelas
                              +-- dados/<site>/<conjunto>/         arquivos como estão
                              +-- dados/_historico.csv
```

- A tela é uma página HTML; quem conversa com os sites é o programa Python
  rodando na sua máquina (um navegador sozinho não consegue acessar a
  maioria das APIs nem gravar arquivos).
- Cada **site** tem um endereço e, se precisar, um login (token, chave de
  API ou usuário e senha).
- Cada **conjunto de dados** é uma consulta ao site (caminho + parâmetros)
  e gera um arquivo `.csv`.
- Sites sem API funcionam pelos tipos "Arquivo" e "Página com vários
  arquivos": a plataforma acha os links e baixa só o que é novo ou mudou.
- APIs que entregam os dados em partes são tratadas pela opção de paginação
  (por página, por posição ou por cursor).
- O programa só aceita acesso do próprio computador.

Os `.csv` usam `;` como separador e abrem direto no Excel. Em Python:

```python
import pandas as pd
ipca = pd.read_csv("dados/ibge_sidra/ipca_12_meses.csv", sep=";")
```

## Sem abrir a tela (para agendar)

```bash
python baixar.py                 # todos os sites
python baixar.py ibge_sidra      # só um site
python baixar.py bcb selic       # só um conjunto
```

## Fontes já cadastradas

As 34 fontes do Catálogo Mestre (IBGE, Receita/CNPJ, SENATRAN, ANTT, DNIT,
ANP, Comex Stat, Banco Central, Siconfi, Compras.gov e outras) já estão em
`config/fontes.json`. A situação de teste de cada uma está na seção 9 do
manual. Novas fontes são cadastradas pela tela, em "+ Novo site".

Cada conjunto de dados tem um tipo: tabela (API/CSV), arquivo, página com
vários arquivos ou portal CKAN. Nada é sobrescrito: versões anteriores
ficam guardadas.

## Manual

O passo a passo completo está em [MANUAL.md](MANUAL.md).

## Testes

```bash
python -m unittest discover tests
```

Usam um site falso local, sem acessar a internet.
