# Fontes de dados

Estado em 29/10/2026. Tudo marcado **A VERIFICAR** precisa ser confirmado numa prova de conceito (plano, Marco 1) antes de virar código de produção. Ao confirmar, troque a marca por **VERIFICADO em <data>** e registre o que achou.

Identificadores do município: código IBGE **3532504**; UF SP; CNPJ da prefeitura **45145414000147** (VERIFICADO em 29/10/2026 nos dados do Transferegov, ver §Transferegov API).

## Acesso

Em 29/10/2026, um teste feito de um servidor fora do Brasil recebeu bloqueio (proxy 403) para Transferegov, Obrasgov, Portal da Transparência e TCE-SP. Isso pode ser restrição do ambiente de teste, não das fontes. Resultado da T1.0:

| Fonte | Local (Brasil) | GitHub Actions |
| --- | --- | --- |
| Transferegov API | HTTP 200 nas páginas `/docs` de `especiais`, `fundoafundo` e `parcerias` | HTTP 200 nas mesmas três (130 a 300 ms) |
| Obrasgov API | HTTP 200 na URL base | HTTP 200 na URL base (1,3 s) |
| Portal da Transparência API | HTTP 401 na URL base sem chave, esperado: o host responde | HTTP 401 na URL base sem chave, esperado |
| Tesouro (APIs) | HTTP 500 na URL base de transferências constitucionais: o host responde, mas a URL sem rota não prova o endpoint; confirmar na T1.6 | HTTP 500, igual ao local |
| Tesouro Transparente (CAUC) | Não testado: URL desconhecida (T1.5) | Não testado |

Testes de 29/10/2026 com `scripts/teste_acesso.py`, sem credenciais: local às 14:57 (America/Sao_Paulo, a partir do Brasil) e no GitHub Actions às 18:02 UTC (runner `ubuntu-latest`, workflow `.github/workflows/teste-acesso.yml`, execução 40926913483). Os dois ambientes deram o mesmo resultado: **o Actions não é bloqueado** nos hosts testados. O teste só prova que o host responde; endpoints, filtros e autenticação continuam A VERIFICAR nas POCs, e o acesso do Actions aos endpoints reais deve ser reconferido na T1.1 e na T1.4 (o Portal exige chave).

## Transferegov — API pública

