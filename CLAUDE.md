# Verba à Vista — Neves Paulista

Site cívico independente que monitora as verbas **federais** destinadas ao município de Neves Paulista (SP, código IBGE **3532504**): o que está disponível, em que etapa cada verba está e, quando uma verba é perdida, **por quê**, sempre com o documento oficial citado.

Leia antes de qualquer tarefa:
- `docs/spec.md`: especificação (fonte da verdade do comportamento)
- `docs/plano.md`: tarefas em ordem, com critérios de aceite
- `docs/fontes.md`: fontes de dados, acesso e o que ainda falta verificar
- `docs/decisoes.md`: decisões já tomadas (não reabrir sem a autora pedir)

## Fluxo de trabalho (Specification-Driven Development)

1. Toda mudança de comportamento começa na spec. Se a tarefa exigir algo que a spec não cobre, **pare e proponha a alteração em `docs/spec.md`** antes de codar.
2. Implemente uma tarefa de `docs/plano.md` por vez. Ao terminar, marque `[x]` e anote em uma linha o que foi feito.
3. Cada tarefa termina com testes passando (`make test`) e o critério de aceite da tarefa verificado.
4. Fatos sobre APIs externas (endpoints, campos, valores de situação) **nunca são inventados**. Se não estiverem confirmados em `docs/fontes.md`, a tarefa é uma prova de conceito que os descobre e registra lá.

## Stack

- **Coleta, normalização, regras e curadoria:** Python 3.12, `httpx`, `pydantic` v2, `pandas` (só para os CSV em lote), `pyyaml`, `anthropic`. Testes com `pytest` e `respx`.
- **Site:** Astro (estático), sem framework de UI. CSS próprio com os tokens de `docs/design.md`.
- **Agendamento:** GitHub Actions (`.github/workflows/coleta-diaria.yml`). Se as APIs bloquearem servidores fora do Brasil, a coleta roda num servidor no Brasil e só faz push dos dados.
- **Hospedagem:** GitHub Pages ou Cloudflare Pages.
- Sem banco de dados. Os dados vivem em arquivos versionados no Git.

## Estrutura

```
coleta/        um módulo por fonte (transferegov_api, transferegov_discricionarias, obrasgov, portal_transparencia, cauc, tesouro) + base.py (HTTP, gravação, execução) e siconv.py
nucleo/        modelo Verba (pydantic), normalização, regras de risco e perda, histórico
curadoria/     cliente da IA, validação de citações, fila de revisão
config/        status_map.yaml, regras.yaml, taxonomia.yaml, fontes.yaml
schemas/       JSON Schemas (verba, rascunho de curadoria)
prompts/       prompt da curadoria
dados/
  brutos/<fonte>/<AAAA-MM-DD>.json   retrato do que a fonte devolveu (nunca editar)
  curadoria/<id-verba>.yaml          motivos revisados (editados por pessoas)
  fila/<id-verba>.yaml               rascunhos da IA aguardando revisão
  publicados/verbas.json, verbas.csv saída consumida pelo site
site/          projeto Astro
docs/          spec, plano, fontes, decisões, design (+ telas de referência)
```

## Convenções

- Termos do domínio em português e sem acento no código (`verba`, `perda`, `em_risco`, `status_site`). Comentários e mensagens em português.
- Valores monetários em centavos (`int`) internamente; formatação `R$ 1.234.567` só na saída.
- Datas em ISO 8601 (`2026-10-29`). Fuso `America/Sao_Paulo`.
- Todo registro publicado carrega `fontes[]` com URL e data da coleta.
- O status original da fonte é sempre preservado ao lado do status do site.
- Nunca apagar arquivos em `dados/brutos/`. O histórico é o Git.

## Regras inegociáveis

- **Motivo de perda só é publicado com citação de documento.** Sem documento: `"motivo em apuração"`.
- **A IA nunca publica sozinha** na fase 1. Todo rascunho passa pela fila de revisão (`curadoria/`), salvo as exceções de `docs/spec.md` §7.5, que só serão ligadas depois.
- **Sem nomes de pessoas** nos textos de motivo. Fale da prefeitura, do órgão ou do instrumento.
- **Sem identidade visual da prefeitura** (brasão, cores oficiais). O site é independente e diz isso no topo de toda página.
- Segredos (`ANTHROPIC_API_KEY`, `PORTAL_TRANSPARENCIA_KEY`) só por variável de ambiente ou secrets do GitHub. Nunca em arquivo versionado.

## Comandos

- `make coleta`: roda todos os coletores e grava em `dados/brutos/`
- `make normaliza`: gera `dados/publicados/` a partir dos brutos + curadoria
- `make curadoria`: gera rascunhos da IA para perdas sem motivo revisado
- `make site`: build do Astro
- `make test`: testes

Comandos personalizados do Claude Code em `.claude/commands/`: `/poc-fonte`, `/proxima-tarefa`, `/checar-spec`.
