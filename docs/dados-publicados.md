# Dados publicados

O pipeline (`make normaliza`) grava dois arquivos em `dados/publicados/`. São os únicos que o site e o público leem. O código está em `nucleo/publica.py` e o contrato em `schemas/publicado.schema.json` (cada verba segue `schemas/verba.schema.json`). Nada é gravado se a validação falhar.

## `verbas.json`

Objeto com:

| Campo | O que é |
| --- | --- |
| `versao` | Versão do formato (hoje `1`). |
| `data` | Data de referência do processamento (America/Sao_Paulo). |
| `atualizado_em` | A coleta mais recente entre os retratos usados (data e hora, com fuso). É o "Atualizado em" do site. |
| `fontes` | Uma entrada por fonte: `nome`, `url`, `retrato` (data do retrato bruto usado), `coletado_em`, `data_do_dado` e `situacao`. |
| `referencias.transferencias_constitucionais` | FPM e ITR por ano (centavos) e `ultimo_mes` com o aviso de que o 3º decêndio ainda estava zerado. Só número de referência, sem ciclo de status. |
| `verbas` | A lista de verbas, ordenada por `id`. |

`situacao` de cada fonte: `ok` (retrato da data de referência), `defasada` (último retrato válido, mais antigo; é o que a spec §9 manda mostrar como "dados de <fonte> de <data>") ou `sem_retrato`. `data_do_dado` é a data a que o dado se refere, quando a fonte informa: a carga do Siconv (hoje 17/07/2026), a pesquisa do CAUC, a atualização das APIs; fica `null` quando não há (Portal da Transparência, Tesouro).

Não há hora de geração: reexecutar sem mudança nas fontes gera o mesmo arquivo, e o Git só mostra o que mudou (por exemplo, a contagem de dias de um alerta de prazo).

Valores monetários ficam em **centavos** (inteiros), datas em ISO 8601.

## `verbas.csv`

Para abrir no Excel ou em qualquer planilha:

- UTF-8 **com BOM** (é o BOM que faz o Excel acertar os acentos), separador `;`, fim de linha `CRLF`.
- Valores em **reais com vírgula decimal e sem separador de milhar** (`3411250,00`), nas colunas terminadas em `_reais`. Em planilha configurada para ponto decimal, converta a vírgula.
- Datas em ISO (`2026-12-20`). Sim ou não escritos como `sim` e `não`.
- Texto vindo das fontes que começaria com `=`, `+`, `-` ou `@` recebe um apóstrofo na frente, para o Excel não o executar como fórmula.

| Coluna | Conteúdo |
| --- | --- |
| `id` | Identificador estável da verba. |
| `tipo` | Nome do tipo (spec §3). |
| `instrumento` | Modalidade como a fonte a chama (ex.: `TERMO DE COMPROMISSO`). |
| `nome`, `objeto` | Resumo e texto do objeto. |
| `orgao_concedente`, `parlamentar` | Órgão que repassa; autor da emenda, quando houver. |
| `numero_instrumento` | Número do convênio, da parceria ou do programa. |
| `situacao` | Status do site (Oportunidade, Proposta enviada, Aprovada, Em execução, Prestação de contas, Concluída, Perdida, ou "Situação em análise" quando a situação da fonte ainda não está mapeada). |
| `situacao_na_fonte` | A situação original, sempre preservada. |
| `em_risco`, `alertas` | `sim` ou `não`; os textos dos alertas, separados por ` \| `. |
| `valor_total_reais`, `contrapartida_reais`, `liberado_reais`, `executado_reais`, `devolvido_reais` | Valores. `valor_total_reais` fica vazio quando a fonte não informa (ex.: oportunidades). |
| `prazo_proposta`, `prazo_assinatura`, `prazo_clausula_suspensiva`, `prazo_fim_vigencia`, `prazo_prestacao_contas`, `prazo_adesao` | Prazos conhecidos. |
| `execucao_fisica_pct` | Percentual físico da obra, quando o Obrasgov informa. Vazio não é 0%. |
| `perda_categoria`, `perda_texto`, `perda_evitavel`, `perda_data`, `perda_valor_reais` | Só nas verbas perdidas. Enquanto não houver curadoria revisada, a categoria é "Motivo em apuração". |
| `perda_gerada_por_ia`, `perda_revisada_por`, `perda_revisada_em` | Transparência da curadoria (spec §7.6). |
| `fontes` | As fontes que sustentam a verba, separadas por `;`. |
| `ultima_coleta` | Data e hora da coleta mais recente entre essas fontes. |

O histórico (`historico[]`), as citações e os registros originais ficam só no JSON.
