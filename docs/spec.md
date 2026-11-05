# Especificação — Verba à Vista (fase 1)

Versão 0.1 · 29/10/2026 · autora: Bárbara Rossalli

## 1. Objetivo

Mostrar a qualquer morador de Neves Paulista, em linguagem simples:
1. quais verbas federais o município pode pleitear, já pleiteou, recebeu ou perdeu;
2. em que etapa cada verba está;
3. quais verbas estão **em risco** de ser perdidas, enquanto ainda dá para agir;
4. **por que** cada verba perdida foi perdida, com o documento oficial citado.

Público: moradores (acesso principal pelo celular, via link no WhatsApp), imprensa local, vereadores e a própria prefeitura.

Postura: iniciativa cidadã **independente**. Tom informativo, nunca acusatório.

## 2. Escopo

**Fase 1 (esta spec):** verbas federais desde 01/01/2024. Nas fontes em lote do Siconv (Transferegov Discricionárias e Legais), entra a proposta com data de proposta a partir de 01/01/2024 **ou** o instrumento ainda ativo (`INSTRUMENTO_ATIVO = SIM`), mesmo que mais antigo, para não esconder o que segue em execução ou com prestação de contas pendente.
- Transferências voluntárias (convênios, contratos de repasse)
- Emendas parlamentares federais com finalidade definida (individuais, bancada, comissão)
- Transferências especiais ("emendas Pix")
- Fundo a fundo (saúde, assistência social, educação)
- Programas federais por adesão ou seleção (ex.: PAR/FNDE, Novo PAC Seleções)
- Contexto: transferências constitucionais (FPM, ITR) só como número de referência, sem ciclo de status

**Fase 2 (fora desta spec):** verbas estaduais (SP), via extração com IA + revisão. Emendas impositivas municipais.

**Fora de escopo:** opinião, ranking de políticos, qualquer dado pessoal além do que já é público nas fontes.

## 3. Tipos de verba

| `tipo` | Nome no site | Fonte principal |
| --- | --- | --- |
| `voluntaria` | Convênio, contrato de repasse ou termo de compromisso | Transferegov (Discricionárias e Legais, CSV) |
| `emenda_finalidade` | Emenda com finalidade definida | Transferegov (emenda indicada ao município, `nr_emenda`) + Portal da Transparência (pagamentos ligados pelo código do autor; a emenda no Portal vem agregada, sem o valor do município) |
| `emenda_pix` | Emenda Pix (transferência especial) | Transferegov API, módulo `especiais` |
| `fundo_a_fundo` | Repasse fundo a fundo | Transferegov API, módulo `fundoafundo` (FNS só na fase 1.5; repasses de saúde podem estar incompletos na fase 1 e o site avisa em "Como funciona") |
| `programa_adesao` | Programa por adesão ou seleção | Transferegov `parcerias`, FNDE, Obrasgov |
| `constitucional` | Transferência constitucional | Tesouro (Transferências Constitucionais) |

**Regra do `tipo` nas verbas do Siconv:** `voluntaria` para convênio, contrato de repasse, termo de compromisso e termo de fomento; `emenda_finalidade` quando há linha em `siconv_emenda` para a proposta. A modalidade original (`MODALIDADE`) fica visível no site. Nas propostas de `parcerias`, `emenda_finalidade` quando o programa só aceita "Beneficiário de Emenda Parlamentar" (todos os programas das 12 propostas do município), senão `fundo_a_fundo`. Planos do módulo `fundoafundo`: `fundo_a_fundo`. Programas abertos: `programa_adesao` com status `oportunidade`.

## 4. Status do site

Sete valores. O status original da fonte é sempre guardado em `status_fonte` e exibido ao lado.

| `status_site` | Rótulo | Significado |
| --- | --- | --- |
| `oportunidade` | Oportunidade | Programa, edital ou emenda que o município pode pleitear |
| `proposta` | Proposta | Pedido cadastrado ou enviado, ainda em análise (D18) |
| `aprovada` | Aprovada | Proposta e plano de trabalho aprovados ou instrumento assinado, recurso ainda não liberado (a assinatura pode estar pendente; pode haver cláusula suspensiva) |
| `execucao` | Em execução | Recurso liberado, obra ou compra em andamento |
| `prestacao` | Prestação de contas | Execução encerrada, contas em análise |
| `concluida` | Concluída | Contas aprovadas |
| `perdida` | Perdida | Município não recebeu ou teve de devolver o recurso |

