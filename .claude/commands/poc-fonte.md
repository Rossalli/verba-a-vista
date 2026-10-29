---
description: Prova de conceito de uma fonte de dados (Marco 1 do plano)
argument-hint: <fonte> (ex.: obrasgov, transferegov_api, portal_transparencia)
---

Faça a prova de conceito da fonte **$ARGUMENTS** seguindo `docs/plano.md` (Marco 1) e `docs/fontes.md`.

1. Leia a seção da fonte em `docs/fontes.md` e a entrada em `config/fontes.yaml`.
2. Consulte a documentação oficial da fonte (docs/Swagger) antes de escrever código. Não invente endpoints, parâmetros ou campos.
3. Escreva `scripts/poc_<fonte>.py` que:
   - faz uma chamada mínima filtrando pelo município (código IBGE 3532504 ou CNPJ da prefeitura);
   - salva uma amostra real em `tests/fixtures/<fonte>/` (no máximo ~50 registros, sem dados pessoais além do que a fonte já publica);
   - imprime: total de registros do município, nomes dos campos e os valores distintos dos campos de situação.
4. Rode o script. Se falhar por acesso (403, timeout, bloqueio geográfico), registre exatamente o erro em `docs/fontes.md` §Acesso e pare.
5. Atualize `docs/fontes.md` (troque A VERIFICAR por VERIFICADO em <data> e registre endpoint, filtro, campos usados, valores de situação e limites) e `config/status_map.yaml` (valores exatos encontrados, `verificado: <data>`).
6. Liste situações que você não soube mapear e pergunte antes de decidir.
7. Marque a tarefa em `docs/plano.md`.
