# Plano de implementação — fase 1

Uma tarefa por vez, em ordem. Marque `[x]` ao concluir e escreva uma linha do que foi feito. Cada tarefa tem critério de aceite; ela só está pronta quando o critério é verificado e `make test` passa.

## Marco 0 — Fundação

- [x] **T0.1 Esqueleto do repositório.** `pyproject.toml` (Python 3.12, deps do CLAUDE.md), `Makefile` com os alvos do CLAUDE.md (podem ser stubs), `pytest` configurado, `.gitignore`, pastas de `dados/` com `.gitkeep`.
  *Aceite:* `make test` roda e passa com um teste trivial.
  *Feito:* pyproject (extra `dev` com pytest, respx, jsonschema), Makefile com stubs, pacotes vazios `coleta/ nucleo/ curadoria/`, `tests/test_esqueleto.py`, venv 3.12 via uv. Teste passa com `.venv/Scripts/python -m pytest`; `make` não está instalado nesta máquina Windows, então o alvo `make test` em si não foi executado.
- [x] **T0.2 Modelo Verba.** `nucleo/modelo.py` com pydantic v2 espelhando `schemas/verba.schema.json`. Teste que valida um exemplo mínimo e rejeita `status_site` inválido.
  *Aceite:* o modelo exporta JSON que valida no schema.
  *Feito:* `nucleo/modelo.py` (`Verba` e submodelos, `extra="forbid"`, centavos como int estrito, `para_dict()`/`para_json()` com `exclude_unset`) e `tests/test_modelo.py` (31 testes: mínimo e completo validam no schema, `status_site` inválido rejeitado, ida e volta, e os Literals conferidos contra os enums do schema). 32 testes passam.
- [x] **T0.3 Leitura de configuração.** Carregar `config/*.yaml` com validação (pydantic). Erro claro se faltar chave.
  *Aceite:* teste com config válida e inválida.
  *Feito:* `nucleo/config.py` (`carregar_config()` valida os 4 arquivos; `ConfigErro` cita arquivo e caminho da chave; chaves desconhecidas são erro; checagens cruzadas no status_map, na taxonomia e no limite do Portal) e `tests/test_config.py` (18 testes, config real e inválidas). 50 testes passam.

## Marco 1 — Provas de conceito das fontes (use `/poc-fonte`)

Objetivo: confirmar acesso, endpoints, filtros por município e valores de situação. Resultado de cada POC vai para `docs/fontes.md` (seção da fonte) e para `config/status_map.yaml`.

- [x] **T1.0 Teste de acesso a partir do ambiente de execução.** Script `scripts/teste_acesso.py` que faz uma requisição simples a cada base URL de `config/fontes.yaml` e reporta status. Rodar localmente (Brasil) e no GitHub Actions.
  *Aceite:* tabela em `docs/fontes.md` §Acesso com o resultado dos dois ambientes. Se o Actions for bloqueado, registrar em `docs/decisoes.md` a decisão sobre onde rodar a coleta.
  *Feito:* script e workflow manual; local e Actions deram o mesmo resultado (hosts respondem, sem bloqueio). Tabela em `docs/fontes.md` §Acesso; nota em `docs/decisoes.md` (Em aberto). Falta só reconferir os endpoints reais do Actions nas T1.1 e T1.4.
- [x] **T1.1 POC Transferegov API** (módulos `especiais`, `fundoafundo`, `parcerias`). Descobrir parâmetro de filtro por município/CNPJ, campos de situação e seus valores distintos.
  *Feito (29/10/2026):* `scripts/poc_transferegov_api.py` (valida parâmetros contra o OpenAPI), amostras em `tests/fixtures/transferegov_api/`, `docs/fontes.md` preenchido, `status_map.yaml` com os valores observados. Achados: filtro por IBGE só em `parcerias/proposta` e `fundoafundo/programas-beneficiarios` (em `planos-acao` dá HTTP 500, usar CNPJ 45145414000147); 12 propostas, 2 planos de ação, 0 emendas Pix; CNPJ da prefeitura confirmado. Pendente: `especiais` sem dados do município (campo `motivo_impedimento_plano_acao` não confirmado); convênios antigos ficam para a T1.2.