`em_risco` **não é status**. É um alerta (booleano + lista de motivos) que pode existir em `proposta`, `aprovada`, `execucao` e `prestacao`.

O mapeamento de cada situação de cada fonte para `status_site` vive em `config/status_map.yaml`. **Papel do Obrasgov:** é fonte auxiliar e **não define `status_site`** (o cadastro dos gestores fica desatualizado: obras "Cadastrada" sem medição, com convênio "Em execução" no Siconv). Um projeto do Obrasgov só entra quando a prefeitura (CNPJ em `executores`) é a executora e ele se liga a um instrumento do Transferegov/Siconv (ponte `siconv_dados_obrasgov_geral`); ele alimenta o alerta `obra_parada`, `execucao_fisica_pct` e o dossiê da curadoria. Projetos de outros executores (ex.: manutenção rodoviária do DNIT) ficam de fora.

**Papel do Portal da Transparência:** é fonte de complemento e **não define `status_site`**. O status vem do Transferegov/Siconv; o Portal atualiza `valor_liberado` e os pagamentos (a carga do Siconv fica atrás), lista pagamentos recebidos pelos CNPJs da prefeitura e dos fundos municipais (estornos, valores negativos, são candidatos a `valor_devolvido`), liga pagamento a emenda pelo código do autor e serve de conferência (a situação coincide com a do Siconv nos instrumentos que casam por `NR_PROPOSTA`, ignorados zeros à esquerda). O filtro por `codigoIBGE` de `recursos-recebidos` não funciona: consultar por CNPJ, em janelas de 12 meses.

**Oportunidades (`oportunidade`):** vêm do Siconv em lote (`siconv_programa` e `siconv_programa_proponentes`). Entra o programa com `SIT_PROGRAMA = DISPONIBILIZADO` e (a) janela de recebimento de propostas voluntárias aberta na data de referência, natureza jurídica "Administração Pública Municipal" e UF do município ou sem UF, ou (b) o município como proponente específico (`siconv_programa_proponentes`) com alguma janela aberta. A data final da janela vira o prazo `adesao`. Ficam de fora os programas que só valem para beneficiário de emenda (exigem emenda indicada), os `CADASTRADO` e os `INATIVO`. O arquivo do Siconv é uma carga antiga, então "aberto" é um mínimo e cada oportunidade mostra a data da carga. O mesmo programa aparece em várias linhas (uma por UF e natureza jurídica): deduplicar por `ID_PROGRAMA`.

Situação desconhecida → `status_site: null`, a verba vai para um relatório de "situações não mapeadas" e **não** recebe status inventado. Ela é publicada mesmo assim, com o `status_fonte` e o selo neutro "situação em análise", fora dos totais por etapa, até a situação ser mapeada.

## 5. Em risco

Regras em `config/regras.yaml` (valores ajustáveis). Uma verba fica `em_risco: true` quando qualquer uma vale:

| Código | Regra |
| --- | --- |
| `prazo_proximo` | Algum prazo do instrumento (cláusula suspensiva, vigência, prestação de contas, adesão) vence de hoje até `dias_alerta_prazo` dias à frente, inclusive os dois extremos (padrão 60: 60 dias dispara, 61 não). Prazo já vencido não conta. Um motivo por verba, com o prazo mais próximo e a data em `data_limite` |
| `cauc_sem_comprovacao` | O CAUC não conseguiu comprovar algum item (`!` no relatório do Tesouro) para o município na data do arquivo, qualquer item, e a verba é do `tipo` `voluntaria` ou `emenda_finalidade` com `status_site` `proposta` ou `aprovada` (antes da liberação) **e veio do Transferegov Discricionárias e Legais** (`cauc_fontes`; o CAUC é requisito de transferência voluntária, então verbas de fundo a fundo, como as de `parcerias`, ficam sem esse alerta). Um motivo por item. Os tipos, as etapas e as fontes ficam em `config/regras.yaml`. O texto cita o item e a exigência da legenda do próprio arquivo, sem a palavra "irregular" (ex.: "CAUC: item 4.2 sem comprovação (Regularidade Previdenciária)"); a data do arquivo é a data do dado. Itens `Desabilitado` não contam. **Não alerta** (D17): (a) verba cuja `fim_vigencia` já passou (regularizar o CAUC não salva instrumento ou proposta com vigência encerrada; vale a data de hoje, e a vigência que termina hoje ainda vale); (b) verba cuja situação na fonte está em `risco.cauc_ignora_situacoes_fonte` (padrão: "Proposta/Plano de Trabalho Cadastrados", a proposta que ainda não foi enviada) |
| `obra_parada` | Obra no Obrasgov sem nova atualização de execução física (`dt_atualizacao_execucao`) há mais de `dias_obra_parada` dias (padrão 90), ou situação `Paralisada`. Sem nenhum registro de execução física a regra **não dispara** (ausência de dado não é obra parada). A falta de atualização só vale para obra em situação aberta (não `Concluída`, `Cancelada` nem `Inacabada`). Para `Paralisada`, os dias contam desde o último registro de paralisação (ou, sem ele, desde a última atualização; sem nenhuma data, o texto não cita dias). A situação "Suspensa" não existe na API |
| `impedimento_emenda` | Emenda com impedimento técnico registrado e ainda não superado (situação atual do plano de ação `IMPEDIDO`). **Desligada** em `risco.desligadas` até um registro real confirmar o campo (D13) |

