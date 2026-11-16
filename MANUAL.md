# Manual da Plataforma de Dados

## 1. O que é

A Plataforma de Dados é um programa em Python que conecta em vários sites
(IBGE, ANP, Banco Central e outros) e baixa os dados de todos para uma pasta
do seu computador. Cada site é cadastrado uma única vez; depois, um clique
atualiza tudo.

Ela roda no seu computador e é usada por uma tela no navegador. Nada é
enviado para terceiros: o programa só conversa com os sites que você
cadastrar.

![Tela de cadastro de sites](docs/tela_sites.png)

## 2. Como abrir

Requisito: Python 3.9 ou mais novo. Não há mais nada para instalar.

1. Abra o terminal (Prompt de Comando) na pasta do projeto.
2. Rode `python app.py`.
3. O navegador abre sozinho em `http://127.0.0.1:8000`.

Para encerrar, volte ao terminal e aperte `Ctrl+C`. Enquanto o terminal
estiver fechado, a tela não funciona.

Se a porta 8000 estiver ocupada, use outra: `python app.py --porta 9000`.

## 3. Conceitos

| Termo | O que significa | Exemplo |
|---|---|---|
| **Site** | Uma fonte de dados, com endereço e (se preciso) login | IBGE SIDRA |
| **Conjunto de dados** | Uma consulta ou um grupo de arquivos dentro de um site | IPCA dos últimos 12 meses |
| **Identificador** | Nome curto, em minúsculas, sem espaços nem acentos; vira nome de pasta ou arquivo | `ibge_sidra`, `ipca_12_meses` |

Um site pode ter vários conjuntos de dados. Cada conjunto tem um **tipo**:

| Tipo | Para que serve | O que é gravado |
|---|---|---|
| **Tabela** | APIs (JSON) e arquivos CSV que devem virar tabela | `dados/<site>/<conjunto>.csv` |
| **Arquivo** | Um arquivo de endereço fixo, baixado como está (ZIP, XLSX, TXT...) | `dados/<site>/<conjunto>/<arquivo>` |
| **Página com vários arquivos** | Uma página do site com links para arquivos; a plataforma acha os links | idem |
| **Portal CKAN** | Portais de dados abertos (ANTT, ANEEL, TSE, CVM, IBAMA...); a plataforma lê a lista de recursos do conjunto | idem |

## 4. A tela, aba por aba

### 4.1 Sites

À esquerda fica a lista de sites cadastrados; à direita, o formulário do
site selecionado.

**Dados do site**

| Campo | O que preencher |
|---|---|
| Identificador | Nome curto do site. Vira o nome da pasta dos dados. Não pode ser alterado depois de salvo |
| Descrição | Texto livre, aparece na lista |
| Endereço do site (URL base) | A parte comum do endereço, ex.: `https://apisidra.ibge.gov.br` |
| Login no site | Ver seção 5 |
| Tempo máximo de espera | Em segundos. O padrão é 60; aumente para arquivos grandes (a ANP está com 600) |

**Dados do site (continuação)**

| Campo | O que preencher |
|---|---|
| Página oficial | Link de consulta para a página do órgão |
| Observações | Anotações livres sobre a fonte |
| Aceitar certificado não reconhecido | Deixe desmarcado. Marque só se o site der erro de certificado e você confiar no endereço: isso desliga uma checagem de segurança da conexão |

Os sites vindos do catálogo mostram também um quadro com ID, sinal de
mercado, prioridade e o que baixar. A caixa **Buscar site** filtra a lista.

**Conjuntos de dados do site**

