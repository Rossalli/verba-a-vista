# Fontes de dados

Estado em 29/10/2026. Tudo marcado **A VERIFICAR** precisa ser confirmado numa prova de conceito (plano, Marco 1) antes de virar código de produção. Ao confirmar, troque a marca por **VERIFICADO em <data>** e registre o que achou.

Identificadores do município: código IBGE **3532504**; UF SP; CNPJ da prefeitura **A VERIFICAR**.

## Acesso

Em 29/10/2026, um teste feito de um servidor fora do Brasil recebeu bloqueio (proxy 403) para Transferegov, Obrasgov, Portal da Transparência e TCE-SP. Isso pode ser restrição do ambiente de teste, não das fontes. Resultado da T1.0:

| Fonte | Local (Brasil) | GitHub Actions |
| --- | --- | --- |
| Transferegov API | HTTP 200 nas páginas `/docs` de `especiais`, `fundoafundo` e `parcerias` (29/10/2026) | A VERIFICAR |
| Obrasgov API | HTTP 200 na URL base (29/10/2026) | A VERIFICAR |
| Portal da Transparência API | HTTP 401 na URL base sem chave, esperado: o host responde (29/10/2026) | A VERIFICAR |
| Tesouro (APIs) | HTTP 500 na URL base de transferências constitucionais (29/10/2026): o host responde, mas a URL sem rota não prova o endpoint; confirmar na T1.6 | A VERIFICAR |
| Tesouro Transparente (CAUC) | Não testado: URL desconhecida (T1.5) | A VERIFICAR |

Teste local feito em 29/10/2026 às 14:57 (America/Sao_Paulo) com `scripts/teste_acesso.py`, a partir do Brasil, sem credenciais. O teste só prova que o host responde; endpoints, filtros e autenticação continuam A VERIFICAR nas POCs. Para a coluna do GitHub Actions: workflow `.github/workflows/teste-acesso.yml` (disparo manual).

## Transferegov — API pública

- Host: `https://api-publica.transferegov.gestao.gov.br`
- Módulos: `especiais` (emendas Pix), `fundoafundo`, `parcerias` (programas, propostas, parcerias, execução financeira), `ted`.
- Documentação: `/especiais/docs`, `/fundoafundo/docs`, `/parcerias/docs`, `/ted/docs`.
- Autenticação: nenhuma documentada. **A VERIFICAR.**
- Cuidado: a API ignora parâmetros desconhecidos e devolve a tabela inteira com HTTP 200. Valide os nomes de parâmetros contra a documentação antes de chamar.
- Exemplo de parâmetro visto: `situacao_proposta` (módulo `parcerias`), `sg_uf_recebedor`.
- Filtro por município: **A VERIFICAR.**
- Valores de situação: **A VERIFICAR.**
- Referência: pacote Python [transferegovpy](https://pypi.org/project/transferegovpy/).

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
