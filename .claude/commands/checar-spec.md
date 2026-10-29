---
description: Confere se o código está aderente à spec e às regras inegociáveis
---

Revise o repositório contra `docs/spec.md` e as "Regras inegociáveis" do `CLAUDE.md`. Não altere código; só relate.

Verifique em especial:
- Algum caminho publica motivo de perda sem citação ou sem passar por `dados/curadoria/`?
- `curadoria.auto_publicar` continua `false` e é respeitado?
- Situações não mapeadas viram `status_site: null` + relatório (e nunca um status chutado)?
- O status original da fonte é preservado e exibido?
- Toda verba publicada tem `fontes[]` com URL e data de coleta?
- Algum segredo em arquivo versionado?
- A faixa de independência aparece em todas as páginas do site?
- Testes cobrem os quatro códigos de risco e a validação de citações?

Responda com uma lista: item, situação (ok / problema), arquivo e linha, correção sugerida.