| Campo | Vale para | O que preencher |
|---|---|---|
| Identificador | todos | Nome curto do conjunto |
| Tipo | todos | Tabela, Arquivo, Página com vários arquivos ou Portal CKAN |
| Caminho | tabela, arquivo, página | O que vem depois do endereço do site |
| Parâmetros | tabela, arquivo, página | Opcional. Um por linha, `chave=valor` |
| Conjunto no portal (dataset) | CKAN | O final do endereço do conjunto, ex.: `rntrc` |
| Filtro | página, CKAN | Termos separados por vírgula; basta um aparecer no nome ou endereço do arquivo. Palavras do mesmo termo precisam aparecer todas. Ex.: `municipio 2026, csv` |
| Máximo de arquivos novos por vez | página, CKAN | Padrão 20. O que sobrar é baixado na próxima vez |
| Os mais novos ficam no fim | página, CKAN | Marque quando a lista do site começa pelos mais antigos |
| Não incluir no "Baixar tudo" | todos | Para arquivos muito grandes; só baixam pelo botão do próprio conjunto |

Para o tipo Tabela, em **Formato da resposta e paginação**:

| Campo | Quando usar |
|---|---|
| Formato da resposta | `JSON` para APIs; `Arquivo CSV` para CSV que deve virar tabela |
| Onde está a lista no JSON | Quando os dados vêm dentro de outro campo, ex.: `data.items`. Aceita posição em lista, ex.: `1` (Banco Mundial) |
| A primeira linha traz os nomes das colunas | Marque para a SIDRA/IBGE |
| Separador do CSV | Normalmente `;` em sites brasileiros |
| Codificação do texto | Troque para Latin-1 se os acentos saírem errados |
| Método | `GET` (padrão) ou `POST`, quando a consulta vai no corpo |
| Paginação | Ver seção 6 |

**Endereços que mudam todo mês**

O caminho e os parâmetros aceitam marcadores de data, preenchidos no dia do
download: `{AAAA}`, `{MM}`, `{AAAA-MM}` e `{AAAAMM}`. Um número depois de
`:` desloca em meses: `{AAAA-MM:-1}` é o mês passado. Exemplo (Receita):
`/public.php/dav/files/.../{AAAA-MM:-1}/Cnaes.zip`.

**Botões**

| Botão | O que faz |
|---|---|
| Testar conexão / Listar arquivos | Mostra as primeiras 20 linhas, ou a lista de arquivos encontrados. Não grava nada |
| Salvar e baixar | Salva o site e baixa esse conjunto |
| Remover | Tira o conjunto do site (vale ao salvar) |
| + Adicionar conjunto | Cria mais um conjunto no mesmo site |
| Salvar site | Grava as alterações |
| Excluir site | Remove o cadastro. Os dados já baixados são mantidos |

### 4.2 Baixar tudo

O botão **Baixar tudo**, no topo, baixa todos os conjuntos de todos os
sites, um de cada vez, mostrando a situação de cada um. Se um site falhar,
os demais continuam. Conjuntos marcados como "Não incluir no Baixar tudo"
ficam de fora.

### 4.3 Dados baixados

Lista os arquivos já baixados, com número de linhas, tamanho e data.

- **ver** mostra as primeiras 50 linhas na própria tela.
- **baixar .csv** salva uma cópia do arquivo onde você escolher.

### 4.4 Histórico

Registro de todos os downloads: data e hora, site, conjunto, situação
(`ok` ou `erro`), número de linhas e a mensagem de erro, quando houver.

### 4.5 Como funciona

Um resumo deste manual dentro da própria tela.

## 5. Sites que exigem login

| Tipo | Quando usar | O que preencher |
|---|---|---|
| Não precisa | APIs públicas (IBGE, Banco Central, ANP) | Nada |
| Token (Bearer) | O site fornece um "token de acesso" | O token |
| Chave de API | O site fornece uma "API key" | A chave, o nome dela (ex.: `X-API-Key`) e onde é enviada: no cabeçalho ou no endereço |
| Usuário e senha | Login tradicional | Usuário e senha |

As credenciais ficam só no seu computador, no arquivo
`config/segredos.json`, que não vai para o Git. A tela nunca mostra uma
credencial já guardada; para mantê-la, deixe o campo vazio ao salvar.

A documentação de cada site informa qual tipo ele usa.

## 6. Paginação

Algumas APIs entregam os dados em partes. A plataforma busca todas as
partes e junta num único arquivo.