`em_risco` só existe nas etapas de `risco.status` (`proposta`, `aprovada`, `execucao`, `prestacao`). As oportunidades **não** entram, mesmo com o prazo de adesão perto: o cartão da oportunidade mostra `prazos.adesao` à parte (D13).

Dependem de campo ainda não verificado: `impedimento_emenda` (e a perda por "impedimento não superado no exercício", §6.1) e o prazo de `adesao`. Só são implementados na T2.3 se a POC correspondente (T1.1, T1.4, T1.7) confirmar o campo na fonte; caso contrário a regra fica desligada e o fato é registrado em `docs/decisoes.md`. Os testes usam fixtures de exemplo.

Cada motivo de risco gera um texto curto para o site (ex.: "Prazo em 38 dias").

## 6. Perda

### 6.1 Detecção automática

Uma verba vira `perdida` quando a fonte indica, por exemplo: cancelada, extinta, rescindida, anulada, recurso devolvido integralmente, proposta rejeitada/indeferida, ou impedimento não superado no exercício. Obra `Cancelada` no Obrasgov não é gatilho: vira sinal e documento para a curadoria (ver §4, papel do Obrasgov). A lista exata de situações fica em `config/status_map.yaml` (destino `perdida`).

Ao detectar uma perda nova, o pipeline:
1. registra a mudança no histórico;
2. calcula `valor_perdido` (valor não liberado + valor devolvido), sobre o **repasse da União**: o valor total menos a contrapartida do município (o valor global do Siconv inclui a parte do município); nunca negativo;
3. cria um pedido de curadoria (§7): toda perda sem arquivo em `dados/curadoria/`.

A `perda.data` é a data do último evento da situação na fonte quando ela a informa (Siconv: `siconv_historico_situacao`); sem isso, a data da detecção. Enquanto não houver curadoria revisada, a perda sai com `categoria: em_apuracao`, o texto padrão de `config/regras.yaml` e `evitavel: indeterminado` (§7). Uma perda já publicada mantém, nas execuções seguintes, a `data` e o `valor_perdido` da detecção; o **motivo nunca é copiado do publicado anterior**: ele vem só de `dados/curadoria/` (sem arquivo, volta a `em_apuracao`). Se a verba deixar de estar perdida, a perda some e o histórico registra a volta.

Invariantes, impostas no modelo, no JSON Schema e no carregamento da curadoria: motivo de perda diferente de `em_apuracao` só existe com pelo menos uma citação, `revisado_por` e `revisado_em`; e `em_apuracao` só pode ter o texto padrão, `evitavel: indeterminado` e nenhuma citação (nada de texto livre sem documento).

### 6.2 Taxonomia de motivos

Definida em `config/taxonomia.yaml`. Cada perda publicada tem exatamente uma `categoria`:

`prazo_proposta`, `reprovacao_tecnica`, `impedimento_emenda`, `cauc`, `clausula_suspensiva`, `execucao_nao_iniciada`, `contrapartida`, `glosa_devolucao`, `decisao_externa`, `em_apuracao`.

`evitavel`: `sim` | `em_parte` | `nao` | `indeterminado`.

## 7. Curadoria com IA

### 7.1 Fluxo