- [x] **T1.2 POC Transferegov Discricionárias e Legais (CSV).** Localizar o download em lote atual, baixar, filtrar por município, listar situações distintas de proposta e convênio.
  *Feito (29/10/2026):* `scripts/poc_transferegov_discricionarias.py`, amostras em `tests/fixtures/transferegov_discricionarias/`, `docs/fontes.md` preenchido, `status_map.yaml` com duas entradas (`..._proposta` e `..._convenio`, só valores observados). Achados: download em `repositorio.dados.gov.br/seges/detru/` (zip por tabela, ~340 MB para o município); **carga de 17/07/2026, 104 dias de defasagem**; 256 propostas + 7 canceladas, 28 convênios, mas só 16 propostas de 2024+; `valor_devolvido` pode vir de `VL_SALDO_REMAN_TESOURO` (dicionário oficial). Recorte da spec §2 esclarecido (proposta 2024+ ou instrumento ativo). Nenhuma tabela traz o motivo de rejeição ou anulação.
- [x] **T1.3 POC Obrasgov.** Projetos do município, execução física, histórico de situação (motivos e providências).
  *Feito (29/10/2026):* `scripts/poc_obrasgov.py`, amostras em `tests/fixtures/obrasgov/`, `docs/fontes.md` preenchido, `status_map.yaml` (mapa vazio de propósito), D8 e spec §4/§5/§6.1 ajustadas. Achados: API sob `/obras`, filtro por município só via `geometria.cod_ibge`; 4 projetos, 3 da prefeitura (executora, não "responsável") ligados a convênios do Siconv pela ponte `siconv_dados_obrasgov_geral`, 1 do DNIT (fora); todos "Cadastrada", **sem execução física nem histórico de paralisação**; estrutura de `motivos` e `justificativa` conferida em outros municípios. Obrasgov é fonte auxiliar (D8).
- [x] **T1.4 POC Portal da Transparência.** Com chave: convênios e emendas do município. Confirmar endpoints no Swagger oficial.
  *Feito (29/10/2026):* `scripts/poc_portal_transparencia.py` (limite de requisições, parada em 401/403/429, chave só por ambiente), amostras em `tests/fixtures/portal_transparencia/`, `docs/fontes.md`, `status_map.yaml` (mapa vazio), spec §3/§4, D11. Achados: OpenAPI público em `/v3/api-docs`; 63 convênios por `codigoIBGE`; número do Portal = `NR_PROPOSTA` do Siconv (sem zeros à esquerda), 19 de 28 casam e a situação é consistente; **Portal mais atual que a carga do Siconv** (R$ 650 mil de 23/07/2026); **emenda agregada (`MÚLTIPLO`)**, sem o valor do município; `recursos-recebidos` só por CNPJ (`codigoIBGE` devolve vazio; período > 13 meses dá 400); pagamentos com `autor` (código da emenda) e estornos negativos. Portal é fonte de complemento (D11).
  *Marco 1 concluído: T1.0 a T1.7.*
- [x] **T1.5 POC CAUC.** Obter a situação do município (dataset do Tesouro Transparente ou consulta pública) com data.
  *Feito (29/10/2026):* `scripts/poc_cauc.py`, amostras em `tests/fixtures/cauc/`, `docs/fontes.md` preenchido, `fontes.yaml` ajustado. Achados: CSV do CKAN do Tesouro Transparente (todos os municípios, cp1252, legenda no fim, achar o recurso pelo nome); retrato do dia **sem histórico**; atualizado em dias úteis às ~08:11 BRT; `!` = sem comprovação, célula = data de validade; Neves Paulista tem 1 item `!` (4.2 Regularidade Previdenciária) e 2 `Desabilitado`. Decisões: alerta renomeado para `cauc_sem_comprovacao` (qualquer item, texto cita o item) e coleta diária às 09:00 (D9).
- [x] **T1.6 POC Tesouro Transferências Constitucionais.** FPM e ITR do município por mês.
  *Feito (29/10/2026):* `scripts/poc_tesouro.py`, amostras em `tests/fixtures/tesouro/`, `docs/fontes.md` preenchido, `url_teste` no `fontes.yaml`. Achados: sem OpenAPI (nomes confirmados por chamadas reais, a partir do pacote `tesouror`); código do município é o do Tesouro (6751 = SIAFI do CAUC), não o IBGE; parâmetros com caixa diferente por endpoint; FPM 2024 R$ 14,3 mi, 2025 R$ 13,8 mi; **mês corrente incompleto** (3º decêndio zerado); bruto ou líquido **A VERIFICAR**.
