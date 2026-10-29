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
- URL do download em lote: **A VERIFICAR** (historicamente no repositório de dados abertos da SEGES/DETRU).
- Uso: baixar, filtrar pelo município, extrair proposta, situação, cláusula suspensiva, pagamentos.

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