| Tipo | Como o site funciona | Campos |
|---|---|---|
| Não tem | Tudo vem de uma vez | — |
| Por número de página | `?page=1`, `?page=2`... | Nome do parâmetro, parâmetro do tamanho, linhas por página |
| Por posição (offset) | `?offset=0`, `?offset=100`... | Os mesmos |
| Por cursor | Cada resposta informa onde está a próxima | Nome do parâmetro e o campo da resposta com a próxima página, ex.: `meta.next` |

O download para quando uma página vem vazia ou incompleta. "Máximo de
páginas" (padrão 1000) é uma proteção; se for atingido, o histórico avisa
que pode haver mais dados.

## 7. Onde ficam os arquivos

```
config/fontes.json                      sites cadastrados (a tela edita esse arquivo)
config/segredos.json                    tokens e senhas (só no seu computador)
dados/<site>/<conjunto>.csv             tabela mais recente
dados/<site>/_versoes/<conjunto>/       versões anteriores da tabela, com data
dados/<site>/<conjunto>/                arquivos baixados como estão
dados/<site>/<conjunto>/_arquivos.csv   origem, data, tamanho e hash de cada arquivo
dados/_historico.csv                    registro dos downloads
```

**Nada é sobrescrito.**

- Tabelas: o `.csv` principal é sempre o mais recente; cada vez que o
  conteúdo muda, uma cópia datada é guardada em `_versoes`.
- Arquivos: só é baixado o que é novo ou mudou no site. Se um arquivo de
  mesmo nome mudar, o novo é gravado com a data no nome
  (`arquivo__20261116-180000.zip`) e o antigo permanece.

Os `.csv` usam `;` como separador e abrem direto no Excel. Campos dentro de
campos viram colunas com ponto, ex.: `regiao.sigla`.

```python
import pandas as pd
ipca = pd.read_csv("dados/ibge_sidra/ipca_12_meses.csv", sep=";")
```

Arquivos ZIP e XLSX são guardados como vieram; a plataforma não os abre nem
transforma.

## 8. Baixar sem abrir a tela

Útil para agendar uma atualização diária (Agendador de Tarefas do Windows
ou cron):

```bash
python baixar.py                 # todos os sites
python baixar.py ibge_sidra      # só um site
python baixar.py bcb selic       # só um conjunto
```

## 9. Fontes já cadastradas (Catálogo Mestre)

As 33 fontes do catálogo estão cadastradas em 36 sites (IBGE, ANP e Comex
Stat ocupam dois cada), com 110 conjuntos. Situação no teste feito em
16/11/2026 contra os sites reais:

| ID | Site (identificador) | Como baixa | Situação |
|---|---|---|---|
| DH-001 | `ibge`, `ibge_sidra` | API | Testado |
| DH-002 | `receita_cnpj` | Arquivos ZIP do mês passado | Testado. Empresas, Estabelecimentos e Sócios fora do "Baixar tudo" |
| DH-003 | `senatran` | Página com planilhas mensais | Testado |
| DH-004 | `antt` | Portal CKAN | Testado (portal lento, às vezes dá tempo esgotado) |
| DH-005 | `dnit` | Portal CKAN | **Não testado**: o site recusou a conexão do ambiente de testes |
| DH-006 | `anp_revendedores`, `anp_precos` | API e página com arquivos | Testado |
| DH-007 | `rais_caged` | Arquivo em FTP | **Não testado** |
| DH-008 | `comexstat`, `comexstat_api` | Página com CSVs; API | Lista testada; download deu erro de certificado (ver seção 11) |
| DH-009 | `bcb` | API | Testado |
| DH-010 | `aneel` | Portal CKAN | **Não testado**: conexão recusada |
| DH-011 | `anatel` | Arquivos ZIP | **Não testado** |
| DH-012 | `siconfi` | API | Testado |
| DH-013 | `compras_gov` | API | Testado |
| DH-014 | `antaq` | Arquivo ZIP | **Não testado**: site não respondeu |
| DH-015 | `anac` | Arquivo CSV (360 MB) | Endereço conferido; download completo não feito |
| DH-016 | `cadastur` | Portal CKAN | Testado |
| DH-017 | `cnes` | Arquivo em FTP | **Não testado** |
| DH-018 | `inep` | Página com ZIPs | Lista testada; download deu erro de certificado |
| DH-019 | `sinisa` | Página com arquivos | Testado |
| DH-020 | `conab` | Arquivo TXT | Testado |
| DH-021 | `inmet` | Página com ZIPs | Lista e endereço conferidos; download completo não feito |
| DH-022 | `mapbiomas` | — | Só referência: página montada por JavaScript |
| DH-023 | `mapbiomas_alerta` | — | Só referência: API GraphQL com login próprio |
| DH-024 | `openstreetmap` | API Overpass | **Não testado**: conexão recusada |
| DH-025 | `tse` | Portal CKAN | Lista testada; download não (servidor de arquivos fora do ambiente de testes) |
| DH-026 | `cvm` | Portal CKAN | Testado |
| DH-027 | `ibama` | Portal CKAN | Testado (portal instável) |
| DH-028 | `portal_transparencia` | API com chave | Aguardando a sua chave |
| DH-029 | `world_bank` | API | Testado |
| DH-030 | `un_comtrade` | API (prévia gratuita) | Testado |
| DH-031 | `faostat` | Arquivo ZIP | Endereço conferido; download completo não feito |
| DH-032 | `oecd` | API (CSV) | Testado |
| DH-033 | `logcomex` | — | Só referência: fonte comercial |

