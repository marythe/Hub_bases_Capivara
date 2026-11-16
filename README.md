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
                              +-- dados/<site>/<conjunto>.csv
                              +-- dados/_historico.csv
```

- A tela é uma página HTML; quem conversa com os sites é o programa Python
  rodando na sua máquina (um navegador sozinho não consegue acessar a
  maioria das APIs nem gravar arquivos).
- Cada **site** tem um endereço e, se precisar, um login (token, chave de
  API ou usuário e senha).
- Cada **conjunto de dados** é uma consulta ao site (caminho + parâmetros)
  e gera um arquivo `.csv`. Um novo download substitui o arquivo anterior.
- Sites sem API que publicam arquivos CSV (caso da ANP) funcionam
  escolhendo o formato "Arquivo CSV".
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

## Sites de exemplo já cadastrados

`bcb` (Selic e IPCA), `ibge` (estados), `ibge_sidra` (IPCA dos últimos 12
meses) e `anp` (preços de combustíveis, arquivo CSV). Podem ser editados ou
excluídos pela tela.

## Manual

O passo a passo completo está em [MANUAL.md](MANUAL.md).

## Testes

```bash
python -m unittest discover tests
```

Usam um site falso local, sem acessar a internet.