1. Para cada verba `perdida` sem arquivo em `dados/curadoria/`, o pipeline reúne os documentos daquela verba (§7.2).
2. Chama o modelo com o prompt de `prompts/curadoria.md`, a taxonomia e os documentos.
3. O modelo devolve JSON conforme `schemas/rascunho_curadoria.schema.json`.
4. **Validação de citações** (§7.4). Rascunho reprovado não entra na fila de revisão: o rascunho e a lista de erros são gravados em `dados/fila/<id>.erro.yaml` (não publicado, versionado no Git) e a perda aparece no site como `em_apuracao` (texto padrão de `config/regras.yaml`) até haver curadoria revisada.
5. Rascunho aprovado na validação vai para `dados/fila/<id>.yaml`.
6. Uma pessoa revisa (fase 1: arquivo YAML editado à mão ou via PR; a tela de revisão do layout é fase 1.5). Ao aprovar, o arquivo vai para `dados/curadoria/<id>.yaml` com `revisado_por` e `revisado_em`.
7. Só `dados/curadoria/` é publicado.

Detalhes da fase 1 (T3.4):
- `python -m curadoria` só mostra o plano; a chamada à IA (cobrada) exige `--executar`. Perda que já tem rascunho ou erro em `dados/fila/` não é enviada de novo sem `--refazer`.
- `dados/fila/<id>.yaml` traz o `rascunho` (a pessoa edita aqui) e os `documentos` citáveis; a revisão é `python -m curadoria.aprovar <id> --por "<nome>"`, que confere o rascunho de novo antes de aprovar e apaga o arquivo da fila (o histórico é o Git).
- **Falha de infraestrutura da IA** (chave ausente ou sem workspace, API fora do ar, rede) não é rascunho reprovado: não grava nada em `dados/fila/` (um `.erro.yaml` bloquearia a nova tentativa), interrompe o laço (as demais chamadas falhariam igual), sai com sucesso para não travar a publicação do dia e deixa um aviso no log; a perda é tentada de novo na próxima execução. Só falha do conteúdo (recusa, corte por tamanho, JSON ou citação inválidos) gera `<id>.erro.yaml`.
- Rascunho `em_apuracao` não se aprova: a perda já aparece como "motivo em apuração".
- `dados/curadoria/<id>.yaml` (modelo `CuradoriaRevisada`) vira a `perda` publicada; `data` e `valor_perdido` continuam os do pipeline. Arquivo inválido, ou motivo diferente de `em_apuracao` sem citação, para o pipeline.
- `gerado_por_ia` é sempre `true` na curadoria aprovada (o texto parte do rascunho da IA, mesmo editado).

### 7.2 Documentos de entrada

Na fase 1, só documentos obtidos automaticamente:
- histórico de situação do Obrasgov (com motivos e providências);
- situação e dados da proposta/instrumento no Transferegov;
- extrato do CAUC mais próximo da data da perda;
- (fase 1.5) publicações do Diário Oficial do município que citem o número do instrumento.

Cada documento entra com `id`, `titulo`, `url`, `data_coleta` e `texto`.

### 7.3 Regras para o modelo

- Afirmar só o que está nos documentos. Proibido inferir causa provável, contexto político ou intenção.
- Toda frase do texto tem pelo menos uma citação `[n]`.
- Sem documento que sustente, `categoria: em_apuracao` e texto padrão.
- Sem nomes de pessoas.
- Na dúvida entre categorias, a menos acusatória, com `confianca: baixa`.
- Saída sempre JSON válido no schema; nada fora do JSON.

### 7.4 Validação automática

O rascunho é reprovado se:
- não valida no JSON Schema;
- algum `trecho` citado não aparece literalmente (após normalizar espaços e caixa) no `texto` do documento citado;
- alguma frase do `texto` não tem marcador `[n]`;
- o texto contém nome de pessoa (heurística: lista de nomes próprios presentes nos documentos que não sejam órgãos, cidades ou programas) — na dúvida, reprova e manda para revisão com aviso.

### 7.5 Publicação sem revisão (desligada na fase 1)

Flag `curadoria.auto_publicar` em `config/regras.yaml`, padrão `false`. Quando ligada, publica sem revisão só se: `confianca == alta`, validação 100% e categoria em `auto_publicar_categorias` (ex.: `cauc`, `execucao_nao_iniciada` com motivo explícito no Obrasgov).

### 7.6 Transparência

Todo motivo publicado mostra: "Explicação gerada com IA a partir dos documentos citados", e "revisada por <nome ou papel> em <data>" quando revisada.

## 8. Modelo de dados

JSON Schema em `schemas/verba.schema.json`. Campos principais:

