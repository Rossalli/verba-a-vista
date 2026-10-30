PYTHON ?= python

.PHONY: coleta normaliza curadoria site test

# Stubs: cada alvo ganha implementação na tarefa indicada em docs/plano.md.

coleta:  # T2.1; ex.: make coleta ARGS="--fonte cauc --data 2026-10-29"
	$(PYTHON) -m coleta $(ARGS)

normaliza:  # T2.2 a T2.5: normaliza, aplica risco, perda e histórico e grava dados/publicados; ARGS="--sem-publicar" só mostra o resumo
	$(PYTHON) -m nucleo.pipeline $(ARGS)

curadoria:  # T3.4; sem ARGS só mostra o plano. make curadoria ARGS="--executar" chama a IA (cobrado)
	$(PYTHON) -m curadoria $(ARGS)

site:  # T4.1
	@echo "site: ainda não implementado (T4.1)"

test:
	$(PYTHON) -m pytest