- Host: `https://api-publica.transferegov.gestao.gov.br`
- Módulos: `especiais` (emendas Pix), `fundoafundo`, `parcerias` (programas, propostas, parcerias, execução financeira), `ted`.
- Documentação: `/especiais/docs`, `/fundoafundo/docs`, `/parcerias/docs`, `/ted/docs`.
- Referência: pacote Python [transferegovpy](https://pypi.org/project/transferegovpy/).

**VERIFICADO em 29/10/2026** (POC `scripts/poc_transferegov_api.py`, 37 requisições; amostras em `tests/fixtures/transferegov_api/`).

Geral:
- **Autenticação:** nenhuma. **Limites:** não documentados; 37 requisições com pausa de 0,3 s não deram 429. Backoff mesmo assim.
- **OpenAPI oficial** de cada módulo: `{host}/{modulo}/openapi.json` (a página `/docs` aponta para ele). Todos os nomes de parâmetro abaixo vêm dele.
- **Paginação:** `pagina` (≥1) e `tamanho_da_pagina` (máx. 200, padrão 50). Resposta: `{data, total_pages, total_items, page_number, page_size}`.
- **Data de atualização:** `GET /{modulo}/data-atualizacao` → `{"data_ultima_atualizacao": ...}` (29/10/2026: as três bases atualizadas no próprio dia).
- **Parâmetro desconhecido é ignorado** e devolve a tabela inteira com HTTP 200. Provado: `cd_ibge_recebedorx=3532504` devolveu os 90.460 registros. O script valida cada parâmetro contra o OpenAPI antes de chamar.
- Valores monetários vêm em **reais, como número decimal** (ex.: `91673.94`): converter para centavos com arredondamento, nunca com `int(x*100)` direto. Datas em ISO (`2025-12-30`; alguns campos com hora).
- Os filtros de texto são de igualdade exata. Em `fundoafundo/planos-acao`, `Neves Paulista` e `NEVES PAULISTA` deram o mesmo resultado (ignora caixa); em `especiais/beneficiarios-especiais` só o nome exato em maiúsculas foi testado (`MUNICIPIO DE BAURU` achou, `NEVES PAULISTA` sem prefixo não).

Identificação do município (confirmada nos dados):
- **Código IBGE 3532504**.
- **Prefeitura:** `MUNICIPIO DE NEVES PAULISTA`, CNPJ **45145414000147** (`fundoafundo/planos-acao` e `programas-beneficiarios`).
- **Fundos municipais** (recebedores em `parcerias`): Fundo Municipal de Saúde, CNPJ 13921776000196; Fundo Municipal de Assistência Social, CNPJ 14513724000143.

Por módulo:

| Módulo / endpoint | Filtro por município | Resultado para Neves Paulista |
| --- | --- | --- |
| `parcerias/proposta` | `cd_ibge_recebedor` (inteiro). Funciona. | 12 propostas (6 de 2025, 6 de 2026): 10 do Fundo Municipal de Saúde, 2 do Fundo Municipal de Assistência Social |
| `parcerias/parceria` | Não tem; filtrar por `id_proposta` | 12 parcerias, uma por proposta |
| `fundoafundo/planos-acao` | **`codigo_ibge_*` dá HTTP 500** ("Erro Interno Inesperado"), testado com 7 dígitos (recebedor e repassador) e com 6 dígitos (recebedor). Funcionam: `nome_municipio_ente_recebedor_plano_acao` (ignora caixa) e `cnpj_ente_recebedor_plano_acao`. | 2 planos de ação do Ministério da Cultura, ambos `AUTORIZADO`, com termo de adesão `ASSINADO` e saldo disponível 0: Lei Paulo Gustavo (R$ 91.673,94; vigência de 05/07/2023 a 31/12/2024) e Aldir Blanc 2025 (R$ 320.840,28; vigência de 22/05/2025 a 31/12/2029) |
| `fundoafundo/termos-adesao` | Não tem; filtrar por `id_plano_acao` | 2 termos, ambos `ASSINADO` |
| `fundoafundo/programas-beneficiarios` | `codigo_ibge_municipio_ente_beneficiario_programa`. Funciona. | 6 registros, todos `ESPECIFICO` |
| `especiais/beneficiarios-especiais` | Só `uf_beneficiario`, `cnpj_beneficiario`, `nome_beneficiario` (igualdade exata); sem IBGE | **0 registros**: a prefeitura não aparece entre os 628 beneficiários de SP do módulo (conferido por CNPJ, por nome e varrendo SP inteiro). Logo não há planos de ação nem de trabalho de emenda Pix para o município neste módulo em 29/10/2026 |
| `especiais/planos-acao-especiais`, `planos-trabalho-especiais` | Ligação por `id_beneficiario` e `id_plano_acao` | Sem dados do município |

Campos úteis (nomes exatos do OpenAPI):
- `parcerias/proposta`: `id_proposta`, `ds_objeto`, `situacao_proposta`, `in_situacao_analise`, `dt_proposta`, `ano_proposta`, `vl_total_planejamento_gastos` (preenchido) e `nr_vlr_total` (veio `null`), `dt_limite_captacao`, `cnpj_ente_recebedor`, `nm_ente_recebedor`, `id_programa`.
- `parcerias/parceria`: `id_parceria`, `cd_parceria`, `id_proposta`, `in_situacao_parceria`, `in_situacao_autorizacao_execucao`, `dh_assinatura`, `prazo_limite_captacao_recursos`, `publicacoes_parceria`.
- `fundoafundo/planos-acao`: `id_plano_acao`, `codigo_plano_acao`, `situacao_plano_acao`, `data_inicio_vigencia_plano_acao`, `data_fim_vigencia_plano_acao`, `valor_total_plano_acao`, `valor_total_repasse_plano_acao`, `valor_repasse_emenda_plano_acao`, `valor_saldo_disponivel_plano_acao`, `sigla_orgao_repassador_plano_acao`, `objetivos_plano_acao`.
- `fundoafundo/termos-adesao`: `situacao_termo_adesao`, `data_assinatura_termo_adesao`, `data_publicacao_dou_termo_adesao`.
- `especiais/planos-acao-especiais` (sem dados do município, nomes do OpenAPI): `situacao_plano_acao`, **`motivo_impedimento_plano_acao`**, `nome_parlamentar_emenda_plano_acao`, `numero_emenda_parlamentar_plano_acao`, `valor_custeio_plano_acao`, `valor_investimento_plano_acao`; `planos-trabalho-especiais`: `situacao_plano_trabalho`, `data_fim_execucao_plano_trabalho`. Existem também `planos-trabalho-historico` e `planos-acao-historico-especiais`.
- As amostras gravadas **não** têm dados bancários nem e-mail (o script remove `numero_conta*`, `numero_agencia*`, `dv_*`, `email*`).

Valores de situação **observados** para o município (29/10/2026):

| Campo | Observado | Documentado no OpenAPI (ainda não visto no município) |
| --- | --- | --- |
| `parcerias/proposta.situacao_proposta` | `Aprovada` (12) | Em Elaboração, Em Análise, Aprovada, Rejeitada, Inativada |
| `parcerias/proposta.in_situacao_analise` | `null` (12) | Proposta e Plano de Trabalho Em Complementação, em Análise, Enviados para Análise, Enviado para Complementação |
| `parcerias/parceria.in_situacao_parceria` | `Aprovada` (12) | Em Elaboração, Em Análise, Em Captação, Aprovada, Rejeitada, Inativa |
| `fundoafundo/planos-acao.situacao_plano_acao` | `AUTORIZADO` (2) | OpenAPI não lista valores |
| `fundoafundo/termos-adesao.situacao_termo_adesao` | `ASSINADO` (2) | EM_ELABORACAO, ENVIADO, ASSINADO |
| `especiais/planos-acao-especiais.situacao_plano_acao` | sem dados | CIENTE, IMPEDIDO (histórico: AGUARDANDO_CIENCIA, AGUARDANDO_CONCLUSAO_PLANO_TRABALHO, CIENTE, IMPEDIDO, IMPEDIDO_REJEICAO_PLANO_TRABALHO) |
| `especiais/planos-trabalho-especiais.situacao_plano_trabalho` | sem dados | (planos-trabalho-historico) Aguardando envio para Análise, Aprovado, Em Ajuste do Plano de Trabalho, Em Complementação, Em Elaboração, Enviado para Análise, Legado ADPF 854 STF / NT - TCU, Reprovado |

Lacunas que esta POC mostrou:
- **O módulo `parcerias` não cobre os convênios e contratos de repasse antigos** (Discricionárias e Legais, T1.2): as 12 propostas são todas de 2025 e 2026. Os instrumentos de 2024 em diante podem estar no CSV.
- Nenhum registro do município tem `nr_vlr_total`, datas de assinatura ou de captação: no módulo `parcerias` não dá para saber, só por estes campos, se o recurso foi liberado. Para `execucao` faltam pagamentos (`parcerias/ordem-pagamento`, `empenho-parceria`), ainda não consultados.
- Dos 2 planos de ação do `fundoafundo` (Cultura), o da Lei Paulo Gustavo tem vigência encerrada em 31/12/2024 (provável encerramento ou prestação de contas) e o da Aldir Blanc 2025 vai até 31/12/2029; nenhum campo diz se o recurso foi usado ou se as contas foram prestadas. (Correção de 29/10/2026: este texto dizia que os dois acabaram em 2024.)
- Para a regra `impedimento_emenda` (spec §5): o campo `motivo_impedimento_plano_acao` existe em `especiais`, mas **não pôde ser confirmado em dados reais** porque o município não tem registros ali.

## Transferegov — Discricionárias e Legais (antigo Siconv)

- Convênios e contratos de repasse. Publicado **apenas como arquivos CSV em lote**, sem API.
- Uso: baixar, filtrar pelo município, extrair proposta, situação, cláusula suspensiva, pagamentos.

**VERIFICADO em 29/10/2026** (POC `scripts/poc_transferegov_discricionarias.py`; amostras em `tests/fixtures/transferegov_discricionarias/`).

> **ALERTA, 29/10/2026 (T2.1): o endereço do download em lote saiu do ar.** De manhã a listagem `https://repositorio.dados.gov.br/seges/detru/` existia (arquivos de 17/07/2026) e todos os zips foram baixados. Às 18:17 (Brasília) o diretório inteiro responde **HTTP 404**, com qualquer cliente e `User-Agent` (`curl`, `httpx`), inclusive os zips e o `data_carga_siconv.txt`. A listagem do diretório pai (`/seges/`) responde 200 e **já não tem a pasta `detru/`**; `/seges/` e a raiz do repositório seguem no ar. Não achei endereço novo (a página do conjunto no dados.gov.br é renderizada por JavaScript e não expõe links). Causa e se é temporário: **desconhecidos**. Efeito: os coletores `transferegov_discricionarias` e `obrasgov` (que lê a ponte do mesmo servidor) falham com `ColetaErro` e a coleta das outras fontes segue normalmente. Os coletores foram validados com dados reais por um espelho local dos arquivos baixados de manhã (ver `docs/plano.md` T2.1). **O retrato `dados/brutos/transferegov_discricionarias/2026-10-29.json` (e a ponte do `obrasgov` de 2026-10-29) foi gerado desse espelho, não de uma coleta ao vivo**: o conteúdo é o do servidor oficial (carga de 17/07/2026), e a origem está registrada no `.log.json` de cada fonte (campo `origem`). Ele serve de "último retrato válido" enquanto o endereço estiver fora do ar.

Acesso:
- **URL:** `https://repositorio.dados.gov.br/seges/detru/` (listagem de diretório). Um zip por tabela: `siconv_<tabela>.csv.zip`. Sem autenticação; o servidor aceita `Range` e informa `Content-Length` e `Last-Modified` (dá para checar mudança com HEAD).
- **Defasagem:** `data_carga_siconv.txt` dizia `17/07/2026 06:30:47` e todos os zips têm `Last-Modified` de 17/07/2026, **104 dias antes da POC**. A frequência de atualização é **A VERIFICAR** (reconferir os HEAD nas próximas semanas). O site tem de mostrar "dados de <fonte> de <data>" (spec §9) com essa data.
- **Formato:** ZIP com um CSV; separador `;`; UTF-8 **com BOM**; campo vazio é texto vazio (não `null`); datas `dd/mm/aaaa` (a de publicação do contrato é `aaaa-mm-dd`; `DIA_HISTORICO_SIT` tem hora); valores com **vírgula decimal e sem milhar** (`1134,75`, mas também inteiros como `490038`); `SIM`/`NÃO`. Ler tudo como texto e converter na normalização.
- **Tamanho:** `proposta` 190 MB zipado (751 MB descompactado), `historico_situacao` 94 MB (579 MB), `convenio` 16 MB, `desembolso` 15 MB, `emenda` 7,7 MB, `proposta_cancelada` 10 MB, `prorroga_oficio` 1,7 MB (~340 MB no total). Ler em blocos (pandas `chunksize`) e guardar o zip em cache fora do Git. Não commitar os zips nem os CSV completos.
- **Dicionário de dados oficial:** `modelo_dados_siconv.zip` (HTML do SchemaSpy, com a descrição de cada coluna). As descrições citadas abaixo vêm dele.

Como filtrar pelo município:
- `siconv_proposta` e `siconv_proposta_cancelada`: coluna `COD_MUNIC_IBGE` (7 dígitos, `3532504`). As canceladas ficam **em arquivo à parte** (ids disjuntos de `siconv_proposta`).
- `siconv_convenio`: **não tem município**; liga por `ID_PROPOSTA`. `siconv_emenda` e `siconv_historico_situacao`: `ID_PROPOSTA`. `siconv_desembolso` e `siconv_prorroga_oficio`: `NR_CONVENIO`.
- `siconv_proponentes` (contém e-mail e telefone) e `siconv_contrato` (contratos de licitação dos convenentes, sem chave do município) não foram usados.

Resultado para Neves Paulista (carga de 17/07/2026):
- **256 propostas** (+ **7 canceladas**): 253 da prefeitura (CNPJ 45145414000147), 2 da Irmandade Santa Casa de Misericórdia e 1 do Lar São Vicente de Paulo (organizações da sociedade civil, mesmo código IBGE). Modalidades: contrato de repasse 142, convênio 89, "convênio ou contrato de repasse" 15, termo de compromisso 9, termo de fomento 1.
- **28 convênios/contratos de repasse** (8 com `INSTRUMENTO_ATIVO=SIM`), 12 emendas, 1.240 linhas de histórico de situação, 30 desembolsos, 22 prorrogações de ofício.
- **Só 16 das 263 propostas são de 2024 em diante** (`DIA_PROPOSTA`); 2 convênios foram assinados desde 2024; 1 foi assinado em 28/12/2023 e segue em execução até 20/12/2026. O recorte "desde 01/01/2024" da spec precisa de uma regra (ver pendências).
- As 16 propostas recentes: 5 "Rejeitados por Impedimento técnico" (2025), 3 "Rejeitados", 2 "Aprovados" (viraram os 2 convênios assinados em 2024 e 2025, ambos "Em execução"), 3 "Enviado para Análise", 1 "Cadastrados", 1 "Proposta Aprovada e Plano de Trabalho em Análise", 1 "Complementado em Análise" (com emenda).

Colunas úteis (nomes exatos):
- `siconv_proposta`: `ID_PROPOSTA`, `NR_PROPOSTA`, `DIA_PROPOSTA`, `ANO_PROP`, `MODALIDADE`, `DESC_ORGAO_SUP`, `DESC_ORGAO`, `IDENTIF_PROPONENTE`, `NM_PROPONENTE`, `NATUREZA_JURIDICA`, `SIT_PROPOSTA`, `SITUACAO_PROJETO_BASICO`, `SITUACAO_CONTA`, `OBJETO_PROPOSTA`, `DIA_INIC_VIGENCIA_PROPOSTA`, `DIA_FIM_VIGENCIA_PROPOSTA`, `VL_GLOBAL_PROP`, `VL_REPASSE_PROP`, `VL_CONTRAPARTIDA_PROP`.
- `siconv_convenio`: `NR_CONVENIO`, `ID_PROPOSTA`, `SIT_CONVENIO`, `INSTRUMENTO_ATIVO`, `IND_ASSINADO`, `DIA_ASSIN_CONV`, `DIA_INIC_VIGENC_CONV`, `DIA_FIM_VIGENC_CONV` ("data de fim de vigência"; a `_ORIGINAL_` é sem aditivos e prorrogações), `DIAS_PREST_CONTAS`, `DIA_LIMITE_PREST_CONTAS` ("data limite para prestação de contas"), `SITUACAO_CONTRATACAO` (Cláusula Suspensiva, Liminar Judicial, Normal, Sob Liminar Judicial e Cláusula Suspensiva), `DATA_SUSPENSIVA` ("data prevista para resolução da cláusula suspensiva"), `DATA_RETIRADA_SUSPENSIVA`, `MOTIVO_SUSPENSAO`, `QTD_PRORROGA`, `VL_GLOBAL_CONV`, `VL_REPASSE_CONV`, `VL_CONTRAPARTIDA_CONV`, `VL_EMPENHADO_CONV`, `VL_DESEMBOLSADO_CONV`, **`VL_SALDO_REMAN_TESOURO`** ("valores devolvidos ao Tesouro ao término do instrumento") e `VL_SALDO_REMAN_CONVENENTE` ("devolvidos ao Convenente"). A primeira é candidata a `valor_devolvido` (spec §8).
- `siconv_emenda`: `ID_PROPOSTA`, `NR_EMENDA`, `NOME_PARLAMENTAR`, `TIPO_PARLAMENTAR`, `IND_IMPOSITIVO`, `VALOR_REPASSE_EMENDA`.
- `siconv_historico_situacao`: `ID_PROPOSTA`, `NR_CONVENIO`, `DIA_HISTORICO_SIT`, `HISTORICO_SIT`, `DIAS_HISTORICO_SIT`. É a trilha de datas de cada mudança, mas **não traz o motivo**.
- `siconv_desembolso`: `NR_CONVENIO`, `DATA_DESEMBOLSO`, `VL_DESEMBOLSADO`. `siconv_prorroga_oficio`: `NR_CONVENIO`, `DT_FIM_PRORROGA`, `SIT_PRORROGA`.

Valores de situação **observados** para o município:

| Campo | Valores (contagem) |
| --- | --- |
| `siconv_proposta.SIT_PROPOSTA` | Proposta/Plano de Trabalho Enviado para Análise (122); Rejeitados (49); em Análise (33); Aprovados (27); Cadastrados (12); Proposta Aprovada e Plano de Trabalho em Análise (5); Rejeitados por Impedimento técnico (5); Proposta Aprovada e Plano de Trabalho Complementado em Análise (1); Proposta Eliminada em Chamamento Público (1); Proposta/Plano de Trabalho Complementado em Análise (1) |
| `siconv_proposta_cancelada.SIT_PROPOSTA` | Proposta/Plano de Trabalho Cancelados (7) |
| `siconv_convenio.SIT_CONVENIO` | Prestação de Contas Aprovada (11); Convênio Anulado (5); Prestação de Contas Concluída (3); Em execução (3); Prestação de Contas em Análise (3); Proposta/Plano de Trabalho Aprovado (1); Prestação de Contas Rejeitada (1); Proposta/Plano de Trabalho Complementado em Análise (1) |
| `siconv_convenio.INSTRUMENTO_ATIVO` | NÃO (20); SIM (8). Os 3 "Prestação de Contas em Análise", os 3 "Em execução" e os 2 "Proposta/Plano de Trabalho ..." são os ativos |
| `siconv_convenio.SITUACAO_CONTRATACAO` | Normal (19); vazio (5); Cláusula Suspensiva (4, com `MOTIVO_SUSPENSAO` "Titularidade de Área, Projeto de Engenharia e Licenciamento Ambiental Prévio") |
| `siconv_historico_situacao.HISTORICO_SIT` | 28 códigos, entre eles PROPOSTA_CADASTRADA, PROPOSTA_ENVIADA_ANALISE, PROPOSTA_EM_ANALISE, PROPOSTA_REPROVADA, PROPOSTA_REJEITADA_IMPEDIMENTO_TECNICO, PLANO_TRABALHO_APROVADO, ASSINADA, EM_EXECUCAO, AGUARDANDO_PRESTACAO_CONTAS, PRESTACAO_CONTAS_APROVADA, PRESTACAO_CONTAS_CONCLUIDA, PRESTACAO_CONTAS_REJEITADA, CONVENIO_ANULADO, PROPOSTA_ELIMINADA_EM_CHAMAMENTO_PUBLICO, RASCUNHO (lista completa na saída da POC) |
| `siconv_convenio.SUBSITUACAO_CONV` | sempre vazio |

Pendências desta fonte:
- O dicionário cita ainda em `SIT_CONVENIO` os valores "Prestação de Contas enviada para Análise", "Prestação de Contas em Complementação" e "Inadimplente", **não observados** no município.
- Os convênios antigos "Prestação de Contas em Análise" (3, ativos) têm vigência já encerrada; não foi verificado há quanto tempo estão nesse estado.
- `SITUACAO_CONTRATACAO = Cláusula Suspensiva` aparece em 4 convênios, mas `DATA_RETIRADA_SUSPENSIVA` está preenchida em 14: a regra `prazo_proximo` precisa checar se a suspensão ainda vale (T2.3).
- Nenhuma tabela traz o **motivo** da rejeição ou da anulação: só a situação e a data (`siconv_historico_situacao`). O motivo continua dependendo de documento (curadoria, spec §7).

## Obrasgov.br — API

- Host: `https://api-publica.obrasgov.gestao.gov.br`; **a API fica sob `/obras`** (a raiz é só uma página de apresentação).
- [Página oficial da API](https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-abertos-obrasgov-br_novo). Referência de terceiros (versão antiga da API): [obrasgovr](https://ftp.fau.de/cran/web/packages/obrasgovr/refman/obrasgovr.html); os nomes de endpoint e de campo abaixo são os da **nova versão**, lidos do OpenAPI.

**VERIFICADO em 29/10/2026** (POC `scripts/poc_obrasgov.py`, 36 requisições; amostras em `tests/fixtures/obrasgov/`).

Geral:
- **Documentação:** `{host}/obras/docs` (Swagger) e `{host}/obras/openapi.json` (FastAPI, v1.0, "nova versão do serviço"). Dicionário de dados: `modelo_dados_api_obrasgov.zip` no gov.br (não baixado nesta POC).
- **Autenticação:** nenhuma. **Limites:** não documentados; 36 requisições com pausa de 0,3 s não deram 429.
- **Paginação:** `pagina` e `tamanho_da_pagina` (máx. 200); envelope `{data, total_pages, total_items, page_number, page_size}`. `GET /data-atualizacao` → `{"data_ultima_atualizacao": "2026-10-29T00:00:00"}`.
- **Parâmetro desconhecido é ignorado** e devolve tudo (provado: `cod_ibgex` devolveu os 240.956 registros). O script valida contra o OpenAPI antes de chamar.
- Endpoints: `projeto-investimento`, `execucao-fisica`, `historico-situacao-cancelada-paralisada`, `geometria`, `contrato`, `empenho`, `estudo-viabilidade`, `data-atualizacao`. Valores monetários em reais (decimal); datas ISO, às vezes com hora.

Como achar as obras do município:
- **`geometria` tem `cod_ibge`** (inteiro) e funciona: 4 geometrias, 4 projetos. É a única rota por município.
- `projeto-investimento` não tem filtro por município (só `uf_principal`, `cnpj_organizacao_resp` etc.). **Filtrar pelo CNPJ da prefeitura devolveu 0**, porque a "organização responsável" é o Ministério da Economia (ou o DNIT). A prefeitura aparece em **`executores[].cnpj_executor`** (campo aninhado, não filtrável): 3 dos 4 projetos têm `45145414000147` como executor.
- **Ponte com o Siconv:** `https://repositorio.dados.gov.br/seges/detru/siconv_dados_obrasgov_geral.zip` (600 KB, CSV `;`) liga `id_projeto_investimento` a `nr_instrumento` (= `NR_CONVENIO`). As 3 obras da prefeitura casam 1 para 1: `106169.35-86` → convênio 990509; `31694.35-09` → 925702; `47960.35-00` → 970941. Valores e vigências também batem. A coluna `link_transparencia` desse arquivo traz usuário e senha `guest` na URL: **não copiar nem publicar** esses links.

Resultado para Neves Paulista (29/10/2026):
- **4 projetos, todos com `situacao = Cadastrada`**: 3 obras da prefeitura (habitação MCMV R$ 2,85 mi e R$ 3,41 mi; recapeamento R$ 486 mil; sistema `Transferegov.br`) e **1 projeto do DNIT** (manutenção rodoviária em todo o estado de SP, sistema `CIPI`, sem executor), que só tem uma geometria no município e **não é verba da prefeitura**.
- **Execução física: 0 registros. Histórico de cancelada/paralisada: 0 registros.** Contratos: 7 (todos do projeto do DNIT). Empenhos: 46 (43 do DNIT, 2 de `47960.35-00`, 1 de `106169.35-86`).
- **A `situacao` do Obrasgov não reflete a realidade nestes casos**: os três convênios correspondentes estão "Em execução" no Siconv (um com R$ 288.758,79 desembolsados), mas as obras seguem "Cadastrada" e sem nenhuma medição lançada. O cadastro é feito pelos gestores e fica desatualizado.

Estrutura dos endpoints sem dados no município (conferida em outros municípios, amostras em `tests/fixtures/obrasgov/exemplo_outros_municipios__*.json`):
- `execucao-fisica` (74.331 registros no país): `id_execucao_fisica`, `percentual_execucao_fisica`, `dt_inicial_execucao`, `dt_final_execucao`, `dt_cadastro_execucao`, **`dt_atualizacao_execucao`** (data da última atualização, base da regra `obra_parada`), `tipo_instrumento`, `tipo_forma_execucao`, e listas `indicativos` (`descricao_indicativo`) e `motivos` (`descricao_motivo`, ex.: "Revisão de projeto básico").
- `historico-situacao-cancelada-paralisada` (8.368 registros no país): `descricao_historico_situacao_investimento` (`Paralisada` ou `Cancelada`), `data_historico_situacao_investimento`, **`justificativa_cancelada_paralisada`** (texto livre, ex.: "Solicitado pela empresa e autorizado pela Secretaria de Obras do Município."), `possui_tratativas_situacao_investimento`, `fase_tratativas_situacao_investimento`. É a fonte do "porquê" nas obras, **mas é texto livre digitado pelo gestor**: só pode ser citado como documento, nunca reescrito como fato (spec §7). Na 1ª página, `fase_tratativas_...` veio sempre vazio.

Valores de `situacao` (OpenAPI, enum de `projeto-investimento`): `Cadastrada`, `Cancelada`, `Concluída`, `Em execução`, `Inacabada`, `Paralisada`. **Não existe "Suspensa"** (estava como exemplo no `status_map.yaml`). Contagem em SP (total_items): Cadastrada 15.170; Em execução 1.727; Concluída 3.587; Cancelada 239; Inacabada 75; Paralisada 19. No município, só `Cadastrada` foi observada.

Lacunas:
- A regra `obra_parada` (spec §5) precisa de `execucao-fisica`, que **não tem nenhum registro** do município: "sem dado de execução" não pode ser lido como "obra parada".
- O `cod_ibge` da geometria diz onde a obra está, não quem recebe o recurso (o projeto do DNIT mostra a diferença).
- `SIT_CONVENIO` do Siconv e `situacao` do Obrasgov podem discordar; falta decidir qual vale (ver `docs/decisoes.md`).

## Portal da Transparência (CGU) — API

- Host: `https://api.portaldatransparencia.gov.br/api-de-dados/`
- Autenticação: header `chave-api-dados`. Chave gratuita gerada com conta gov.br que tenha verificação em duas etapas.
- Limites: 400 requisições/min (700 entre 00h e 06h); acima disso a chave fica suspensa por 8 h.
- Referência: [cliente portaldatransparencia](https://github.com/guizsantos/portaldatransparencia).

**VERIFICADO em 29/10/2026** (T1.4, POC `scripts/poc_portal_transparencia.py`, 52 requisições; amostras em `tests/fixtures/portal_transparencia/`).

Acesso:
- **OpenAPI oficial** (público, sem chave): `https://api.portaldatransparencia.gov.br/v3/api-docs` (109 caminhos); Swagger em `/swagger-ui/index.html`. Os nomes abaixo vêm dele. O script valida cada parâmetro contra ele antes de chamar.
- **Chave:** header `chave-api-dados` (confirmado no OpenAPI). Sem chave a API responde HTTP 401 e cita a página de cadastro `portaldatransparencia.gov.br/api-de-dados/cadastrar-email`. A chave fica só em `PORTAL_TRANSPARENCIA_KEY` (variável de ambiente ou `.env`); o script nunca imprime nem grava o valor.
- **Limite:** 400 requisições/min (docs). O script usa intervalo mínimo de 0,2 s (300/min, `config/regras.yaml`), teto de 400 requisições por execução e **para na hora em 401, 403 ou 429, sem nova tentativa** (uma chave suspensa fica 8 h fora do ar). Nenhum cabeçalho de limite é devolvido; não houve 429.
- **Paginação:** `pagina` é obrigatório; **15 itens por página, sem total**: paginar até a página vir vazia. Valores monetários às vezes em número (`valor` de `/convenios`) e às vezes em texto brasileiro (`"1.234,56"`; estornos como `"- 7.174,10"`, com sinal e espaço): converter para centavos com `Decimal`, nunca com `float`.

Endpoints usados para o município:

| Endpoint | Filtro | Resultado para Neves Paulista |
| --- | --- | --- |
| `convenios` | `codigoIBGE` (funciona) | **63 convênios**, desde 1996: 62 da prefeitura e 1 da Santa Casa; inclui os históricos (dataInicioVigencia de 10/04/1996 a 30/12/2025) |
| `emendas` | sem filtro de município (só `codigoEmenda`, `numeroEmenda`, `nomeAutor`, `tipoEmenda`, `ano`, função) | **a emenda vem agregada**: `localidadeDoGasto = MÚLTIPLO` e os valores são os da emenda inteira (ex.: R$ 9,98 milhões empenhados numa emenda da qual o município recebe R$ 100 mil) |
| `despesas/recursos-recebidos` | `codigoFavorecido` (CNPJ) funciona; **`codigoIBGE` devolve vazio** (testado com 7 e 6 dígitos) | 103 linhas mensais para a prefeitura e os 2 fundos |
| `despesas/documentos-por-favorecido` | `codigoPessoa` (CNPJ), `fase` (1 empenho, 2 liquidação, 3 pagamento) e `ano`, todos obrigatórios | pagamentos (fase 3) de 2024 a 2026: 10 documentos |

`convenios` (campos): `id`, `dimConvenio.numero` e `.objeto`, `situacao`, `convenente`, `municipioConvenente.codigoIBGE`, `orgao`, `tipoInstrumento`, `subfuncao`, `dataInicioVigencia`, `dataFinalVigencia`, `dataPublicacao`, `dataUltimaLiberacao`, `dataConclusao`, `valor` (**repasse da União**, não o valor global: R$ 481.104,00 contra R$ 486.124,06 no Siconv), `valorContrapartida`, `valorLiberado`, `valorDaUltimaLiberacao`, `numeroProcesso`.
- **`situacao` (11 valores, 63 convênios):** CONCLUÍDO 26, PRESTAÇÃO DE CONTAS APROVADA 11, ARQUIVADO 7, CONVÊNIO ANULADO 5, NORMAL 3, EM EXECUÇÃO 3, PRESTAÇÃO DE CONTAS EM ANÁLISE 3, EXCLUÍDO 2, ADIMPLENTE 1, INADIMPLÊNCIA SUSPENSA 1, PRESTAÇÃO DE CONTAS REJEITADA 1. Vocabulário mais grosso que o do Siconv.
- **Ligação com o Siconv:** `dimConvenio.numero` é o **`NR_PROPOSTA`** do Siconv (formato `33961/2024`), **não** o `NR_CONVENIO` (0 em comum), e **com zeros à esquerda diferentes** (`04431/2016` no Portal, `4431/2016` no Siconv): normalizar antes de comparar. Os 63 convênios do Portal viram 61 números distintos (2 repetidos: `1586/1999` e um número no formato `CR.NR.0107614-79/`). **Só pelo número da proposta, 19 dos 28 convênios do Siconv casam**; mas **o número do processo é uma segunda chave**: `NR_PROCESSO` do Siconv = `numeroProcesso` do Portal (também sem zeros à esquerda). **Pelas duas chaves casam 26 dos 28**, e os 2 restantes são propostas sem convênio assinado ("Proposta/Plano de Trabalho Aprovado" e "Complementado em Análise"), que o Portal não lista. Todos os convênios em aberto do Portal casam com o Siconv, então a junção não duplica verbas (D12). (Correção de 29/10/2026: este texto dizia que 9 convênios antigos não tinham par; 7 deles casam pelo processo.)
- **Nos 19 que casam a situação é consistente, e o vocabulário se traduz:** Convênio Anulado → CONVÊNIO ANULADO (4), Em execução → EM EXECUÇÃO (3), Prestação de Contas Aprovada → PRESTAÇÃO DE CONTAS APROVADA (9) e **Prestação de Contas Concluída → NORMAL (3 de 3)**.
- **O Portal é mais atual que a carga do Siconv (17/07/2026):** o convênio `33961/2024` mostra R$ 938.758,79 liberados no Portal; o Siconv tinha R$ 288.758,79, e a diferença é exatamente a ordem bancária de R$ 650.000,00 de 23/07/2026 (`2026OB000885`).
- Filtro de datas: `dataInicial`/`dataFinal` ("data referência") com `codigoIBGE` devolveu vazio para um ano inteiro; **não usar** sem entender melhor.

`despesas/recursos-recebidos` (`mesAnoInicio` e `mesAnoFim` obrigatórios, `MM/AAAA`): períodos de até 13 meses funcionam; **34 meses deram HTTP 400**. Usar janelas de 12 meses. `codigoPessoa` volta formatado (`45.145.414/0001-47`). Campos: `anoMes`, `codigoPessoa`, `nomePessoa`, `municipioPessoa`, `nomeUG`, `nomeOrgao`, `nomeOrgaoSuperior`, `valor`. Soma por ano (prefeitura + Fundo Municipal de Saúde + Fundo Municipal de Assistência Social): **2024 R$ 4.378.747,04; 2025 R$ 4.120.779,24; 2026 (jan a out) R$ 3.736.911,51**, vindos de Saúde (34 linhas), Educação (33), Desenvolvimento e Assistência Social (32), Cidades (3) e Cultura (1).

`despesas/documentos-por-favorecido` (pagamentos, 2024 a 2026): Fundo Municipal de Saúde 5 documentos, R$ 292.825,90 líquidos (inclui um **estorno de R$ 7.174,10**); Fundo Municipal de Assistência Social 2, R$ 100.000,00; prefeitura 3, R$ 975.000,00 (Ministério das Cidades/FNHIS). Campos úteis: `data`, `documentoResumido`, `observacao`, `valor`, `orgaoSuperior`, `numeroProcesso`, **`autor`** (nas emendas, `4289 - DELEGADO BRUNO LIMA`: o código bate com o de `nr_emenda` do Transferegov) e `favorecidoIntermediario`. A `observacao` cita o instrumento (`CR.NR.0033961-PC2024`). Estornos aparecem como valor negativo.

Emendas: `codigoEmenda` = **ano + código do autor (4 dígitos) + sequência (4 dígitos)**, que é o `nr_emenda` do Transferegov sem os pontos (`2025.4289.0003` → `202542890003`); as 13 emendas distintas indicadas ao município foram achadas. `numeroEmenda` é só o sufixo de 4 dígitos e o filtro devolve emendas de qualquer lugar. Então **o Portal não dá o valor da emenda para o município**: quem diz que a emenda foi indicada é o Transferegov, e o que o município recebeu sai dos pagamentos (`autor` + `observacao`).

Lacunas:
- **Inexplicado:** `recursos-recebidos` mostra 34 linhas mensais do Fundo Municipal de Saúde, mas `documentos-por-favorecido` só lista 5 pagamentos dele. Os repasses regulares do fundo a fundo parecem não aparecer nesse endpoint.
- Não achei endpoint de "data da última atualização" nesta API.
- `documentos-por-favorecido` ainda não foi testado nas fases 1 (empenho) e 2 (liquidação).
- Nenhuma situação do Portal foi mapeada para `status_site` (o Portal não define status, D11). `ARQUIVADO` (7), `CONCLUÍDO` (26), `EXCLUÍDO` (2), `ADIMPLENTE` (1) e `INADIMPLÊNCIA SUSPENSA` (1) não casaram com instrumentos do Siconv na comparação (provavelmente são convênios antigos, pré-Siconv), então seu significado não foi confirmado.

## CAUC (Tesouro Nacional)

- Regularidade do município para transferências voluntárias.
- [Página do CAUC](https://www.gov.br/tesouronacional/pt-br/estados-e-municipios/cauc). Consulta pública: `cauc.tesouro.gov.br/ng/` (app Angular, sem API documentada; **não usada**, o CSV abaixo basta).

**VERIFICADO em 29/10/2026** (POC `scripts/poc_cauc.py`; amostras em `tests/fixtures/cauc/`).

Como coletar:
- **API CKAN do Tesouro Transparente**: `GET https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=cauc` (sem autenticação). Dentro de `resources`, o recurso de nome **"Relatório da situação dos municípios no CAUC"**, formato CSV, traz a `url` do arquivo. **Achar o recurso pelo nome a cada coleta**, sem fixar o endereço (é um upload que o Tesouro pode substituir). Há também o recurso dos estados e do DF e dois PDFs de metadados.
- **O CSV traz todos os municípios do país** (5.569 entes, 1,9 MB), não há filtro no servidor: baixar e filtrar por `Código IBGE` (`3532504`). Codificação **cp1252** (sem BOM), separador `;`, campos entre aspas, 3 linhas de metadados antes do cabeçalho (`Data da Pesquisa: dd/mm/aaaa`, tipo de ente, abrangência) e **uma legenda de 39 linhas no fim** (código do item e exigência, com os cinco grupos I a V). Linhas curtas fora da legenda devem ser tratadas como erro.
- **O arquivo é um retrato do dia, sem histórico**: o recurso é sobrescrito no mesmo endereço. A "data da pesquisa" está dentro do arquivo. **Qualquer série histórica só existirá a partir das nossas próprias coletas** (o Git guarda os retratos). A spec §7.2 ("extrato do CAUC mais próximo da data da perda") só vale daqui para a frente.
- **Frequência:** o texto do dataset diz "semanalmente", os metadados e o campo `Frequência de atualização` dizem diário, e o histórico de atividade do CKAN (60 eventos, 06/08 a 29/10/2026) mostra **atualização em dias úteis, por volta das 11:11 UTC (08:11 em Brasília)**, com algumas falhas isoladas (ex.: 22 e 23/09, 05 a 08/10). Uma coleta às 06:00 em Brasília pegaria o arquivo do dia útil anterior, por isso a coleta diária passou para as 09:00 (D9). Usar sempre a "data da pesquisa" do arquivo como data do dado: em fins de semana e feriados ela continuará sendo a do último dia útil.

Semântica (dicionário oficial, PDF "Metadados CAUC – Municípios", e legenda do arquivo):
- Colunas `1.1` a `5.7` (28 itens). A legenda tem ainda `4.3` e `5.8`, que **não têm coluna** no arquivo, além dos itens-pai `2.1`, `3.1`, `3.2`, `3.4`.
- **Célula = data de validade da comprovação do requisito** (`dd/mm/aa`). **`!` = o CAUC não conseguiu obter a comprovação do requisito.** **`Desabilitado` = informação do item indisponível na data da consulta, vale para todos os entes.** Informações referem-se ao CNPJ principal do município (a prefeitura).
- Observado em todo o arquivo (5.569 entes × 28 itens): 134.959 datas, 9.835 `!`, 11.138 `Desabilitado`, nenhuma célula vazia e **nenhuma data anterior à data da pesquisa**. Valor novo no arquivo deve gerar erro, nunca ser interpretado ao acaso.
- O dicionário não diz o que acontece com uma data que vence: ela some ou vira `!`. **A VERIFICAR** acompanhando coletas diárias.

Resultado para Neves Paulista (Código IBGE 3532504, SIAFI 6751, população 8.777; data da pesquisa 29/10/2026):
- 25 itens com data de validade, 2 `Desabilitado` (`1.3` FGTS, `3.2.4` Siops) e **1 item sem comprovação: `4.2` Regularidade Previdenciária**.
- Validades mais próximas: 29/10/2026 (itens `1.2`, `1.4`, `1.5`, `2.1.1`, `2.1.2`, `3.5`, `3.6`, `3.7`, `5.2`) e 31/10/2026 (`3.4.1`); a mais distante é 30/04/2027. Muitos itens são reconfirmados todo dia.
- **Contexto:** 307 dos 645 municípios de SP e 3.247 dos 5.569 do país têm ao menos um item sem comprovação. Ter um `!` é comum, o que pesa no tom do alerta (spec §1: "nunca acusatório").

Lacunas:
- O arquivo não diz **quais itens bloqueiam qual tipo de transferência**: o CAUC exige itens diferentes por instrumento e há dispensas legais (por exemplo, transferências fundo a fundo na saúde, educação e assistência social). A regra `cauc_sem_comprovacao` (antes `cauc_irregular`) vale só para `voluntaria` e `emenda_finalidade` em `proposta` e `aprovada` e alerta para **qualquer** item `!` (decisão da autora em 29/10/2026); o texto diz o item, sem a palavra "irregular".
- O CAUC mede a regularidade do **município**, não de um instrumento: o mesmo alerta aparece em todas as verbas elegíveis.

## Tesouro — Transferências Constitucionais e SICONFI

- Transferências constitucionais: `https://apiapex.tesouro.gov.br/aria/v1/transferencias_constitucionais/custom/`
- SICONFI: `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/` (**não verificado**: fora do escopo da T1.6).
- Referência: pacote [tesouror](https://rdrr.io/cran/tesouror/f/README.md) (código em [github.com/StrategicProjects/tesouror](https://github.com/StrategicProjects/tesouror), arquivo `R/transferencias.R`).

### Transferências constitucionais (FPM, ITR e outras)

**VERIFICADO em 29/10/2026** (POC `scripts/poc_tesouro.py`, 8 requisições; amostras em `tests/fixtures/tesouro/`).

Documentação e acesso:
- **Não achei OpenAPI nem documentação oficial** (testei `/aria/docs`, `/aria/openapi.json`, `/aria/v1/api-docs`, swagger). Os nomes de endpoint e de parâmetro vêm do código do pacote de terceiros `tesouror` e **foram confirmados por chamadas reais**. Sem autenticação; limites não documentados (as 8 chamadas não deram 429); respostas lentas (1 s nos dicionários, 5 a 7 s nos valores): guardar em cache.
- **A URL base sozinha dá HTTP 500** (`{"status":"erro","errorMessage":"... Endpoint não encontrado"}`), mesmo com a API no ar. Por isso `config/fontes.yaml` tem `url_teste` (`.../custom/estados`) para o teste de acesso.
- **Os nomes dos parâmetros diferem de caixa entre endpoints** e nome errado é perigoso: segundo o pacote, o servidor ignora o parâmetro, tenta devolver a série inteira e estoura o tempo (HTTP 504). Não reproduzi de propósito. O script só aceita os nomes da lista abaixo.

Endpoints (todos `GET {base}/<endpoint>`; resposta `{"registros": [...], "status": "ok"}`):

| Endpoint | Parâmetros (caixa exata) | Observação |
| --- | --- | --- |
| `transferencias` | nenhum | dicionário: 18 tipos (código e nome) |
| `estados` | nenhum | dicionário: 27 UFs com código do Tesouro |
| `municipios` | `p_nome`, `p_uf` | `p_nome=Neves Paulista` → `{"codigo": 6751, "codigo_uf": 26, "nome": "Neves Paulista"}` |
| `por_estado_municipio` | `p_estado`, `p_municipio`, `p_ano`, `p_mes`, `p_transferencia`, `p_sn_detalhar`, `page`, `pageSize` (minúsculas) | **paginado**: 10 linhas por página por padrão, `pageSize=500` funciona; o campo `next` vem **sempre** preenchido (e com `aria//v1`, barra dupla), então parar quando a página vier incompleta |
| `por_estado_municipio_detalhe` | `P_ESTADO`, `P_MUNICIPIOS` (plural), `P_ANO`, `P_MES`, `P_TRANSFERENCIA` (MAIÚSCULAS) | sem paginação; traz `VA_PRIMEIRO_DEC`, `VA_SEGUNDO_DEC`, `VA_TERCEIRO_DEC` e `TOTAL` |
| `por_estados`, `por_estados_detalhe` | (por estado) | existem segundo o pacote; não testados |

Códigos (são **do Tesouro, não do IBGE**):
- **Município: 6751 = o Código SIAFI** que aparece no CAUC (§CAUC). Estado: **26** = São Paulo. As linhas devolvidas trazem também `CO_IBGE` (3532504) e `UF`, o que permite conferir.
- Tipos: 1 CIDE-Combustíveis, 2 FEX, **3 FPM**, **4 ITR**, 5 LC 87/96 (Lei Kandir), 6 IOF-Ouro, 7 FPE, 8 FUNDEF, 9 IPI-Exp, 10 FUNDEB, 11 AFM/AFE, 12 Royalties, 13 Cessão Onerosa, 14 Ajuste FUNDEB, 15 LC 173/2020 (PFEC), 16 LC 176/2020 (ADO25), 17 LC 201/2023 (compensação ICMS), 18 **FPM 1%**.
- **O nome do tipo nas linhas nem sempre é o do dicionário**: o dicionário diz `Royalties : ANP, FEP, PEA, ITAIPU, CFH e CFEM` e as linhas dizem `Royalties`. As linhas só trazem o nome, não o código.

Linhas de `por_estado_municipio`: `UF`, `ANO` (texto), `MES` (texto, `"09"`), `TRANSFERENCIA`, `codigo_siafi`, `CO_IBGE`, `MUNICIPIO`, `VALOR` (decimal em **reais**; converter para centavos com `round(valor * 100)`, nunca `int(valor * 100)`: `int(0.29 * 100)` dá 28).

Resultado para Neves Paulista (consulta de 29/10/2026):
- Linhas: 64 em 2024, 68 em 2025, 56 em 2026. Tipos presentes: CIDE-Combustíveis, FPM, FPM 1%, FUNDEB, Ajuste FUNDEB, ITR, LC 176/2020 (ADO25), Royalties. FPM e ITR não têm mês repetido (os outros tipos não foram conferidos).
- **FPM:** 2024 R$ 14.317.574,69; 2025 R$ 13.846.100,14; 2026 (jan a out) R$ 11.768.583,74. **ITR:** 2024 R$ 375.046,43; 2025 R$ 440.420,42; 2026 (jan a out) R$ 349.119,83. FPM e ITR têm os 12 meses de 2024 e 2025. FPM 1% aparece em poucos meses (5 linhas no período).
- **O mês corrente está incompleto.** Em outubro/2026 o FPM veio com R$ 621.852,86 (3º decêndio **zerado**; setembro foi R$ 1.000.410,68) e o ITR com R$ 208.700,34. `VALOR` é a soma dos três decêndios (conferido: 438.787,51 + 183.065,35 + 0 = 621.852,86), e a consulta foi feita no dia 29, antes do fim do mês: pelo que se vê, o mês fecha quando o 3º decêndio entra (inferência, não confirmada pela documentação). O site deve rotular o mês em andamento ou usar só meses fechados.
- Não existe endpoint de "data da última atualização" nesta API.

Lacunas:
- **A VERIFICAR:** se `VALOR` é bruto ou líquido (por exemplo, antes ou depois do desconto do FUNDEB, que aparece como linha própria). O endpoint de detalhe só devolve `SG_DETALHE = FPM`/`ITR`, sem decompor. A spec (§2) usa FPM e ITR só como número de referência, mas o texto do site precisa dizer "bruto" ou "líquido" só depois dessa confirmação.
- Não há data de pagamento por decêndio, só os valores.
- `LC 201/2023 (compensação ICMS)` e outros tipos do dicionário não apareceram para o município em 2024 a 2026.

## Oportunidades (programas e editais que o município pode pleitear)

**VERIFICADO em 29/10/2026** (T1.7, POC `scripts/poc_oportunidades.py`; amostras em `tests/fixtures/oportunidades/`). Há fonte automática, com ressalvas.

**Fonte principal: Siconv em lote** (mesmo servidor das Discricionárias, §Transferegov — Discricionárias e Legais), 4 arquivos além dos já usados: `siconv_programa` (11 MB zipado, 353 MB descompactado), `siconv_programa_proponentes` (2 MB), `siconv_proposta_selecao_pac` (38 MB, 125 MB descompactado) e `siconv_proponentes` (6 MB; contém e-mail e telefone: usar só `ID_PROPONENTE` e `IDENTIF_PROPONENTE`).
- `siconv_programa`: `ID_PROGRAMA`, `COD_PROGRAMA`, `NOME_PROGRAMA`, `SIT_PROGRAMA` (`DISPONIBILIZADO` 1.004.603 linhas, `CADASTRADO` 128.234, `INATIVO` 122.377), `DESC_ORGAO_SUP_PROGRAMA`, `MODALIDADE_PROGRAMA`, `NATUREZA_JURIDICA_PROGRAMA` (quem pode propor), `UF_PROGRAMA`, `NOME_SUBTIPO_PROGRAMA` (`NOVO PAC`, `NOVO PAC - FORMALIZAÇÃO`, `MCMV FNHIS`, `ECTI`, `FIIS`, `TEC`, `TCC`) e três janelas `dd/mm/aaaa`: **`DT_PROG_INI/FIM_RECEB_PROP`** (propostas voluntárias), `DT_PROG_INI/FIM_EMENDA_PAR` (emendas) e `DT_PROG_INI/FIM_BENEF_ESP` (beneficiários específicos).
- **A tabela repete o programa por UF e natureza jurídica**: 1.255.214 linhas para 52.935 programas. Contar e filtrar sempre por `ID_PROGRAMA` distinto.
- Sem filtro por município: o recorte é por **natureza jurídica** (contém "Municipal") e **UF** (`SP` ou vazio). `siconv_programa_proponentes` (`ID_PROGRAMA`, `ID_PROPONENTE`) lista os programas dirigidos a proponentes específicos. A prefeitura é o proponente `ID_PROPONENTE = 15310` (achado por `IDENTIF_PROPONENTE = 45145414000147` em `siconv_proponentes`).
- **Atenção à defasagem:** é a carga de 17/07/2026. Programas criados depois não aparecem e "aberto hoje" é um **mínimo**.

Resultado (janelas avaliadas em 29/10/2026 sobre a carga de 17/07/2026; programas distintos):

| Medida | Resultado |
| --- | --- |
| Janela de propostas voluntárias aberta (todo o país) | 46 programas (1.148 linhas) |
| Janela de emendas aberta / de beneficiários específicos aberta | 97 / 34 programas |
| **Abertos e elegíveis** (natureza municipal, UF SP ou sem UF) | **9 programas: 7 `DISPONIBILIZADO`, 1 `CADASTRADO`, 1 `INATIVO`**, todos até 31/12/2026: Educação (DIEA/Capes, 2; SIMEC/PAR, 2), Agricultura (Fomento ao Setor Agropecuário, PRONER, PROMAQ), INCRA (infraestrutura básica) |
| **Programas dirigidos à prefeitura** (`siconv_programa_proponentes`) | 68 programas; **3 com alguma janela aberta** |
| Novo PAC Seleções da prefeitura (`siconv_proposta_selecao_pac`) | **10 propostas em 9 programas** (todos `NOVO PAC`, `DISPONIBILIZADO`): 5 `SELECIONADA`, 2 `HABILITADA`, 2 `ENVIADA`, 1 `NAO_HABILITADA`. Ex.: renovação de frota do SAMU (selecionada), unidade básica de saúde (não habilitada), produção de unidades habitacionais (selecionada, R$ 2,8 mi) |

Fontes complementares, Transferegov API (`parcerias`):
- `parcerias/programa` (92 programas `Disponibilizado` no país; sem filtro por município; `uf_habilitada_sg_uf=SP` devolve 3 de 182): campos `situacao_programa`, `qualificacao_beneficiario` (68 "Beneficiário de Emenda Parlamentar", 23 "Beneficiário Espontâneo", 1 "Específico"), janelas `dt_inicio/fim_beneficiario_espontaneo|especifico|emenda`, `expiracao_prog_*` e `programa_atende_a`. **Nenhuma janela espontânea aberta hoje** (as 23 estão `prog_expirado`); as únicas abertas são 5 programas de emenda do SUAS (até 31/12/2026), que só valem para quem tem emenda indicada. Logo, aqui não há oportunidade aberta para o município.
- `parcerias/beneficiario_emenda_parlamentar` (filtros `nm_municipio_beneficiario_emenda` e `sg_uf_beneficiario_emenda`): **14 emendas indicadas** ao município (12 ao Fundo Municipal de Saúde, 2 ao de Assistência Social; 2025: 5, 2026: 9; total R$ 2,1 milhões), com `nr_emenda`, `nm_parlamentar` (nome público do autor, permitido pela spec §8), `in_tipo_emenda_parlamentar` e `vl_total_emenda`. São a origem das 12 propostas do §T1.1, mas **não dá para casar emenda com proposta 1 para 1** (uma proposta pode juntar emendas; por exemplo, o programa 14 tem 4 emendas e 5 propostas): o cruzamento por (programa, CNPJ) sugere emendas de 2026 ainda sem proposta, **sem confirmação**.
- `fundoafundo/programas-beneficiarios` (§T1.1): os 6 programas ligados ao município (Aldir Blanc 2020, 2021 e 2025, Gratuidade EC 123/22, Lei Paulo Gustavo, PNAB) têm **todas as janelas de recebimento já encerradas** (2020 a 2025), embora a situação seja `DISPONIBILIZADO`. A situação do programa não indica se há prazo aberto: usar as datas.
- `especiais/programas-especiais` tem janela de ciência por programa, mas o município não consta como beneficiário do módulo (§T1.1): sem oportunidade ali.

Novo PAC Seleções: não achei API própria; os dados chegam por `siconv_programa` (subtipo `NOVO PAC`) e `siconv_proposta_selecao_pac`. A página do programa no gov.br não foi explorada.

Lacunas:
- A carga de 17/07/2026 não mostra programas criados desde então; se o Siconv publicar cargas mais frequentes, o número de oportunidades abertas muda.
- O Novo PAC Seleções das propostas do município tem situações próprias (`SELECIONADA`, `HABILITADA`, `ENVIADA`, `NAO_HABILITADA`) que **ainda não foram mapeadas** para `status_site` (decisão pendente; `NAO_HABILITADA` é candidata a `perdida`, com motivo só por documento).
- `siconv_programa` não traz o valor do programa nem o texto de elegibilidade além da natureza jurídica e da UF.

## Fontes sem API (fase 1.5 / fase 2)

| Fonte | O que traz | Plano |
| --- | --- | --- |
| Fundo Nacional de Saúde (consultafns, InvestSUS) | Repasses de saúde, propostas | Extração de página, A VERIFICAR |
| FNDE (PAR, painel de obras; SIOPE tem OData) | Educação | Obras do PAR também aparecem no Obrasgov |
| Diário Oficial do município | Licitações desertas, rescisões, ofícios | Coleta de PDF + texto para o dossiê da curadoria (fase 1.5) |
| Portal da Transparência do município | Empenhos, licitações | Fornecedor e formato A VERIFICAR |
| TCE-SP Portal da Transparência Municipal | Receitas e despesas do município | Tem seção de APIs e conjuntos de dados; útil para confirmar entrada no caixa |
| Governo de SP | Convênios e emendas estaduais | Fase 2 |

## Contexto regulatório útil para a curadoria

- Exigências do CAUC e regras de transferências discricionárias: Portaria Conjunta MGI/MF/CGU nº 33/2023.
- Emendas Pix: o STF (ADPF 854) exige plano de trabalho com objeto definido e conta específica por emenda; decisão de 07/08/2026 mandou apurar irregularidades ([notícia do STF](https://noticias.stf.jus.br/postsnoticias/stf-determina-que-pf-apure-possiveis-crimes-na-execucao-de-emendas-pix/)).
