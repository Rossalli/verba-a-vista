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
| `fundoafundo/planos-acao` | **`codigo_ibge_*` dá HTTP 500** ("Erro Interno Inesperado"), testado com 7 dígitos (recebedor e repassador) e com 6 dígitos (recebedor). Funcionam: `nome_municipio_ente_recebedor_plano_acao` (ignora caixa) e `cnpj_ente_recebedor_plano_acao`. | 2 planos de ação (Ministério da Cultura, vigência até 31/12/2024), ambos `AUTORIZADO` |
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
- Os 2 planos de ação do `fundoafundo` (Cultura) tinham vigência até 31/12/2024: provável convênio encerrado ou em prestação, sem campo de situação que diga isso.
- Para a regra `impedimento_emenda` (spec §5): o campo `motivo_impedimento_plano_acao` existe em `especiais`, mas **não pôde ser confirmado em dados reais** porque o município não tem registros ali.

## Transferegov — Discricionárias e Legais (antigo Siconv)

- Convênios e contratos de repasse. Publicado **apenas como arquivos CSV em lote**, sem API.
- Uso: baixar, filtrar pelo município, extrair proposta, situação, cláusula suspensiva, pagamentos.

**VERIFICADO em 29/10/2026** (POC `scripts/poc_transferegov_discricionarias.py`; amostras em `tests/fixtures/transferegov_discricionarias/`).

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

- Host: `https://api-publica.obrasgov.gestao.gov.br`
- Autenticação: não exige (segundo a documentação do pacote [obrasgovr](https://ftp.fau.de/cran/web/packages/obrasgovr/refman/obrasgovr.html)).
- Recursos: projetos de investimento, execução física, contratos, empenhos, geometrias, estudos de viabilidade, histórico de situação, data da última atualização.
- **Histórico de situação traz projetos cancelados ou suspensos com motivos e providências.** Principal fonte automática de "porquê".
- Filtro por município: **A VERIFICAR** (exemplos usam `uf_principal`).
- [Página oficial da API](https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-abertos-obrasgov-br_novo).

## Portal da Transparência (CGU) — API

- Host: `https://api.portaldatransparencia.gov.br/api-de-dados/`
- Autenticação: header `chave-api-dados`. Chave gratuita gerada com conta gov.br que tenha verificação em duas etapas.
- Limites: 400 requisições/min (700 entre 00h e 06h); acima disso a chave fica suspensa por 8 h.
- Endpoints relevantes: `convenios`, emendas, despesas por favorecido. **Nomes exatos A VERIFICAR no Swagger oficial.**
- Referência: [cliente portaldatransparencia](https://github.com/guizsantos/portaldatransparencia).

## CAUC (Tesouro Nacional)

- Regularidade do município para transferências voluntárias; atualização diária.
- Consulta pública: `cauc.tesouro.gov.br`. Dataset no Tesouro Transparente (há documento de metadados "TT CAUC – Municípios").
- Forma de coleta automática: **A VERIFICAR**.
- [Página do CAUC](https://www.gov.br/tesouronacional/pt-br/estados-e-municipios/cauc).

## Tesouro — Transferências Constitucionais e SICONFI

- Transferências constitucionais: `https://apiapex.tesouro.gov.br/aria/v1/transferencias_constitucionais/custom/`
- SICONFI: `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/`
- Referência: pacote [tesouror](https://rdrr.io/cran/tesouror/f/README.md).

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