- `id` (estável: `<fonte>-<id_na_fonte>`), `fonte`, `id_fonte`, `numero_instrumento`. Quando a mesma verba aparece em várias fontes (junção pelo número do instrumento), `id`, `fonte` e `id_fonte` vêm da fonte de maior precedência (ordem definida em `config/fontes.yaml`, a criar na T2.2; Transferegov antes do Portal da Transparência) e as demais entram em `fontes[]`. O `id` não muda se uma fonte deixar de listar a verba.
- `nome`, `objeto`, `tipo`, `area`, `instrumento` (modalidade como a fonte a chama, ex.: `TERMO DE COMPROMISSO`), `orgao_concedente`, `parlamentar` (se emenda; nome público do autor, permitido)
- `valor_total` (obrigatório, mas **nulo** quando a fonte não informa, como nas oportunidades; o site mostra "valor não informado" e as deixa fora das somas), `valor_contrapartida`, `valor_liberado`, `valor_executado`, `valor_devolvido` (centavos; `valor_devolvido` é opcional, só preenchido se uma fonte confirmada o trouxer; sem ele, `valor_perdido` considera só o não liberado e o site avisa "valor devolvido não informado")
- `status_site`, `status_fonte`, `em_risco`, `motivos_risco[]`
- `prazos`: `proposta`, `assinatura`, `clausula_suspensiva`, `fim_vigencia`, `prestacao_contas`, `adesao`
- `execucao_fisica_pct` (obras)
- `perda`: `categoria`, `texto`, `citacoes[]`, `evitavel`, `data`, `valor_perdido`, `gerado_por_ia`, `revisado_por`, `revisado_em`
- `historico[]`: `data`, `de`, `para`, `fonte`, `nota`
- `fontes[]`: `nome`, `url`, `data_coleta`

## 9. Pipeline

```
coleta  ──►  dados/brutos/<fonte>/<data>.json
normaliza  ──►  Verba[] em memória  ──►  regras (risco, perda, histórico)
curadoria  ──►  dados/fila/ (rascunhos)  ──►  revisão humana  ──►  dados/curadoria/
publica  ──►  dados/publicados/verbas.json + verbas.csv  ──►  site (Astro build)
```

A publicação grava `dados/publicados/verbas.json` (objeto com `versao`, `data`, `atualizado_em`, `fontes`, `referencias` e a lista em `verbas`) e `verbas.csv` (UTF-8 com BOM, separador `;`, valores em reais com vírgula decimal, rótulos do site, texto protegido contra fórmulas do Excel). Os dois são validados contra `schemas/` antes de gravar; se algo falhar, nada é gravado e o publicado anterior fica. O formato completo está em `docs/dados-publicados.md`.

O histórico é calculado comparando o resultado normalizado do dia com o publicado anterior (`dados/publicados/verbas.json` no Git, um objeto com a lista em `verbas`). Cada mudança na situação do site **ou** na situação da fonte vira uma entrada (`de` e `para` são os status do site; a `nota` diz a mudança na fonte). Sem publicado anterior (primeira execução), cada verba nasce com uma entrada de `de` nulo e a nota "Primeira coleta", que cita desde quando a fonte registra a situação, se informar; uma verba nova depois disso diz "Verba apareceu nas fontes". Uma verba publicada que some das fontes de um dia para o outro **não é publicada** e vai para os avisos, para revisão. Se o publicado anterior existir e não puder ser lido, o pipeline para: o histórico nunca é recomeçado em silêncio.

Execução diária às 09:00 (horário de Brasília), depois da publicação diária do CAUC (~08:11 em dias úteis). Falha de uma fonte não derruba as outras: a fonte com falha mantém os dados do último retrato válido e o site mostra "dados de <fonte> de <data>".

Detalhes do workflow (`.github/workflows/coleta-diaria.yml`, T5.1):
- **Disparos:** agenda diária, execução manual e `push` em `dados/curadoria/`, `config/` ou `site/` (quando uma pessoa aprova uma curadoria ou muda uma regra, o site é republicado sem nova coleta). O commit do robô, feito com o token do próprio Actions, não dispara o workflow de novo.
- **Coleta que falha não derruba o dia:** a falha de fontes não impede normalizar e publicar com o último retrato válido; ela aparece em `fontes[].situacao` e vira aviso. Erro no pipeline (por exemplo, curadoria inválida) para tudo, e nada é publicado nem implantado.
- **IA só com chave de ativação:** `make curadoria ARGS="--executar"` (chamada cobrada) só roda com a variável do repositório `CURADORIA_IA=true`. Sem ela, o dia mostra só o plano.
- **Avisos por issue** (`python -m nucleo.avisos`): rascunhos novos na fila, situações sem mapeamento e fonte sem retrato do dia. Cada aviso tem título fixo; com issue já aberta não se abre outra (rascunhos novos entram como comentário), então a fila pendente não gera uma issue por dia.
- **Implantação no GitHub Pages**, com o `base` do site tirado da própria configuração do Pages (vale também para domínio próprio, quando houver).

