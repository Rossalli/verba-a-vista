PYTHON ?= python

.PHONY: coleta normaliza curadoria site test

# Stubs: cada alvo ganha implementação na tarefa indicada em docs/plano.md.

coleta:  # T2.1; ex.: make coleta ARGS="--fonte cauc --data 2026-10-29"
	$(PYTHON) -m coleta $(ARGS)

normaliza:  # T2.2 e T2.3: normaliza, aplica o risco e imprime o resumo; T2.4 e T2.5 completam
	$(PYTHON) -m nucleo.pipeline $(ARGS)

curadoria:  # T3.2
	@echo "curadoria: ainda não implementado (T3.2)"

site:  # T4.1
	@echo "site: ainda não implementado (T4.1)"

test:
	$(PYTHON) -m pytest
