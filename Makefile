PYTHON ?= python

.PHONY: coleta normaliza curadoria site test

# Stubs: cada alvo ganha implementação na tarefa indicada em docs/plano.md.

coleta:  # T2.1
	@echo "coleta: ainda não implementado (T2.1)"

normaliza:  # T2.2 a T2.5
	@echo "normaliza: ainda não implementado (T2.2)"

curadoria:  # T3.2
	@echo "curadoria: ainda não implementado (T3.2)"

site:  # T4.1
	@echo "site: ainda não implementado (T4.1)"

test:
	$(PYTHON) -m pytest