## 10. Site

Layout de referência em `docs/design.md` e `docs/design/telas/`.

| Página | Rota | Conteúdo |
| --- | --- | --- |
| Início | `/` | Frase-tese, resumo (em andamento, em risco, perdidas desde 2024, concluídas), "Em risco agora", perdas por motivo, últimas mudanças, como funciona |
| Lista | `/verbas/` | Filtros por situação, "só em risco", tipo, **ano**, área, busca; tabela; link para CSV |
| Verba | `/verbas/<id>/` | Cabeçalho com status do site + status da fonte, valores, bloco de perda (se houver) com selo de IA e citações, histórico, registros originais, "encontrou um erro?"; **"O que é esta verba"** (uma frase com instrumento, objeto, valor e concedente, mais o que o tipo e a etapa significam, D21); em "Registros originais", links que abrem e, quando o Transferegov não tem link direto, o número a buscar e onde clicar |
| Perdas | `/perdas/` | Todas as perdas agrupadas por motivo **ou por ano da perda** (alternável, D20), com totais |
| Como funciona | `/como-funciona/` | Fontes, frequência, método de curadoria com IA, limitações, contato; definição de cada tipo de verba e de cada etapa (D21) |

Links das fontes (D21): `fontes[].url` é um endereço que uma pessoa abre no navegador, não o de coleta (o do Siconv em lote está fora do ar e o das APIs não é página). É a consulta pública do módulo (Acesso Livre, Parcerias, Fundo a Fundo) ou, no Portal da Transparência, a página do próprio convênio quando o Portal informa o código. O Transferegov não tem link direto por proposta ou instrumento; a página da verba diz o número a buscar e onde clicar.

Filtro por **ano** (D19): é o ano da proposta (`prazos.proposta`) ou, nos programas por adesão, do prazo de adesão (`prazos.adesao`); verba sem nenhuma dessas datas entra em "Sem data". Não é o ano da perda: este aparece na própria linha da verba perdida (`perda.data`).

Requisitos:
- Faixa "Iniciativa cidadã independente. Não é o site oficial da Prefeitura de Neves Paulista." no topo de toda página.
- Data e hora da última coleta visível no início e em cada verba.
- Funciona a partir de 360 px de largura, sem rolagem horizontal da página (tabelas rolam dentro da própria caixa).
- Filtros da lista funcionam sem JavaScript pesado (ilha pequena ou JS puro). Estado do filtro na URL (`?status=perdida&risco=1`).
- Acessibilidade: contraste AA, alvos de toque ≥ 44 px, navegação por teclado, `lang="pt-BR"`.
- Sem rastreadores de terceiros. Se houver métrica de acesso, só agregada e sem cookies.
- Página de cada verba compartilhável (título e descrição próprios para o preview do WhatsApp).

## 11. Requisitos não funcionais

- Custo de hospedagem zero; custo de IA proporcional ao número de perdas novas (baixo).
- Reprodutível: `make coleta normaliza site` a partir de um clone gera o mesmo site.
- Respeitar limites das APIs (Portal da Transparência: 400 req/min; acima disso a chave é suspensa por 8 h). Backoff exponencial e cache dos retratos do dia.
- Logs da coleta em `dados/brutos/<fonte>/<data>.log.json` com contagem de registros e erros.

## 12. Critérios de aceite da fase 1

- [ ] Todas as verbas federais do município desde 2024 presentes nas fontes automáticas aparecem no site. Quem tem situação mapeada mostra o status do site; as demais mostram o selo "situação em análise" e constam do relatório de situações não mapeadas (nenhuma sem relatório).
- [ ] Toda verba `perdida` tem motivo revisado com citação **ou** aparece como "motivo em apuração".
- [ ] Alertas de risco aparecem para os quatro códigos do §5, testados com dados de exemplo.
- [ ] A coleta roda sozinha todo dia e o site é republicado.
- [ ] Revisão de credibilidade: alguém que trabalhe com convênios conferiu uma amostra de pelo menos 10 verbas antes do lançamento.