"Não testado" significa que o endereço foi cadastrado mas não pôde ser
conferido; use **Listar arquivos** ou **Testar conexão** na primeira vez. O
campo Observações de cada site traz os detalhes.

Para cadastrar outras fontes, use **+ Novo site** (seção 10).

## 10. Exemplo: cadastrar um site novo

Para baixar a lista de municípios do IBGE:

1. Aba **Sites**, selecione `ibge` e clique em **+ Adicionar conjunto**.
2. Identificador: `municipios`. Caminho: `/api/v1/localidades/municipios`.
3. Clique em **Testar conexão** e confira as primeiras linhas.
4. Clique em **Salvar e baixar**.
5. O arquivo aparece na aba **Dados baixados** e em
   `dados/ibge/municipios.csv`.

## 11. Problemas comuns

| Mensagem | Causa provável | O que fazer |
|---|---|---|
| "Sem resposta da plataforma" | O terminal com `app.py` foi fechado | Rode `python app.py` de novo |
| "Não foi possível conectar ao site" | Sem internet, endereço errado ou site fora do ar | Confira o endereço do site |
| "erro HTTP 404" | Caminho errado | Confira o caminho na documentação do site |
| "erro HTTP 401" ou "403" | Login ausente ou inválido | Revise o tipo de login e a credencial |
| "A resposta do site não é um JSON válido" | O site entrega um arquivo, não uma API | Mude o formato para "Arquivo CSV" |
| "o certificado de segurança do site não foi reconhecido" | O servidor usa um certificado que o Python não reconhece | Se confiar no endereço, marque "Aceitar certificado não reconhecido" no site |
| "Nenhum arquivo encontrado" | Filtro restritivo demais ou página montada por JavaScript | Afrouxe o filtro; se não houver links, cadastre o endereço direto como tipo Arquivo |
| Acentos errados | Codificação diferente | Troque a codificação para Latin-1 |
| Tudo veio numa coluna só | Separador errado | Ajuste o separador do CSV (`;` ou `,`) |
| "Limite de páginas atingido" | Há mais dados que o limite | Aumente "Máximo de páginas" |

## 12. Limites atuais

- Arquivos ZIP, XLSX, 7z e TXT são baixados e guardados como vieram; a
  plataforma não os abre nem os transforma em tabela.
- Páginas montadas por JavaScript (MapBiomas, painéis) não têm links que a
  plataforma consiga ler.
- Não atende sites que exigem login por formulário, OAuth ou token obtido
  por chamada própria (MapBiomas Alerta).
- O agendamento automático não é feito pela tela; use `baixar.py` com o
  agendador do sistema.
- "Baixar tudo" é feito um conjunto por vez; com muitas fontes, demora.

