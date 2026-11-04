# Revisão de credibilidade (antes do lançamento)

Critério da spec §12: **alguém que trabalhe com convênios confere uma amostra de pelo menos 10 verbas antes do lançamento.** Esta pasta tem o material para essa pessoa.

## O que é o Verba à Vista

Um site cidadão e independente que mostra as verbas **federais** destinadas a Neves Paulista (SP): o que está disponível, em que etapa cada uma está e, quando uma é perdida, por quê, sempre com o documento oficial citado. Os dados vêm do Transferegov, do Obrasgov, do Portal da Transparência e do CAUC. O site traduz a situação de cada fonte para sete etapas (Oportunidade, Proposta, Aprovada, Em execução, Prestação de contas, Concluída, Perdida) e **sempre mostra também a situação original da fonte**.

## O que você precisa fazer (cerca de 1 hora)

1. Abra `amostra.csv` no Excel ou no Google Planilhas (separador `;`, codificação UTF-8). São 12 verbas, escolhidas para cobrir perdas, alertas de risco e cada tipo de fonte.
2. Para cada linha, procure a verba no Transferegov pelo **nº do instrumento** (ou pelo **id na fonte**, que é o ID da proposta). Compare o que o site mostra com o que a fonte oficial mostra.
3. Responda as quatro colunas em branco (`sim`, `não`, `não sei` ou `não se aplica`) e escreva na coluna **Observações** o que está errado ou faltando e como você sabe.
4. Responda as perguntas gerais abaixo, em poucas linhas.

Não é preciso conferir tudo de cada linha: o que mais importa é **a situação**, **o valor** e **os alertas**. O motivo das perdas, por ora, está todo como "em apuração" (veja "O que já sabemos").

## Perguntas gerais

1. A tradução das situações da fonte para as sete etapas está razoável? Alguma situação do Transferegov está na etapa errada?
2. Os alertas de risco fazem sentido para quem trabalha com convênios? Algum deles assustaria sem motivo, ou algum risco real não aparece?
3. As 8 perdas listadas são realmente perdas? Falta alguma que você conhece?
4. Falta alguma verba federal de Neves Paulista que você sabe que existe desde 2024?
5. Algum texto do site é impreciso, injusto com a prefeitura ou difícil de entender? (Veja "Como funciona" no site.)
6. Você publicaria este site com o seu nome ou o da sua instituição por perto? Se não, o que precisaria mudar?

## O que já sabemos (não precisa apontar)

- **Os dados do Siconv em lote são de 17/07/2026.** O Governo tirou a publicação desse lote do ar em 29/10/2026; mudanças posteriores a julho podem não aparecer. As outras fontes são de 29/10/2026.
- **Todas as perdas estão como "em apuração".** As fontes automáticas dizem que a proposta foi rejeitada e quando, mas não por quê. O motivo só será publicado com documento citado e revisado.
- **Os nomes vêm das fontes** e, às vezes, sem acento ou em caixa alta.
- **Não há filtro por área** (a fonte não informa).

## Pontos em que queremos a sua opinião específica

- **Etapa "Proposta".** Ela agrupa as situações do Transferegov que vão de "Cadastrados" (a proposta ainda não foi enviada) a "Enviado para Análise" e "Complementado em Análise". Faz sentido ficarem na mesma etapa, ou "Cadastrados" deveria aparecer separada? (Ex.: `transferegov_discricionarias-2122457`, R$ 21,38 mi, situação "Cadastrados".)
- **Alerta de CAUC.** Aparece para convênios e emendas com proposta já enviada ou aprovada e ainda vigentes, quando o CAUC tem algum item sem comprovação (hoje, o item 4.2, regularidade previdenciária). O alerta diz "sem comprovação", não "irregular", porque o arquivo do Tesouro diz só que não conseguiu comprovar. Faz sentido?
- **Valor perdido.** É a parte do repasse da União que não foi liberada, mais o que foi devolvido; a contrapartida do município não entra. É assim que você calcularia?

## Como devolver

Devolva a planilha preenchida e as respostas gerais. Quem recebe registra o resultado em `docs/revisao-credibilidade/resultado.md` (uma linha por verba com "não": o que era, o que foi corrigido). O lançamento só acontece depois de corrigir os erros de situação, valor ou alerta que a revisão apontar.

Para gerar a planilha de novo com dados atualizados: `python -m nucleo.amostra`. A escolha é determinística (mesmos dados, mesma amostra).