- [x] **T1.7 POC Oportunidades.** Verificar se `parcerias` (programas) do Transferegov, o Novo PAC Seleções ou outra fonte automática listam programas e editais abertos para o município (fonte do status `oportunidade` e do prazo `adesao`). Sem fonte automática confirmada, `oportunidade` fica sem dados na fase 1, registrado em `docs/fontes.md` e `docs/decisoes.md`.
  *Feito (29/10/2026):* `scripts/poc_oportunidades.py`, amostras em `tests/fixtures/oportunidades/`, `docs/fontes.md` (§Oportunidades), spec §4 e D10. **Há fonte automática: o Siconv em lote** (`siconv_programa`: janelas, natureza jurídica, UF; `siconv_programa_proponentes`; `siconv_proposta_selecao_pac` para o Novo PAC). Resultado: 9 programas abertos e elegíveis (7 `DISPONIBILIZADO`), 3 dirigidos à prefeitura com janela aberta, 10 propostas do Novo PAC em 9 programas, 14 emendas indicadas; `parcerias/programa` não tem janela espontânea aberta. Ressalva: carga de 17/07/2026. Sem entrada no `status_map.yaml` (oportunidade é derivada de janelas, não de situação); o mapeamento das situações do Novo PAC Seleções fica pendente.
  *Aceite de cada POC:* script em `scripts/poc_<fonte>.py`, amostra real salva em `tests/fixtures/<fonte>/`, seção da fonte em `docs/fontes.md` preenchida (endpoint, filtro, campos usados, valores de situação, limites), entradas correspondentes em `config/status_map.yaml`.

## Marco 2 — Coleta e normalização

- [x] **T2.1 Coletores.** Um módulo por fonte em `coleta/`, com interface comum `coletar(data) -> RetratoBruto`. Grava `dados/brutos/<fonte>/<data>.json` + `.log.json`. Retry com backoff, respeito a limites.
  *Aceite:* testes com `respx` usando as fixtures do Marco 1; `make coleta` real funciona localmente.
  *Feito (29/10/2026):* `coleta/base.py` (cliente HTTP com tentativas, backoff e intervalo mínimo; paradas em 401/403/429; teto de requisições; gravação atômica sem sobrescrever; log `.log.json` que acumula as execuções do dia; cache do dia; falha de uma fonte não derruba as outras), um módulo por fonte (`cauc`, `tesouro`, `obrasgov`, `transferegov_api`, `portal_transparencia`, `transferegov_discricionarias` + `siconv.py`), CLI `python -m coleta [--fonte] [--data] [--forcar] [--cache] [--destino]`, alvo `make coleta`, `municipio.cnpjs_fundos` na config. 89 testes novos, com `respx` sobre as amostras do Marco 1 (218 no total).
  *Verificação real:* sem `make` nesta máquina Windows, rodei `python -m coleta`. **4 das 6 fontes rodaram contra os servidores reais** (`transferegov_api` 59 registros, `portal_transparencia` 176, `cauc` 40, `tesouro_constitucionais` 208), com os mesmos números das POCs, e nenhum retrato contém a chave, credenciais `guest`, e-mail ou dado bancário. **Ressalva:** `transferegov_discricionarias` e `obrasgov` falharam com HTTP 404 porque o diretório do Siconv em lote saiu do ar durante o dia (ver `docs/fontes.md` e `docs/decisoes.md`, Em aberto); com um espelho local dos arquivos baixados de manhã os dois funcionaram e deram os números das POCs (256 propostas, 28 convênios, 1.240 linhas de histórico, 68 programas dirigidos, 10 propostas do Novo PAC; 4 projetos Obrasgov e 3 linhas de ponte). A falha dessas duas, sem derrubar as outras, é o comportamento previsto na spec §9.
