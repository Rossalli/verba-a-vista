# Verba à Vista — Neves Paulista

Site cívico independente que acompanha as verbas federais destinadas a Neves Paulista (SP): o que o município pode receber, o que já recebeu, o que está em risco e, quando uma verba é perdida, por quê — sempre com o documento oficial citado.

**Estado:** especificação e layout prontos; implementação começando (fase 1, só verbas federais).

## Começando no VS Code com o Claude Code

1. Descompacte esta pasta, abra no VS Code e rode `git init`.
2. Copie `.env.example` para `.env` e preencha as chaves quando chegar a hora (Portal da Transparência na T1.4, Anthropic na T3.2).
3. Abra o Claude Code e cole o conteúdo de `PRIMEIRO-PROMPT.md`.
4. Daí em diante, use `/proxima-tarefa` e `/poc-fonte <fonte>`. Rode `/checar-spec` antes de cada marco terminar.

## Documentos

- `CLAUDE.md` — contexto e regras para o Claude Code
- `docs/spec.md` — especificação
- `docs/plano.md` — tarefas com critérios de aceite
- `docs/fontes.md` — fontes de dados e pendências de verificação
- `docs/decisoes.md` — decisões tomadas e em aberto
- `docs/design.md` + `docs/design/telas/` — layout de referência

## Licença

A definir (sugestão: código MIT, dados CC BY 4.0).
