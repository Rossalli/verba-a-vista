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

- [ ] **T1.0 Teste de acesso a partir do ambiente de execução.** Script `scripts/teste_acesso.py` que faz uma requisição simples a cada base URL de `config/fontes.yaml` e reporta status. Rodar localmente (Brasil) e no GitHub Actions.
  *Aceite:* tabela em `docs/fontes.md` §Acesso com o resultado dos dois ambientes. Se o Actions for bloqueado, registrar em `docs/decisoes.md` a decisão sobre onde rodar a coleta.
- [ ] **T1.1 POC Transferegov API** (módulos `especiais`, `fundoafundo`, `parcerias`). Descobrir parâmetro de filtro por município/CNPJ, campos de situação e seus valores distintos.
- [ ] **T1.2 POC Transferegov Discricionárias e Legais (CSV).** Localizar o download em lote atual, baixar, filtrar por município, listar situações distintas de proposta e convênio.
- [ ] **T1.3 POC Obrasgov.** Projetos do município, execução física, histórico de situação (motivos e providências).
- [ ] **T1.4 POC Portal da Transparência.** Com chave: convênios e emendas do município. Confirmar endpoints no Swagger oficial.
- [ ] **T1.5 POC CAUC.** Obter a situação do município (dataset do Tesouro Transparente ou consulta pública) com data.
- [ ] **T1.6 POC Tesouro Transferências Constitucionais.** FPM e ITR do município por mês.
- [ ] **T1.7 POC Oportunidades.** Verificar se `parcerias` (programas) do Transferegov, o Novo PAC Seleções ou outra fonte automática listam programas e editais abertos para o município (fonte do status `oportunidade` e do prazo `adesao`). Sem fonte automática confirmada, `oportunidade` fica sem dados na fase 1, registrado em `docs/fontes.md` e `docs/decisoes.md`.
  *Aceite de cada POC:* script em `scripts/poc_<fonte>.py`, amostra real salva em `tests/fixtures/<fonte>/`, seção da fonte em `docs/fontes.md` preenchida (endpoint, filtro, campos usados, valores de situação, limites), entradas correspondentes em `config/status_map.yaml`.

## Marco 2 — Coleta e normalização

- [ ] **T2.1 Coletores.** Um módulo por fonte em `coleta/`, com interface comum `coletar(data) -> RetratoBruto`. Grava `dados/brutos/<fonte>/<data>.json` + `.log.json`. Retry com backoff, respeito a limites.
  *Aceite:* testes com `respx` usando as fixtures do Marco 1; `make coleta` real funciona localmente.
- [ ] **T2.2 Normalização.** `nucleo/normaliza.py`: brutos → `Verba[]`, aplicando `status_map.yaml`. Junção da mesma verba vista em várias fontes (chave: número do instrumento/proposta).
  *Aceite:* testes por fonte; relatório de situações não mapeadas.
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