- [x] **T2.2 Normalização.** `nucleo/normaliza.py`: brutos → `Verba[]`, aplicando `status_map.yaml`. Junção da mesma verba vista em várias fontes (chave: número do instrumento/proposta).
  *Aceite:* testes por fonte; relatório de situações não mapeadas.
  *Feito (29/10/2026):* `nucleo/normaliza.py` (carrega o último retrato válido de cada fonte; `normalizar()` → `Normalizacao` com verbas, situações não mapeadas, avisos e a data de cada retrato; `relatorio_nao_mapeadas()`; CLI `python -m nucleo.normaliza` e alvo `make normaliza`) e `nucleo/dinheiro.py` (centavos de texto brasileiro e de reais decimais, sempre com arredondamento). Com os retratos reais de 29/10/2026: **46 verbas** (22 do Siconv no recorte, 12 de `parcerias`, 2 do fundo a fundo, 10 oportunidades), 0 situações não mapeadas, 0 avisos. Regras: recorte do Siconv (proposta de 2024+ ou instrumento ativo); `tipo` pela D12; junção Siconv-Portal por número da proposta **ou** do processo (26 de 28 casam); Portal atualiza `valor_liberado`; Obrasgov dá o percentual físico só quando a prefeitura é executora (D8); `valor_devolvido` vem de `VL_SALDO_REMAN_TESOURO`; `valor_total` nulo nas oportunidades. Mudanças de spec/schema: `valor_total` nulo, campo opcional `instrumento`, rótulo de `voluntaria` (§3, §8, D12). 80 testes novos (298 no total), parte deles fixada nos retratos reais.
  *Fora desta tarefa / pendente:* risco, perda e histórico saem vazios (T2.3, T2.4); o Tesouro (FPM, ITR) e o CAUC não são verbas (T2.5 e T2.3); Novo PAC Seleções só no bruto (D12); `area` fica nulo (a spec não define a taxonomia); emendas Pix (`especiais`) geram aviso se aparecerem registros; **sem retrato do Siconv não há fallback para o Portal** (D11 diz que ele não define status; decidir se vale um mapa degradado só para esse caso); o link de cada verba aponta para a fonte, não para a página da proposta (T4.4).
- [ ] **T2.3 Regras de risco.** Os quatro códigos de spec §5, parametrizados por `regras.yaml`.
  *Aceite:* um teste por código, incluindo bordas (59, 60, 61 dias).
- [ ] **T2.4 Detecção de perda e histórico.** Compara com `dados/publicados/verbas.json` anterior, gera `historico[]`, calcula `valor_perdido`.
  *Aceite:* testes de transição (execucao → perdida, aprovada → execucao, sem mudança).
- [ ] **T2.5 Publicação.** `dados/publicados/verbas.json` e `verbas.csv` (UTF-8 com BOM para abrir no Excel).
  *Aceite:* saída valida no schema; CSV abre com acentos corretos.

## Marco 3 — Curadoria com IA

- [ ] **T3.1 Montagem do dossiê.** Para uma verba perdida, reunir documentos (spec §7.2) com `id`, `titulo`, `url`, `data_coleta`, `texto`.
- [ ] **T3.2 Cliente da IA.** `curadoria/ia.py` usando `anthropic`, prompt de `prompts/curadoria.md`, saída validada em `schemas/rascunho_curadoria.schema.json`. Modelo e parâmetros em `config/regras.yaml`.
- [ ] **T3.3 Validação de citações.** Regras da spec §7.4.
  *Aceite:* testes com rascunho bom, trecho inexistente, frase sem citação, nome de pessoa.
- [ ] **T3.4 Fila e aprovação.** `dados/fila/<id>.yaml` → revisão → `dados/curadoria/<id>.yaml`. Comando `python -m curadoria.aprovar <id> --por "<nome>"`.
  *Aceite:* fluxo completo com uma perda de fixture; só `dados/curadoria/` chega ao publicado.

## Marco 4 — Site

- [ ] **T4.1 Projeto Astro + tokens.** Tokens e tipografia de `docs/design.md`, layout base com faixa de independência, cabeçalho e rodapé.
- [ ] **T4.2 Início.** Conforme `docs/design/telas/Main.dc.html` e `Celular.dc.html`.
- [ ] **T4.3 Lista.** Conforme `Lista.dc.html`; filtros com estado na URL.
- [ ] **T4.4 Página da verba.** Conforme `Verba.dc.html`; bloco de perda com selo e citações; meta tags para preview.
- [ ] **T4.5 Perdas e Como funciona.**
  *Aceite do marco:* build lê `dados/publicados/verbas.json`; Lighthouse acessibilidade ≥ 95 no celular; sem rolagem horizontal em 360 px.

## Marco 5 — Automação e lançamento

- [ ] **T5.1 Workflow diário** (`.github/workflows/coleta-diaria.yml`): coleta → normaliza → curadoria (gera fila) → commit dos dados → build → deploy. Abre issue automática quando há rascunhos novos na fila ou situações não mapeadas.
- [ ] **T5.2 Carga histórica desde 2024** e revisão de todas as perdas encontradas.
- [ ] **T5.3 Revisão de credibilidade** (spec §12) e lançamento.

## Fase 1.5 (depois do lançamento)

- Coleta do Diário Oficial do município (PDF) e inclusão no dossiê.
- Tela de revisão (`docs/design/telas/Revisao.dc.html`) como página protegida ou app local.
- Avaliar `curadoria.auto_publicar` (spec §7.5).

## Fase 2

- Verbas estaduais (SP) via extração com IA + revisão.
