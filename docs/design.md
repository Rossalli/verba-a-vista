# Design

Canvas original (privado, da autora): https://claude.ai/artifact/SYwwP1cgYxoyBXHKqgkRn2

As telas de referência estão em `docs/design/telas/*.dc.html`. Elas usam um formato de componente do canvas (`<x-dc>`, `{{holes}}`, `<sc-for>`), **não** rodam sozinhas no navegador. Use-as como referência de estrutura, textos, espaçamentos e estilos inline para escrever os componentes Astro. Dados nelas são ilustrativos.

| Arquivo | Página |
| --- | --- |
| `Main.dc.html` | Início (desktop) |
| `Celular.dc.html` | Início no celular (390 px) |
| `Lista.dc.html` | Lista de verbas com filtros |
| `Verba.dc.html` | Página de uma verba perdida |
| `Revisao.dc.html` | Fila de revisão da curadoria (fase 1.5, uso interno) |

## Direção

Jornal cívico: claro, sóbrio, legível no celular. Uma cor de destaque (azul de caneta); laranja só para risco; vermelho só para perda; verde só para concluída. Nada de gradientes, emoji ou visual de painel corporativo.

## Tokens

```css
:root {
  /* superfícies */
  --fundo: #F5F7FA;
  --superficie: #FFFFFF;
  --linha: #D9E0E7;
  --linha-suave: #E6EBF0;
  --campo-borda: #C5CFD9;

  /* texto */
  --tinta: #111C27;
  --tinta-2: #2B3A48;
  --tinta-suave: #4A5A6A;

  /* destaque */
  --acento: #1E4FBF;
  --acento-hover: #163C91;
  --acento-fundo: #E8EEFB;

  /* semântica (texto / fundo) */
  --risco: #B54708;     --risco-fundo: #FEF0E3;   --risco-borda: #F1C9A5;
  --perda: #B42318;     --perda-fundo: #FDECEA;   --perda-borda: #E8B4AE;
  --ok: #067647;        --ok-fundo: #E3F4EA;

  /* pílulas de status */
  --st-oportunidade: #3E4C5A; --st-oportunidade-fundo: #EEF1F4;
  --st-proposta: #5B3FB0;     --st-proposta-fundo: #EFEAFB;
  --st-aprovada: #0B5F63;     --st-aprovada-fundo: #E2F3F3;
  --st-execucao: #1E4FBF;     --st-execucao-fundo: #E8EEFB;
  --st-prestacao: #6B4E16;    --st-prestacao-fundo: #F6EFDF;
  --st-concluida: #067647;    --st-concluida-fundo: #E3F4EA;
  --st-perdida: #B42318;      --st-perdida-fundo: #FDECEA;

  /* tipografia */
  --fonte-titulo: "Archivo", system-ui, sans-serif;          /* 800, font-stretch 80–90% */
  --fonte-texto: "Atkinson Hyperlegible", system-ui, sans-serif;
  --fonte-dados: "IBM Plex Mono", ui-monospace, monospace;    /* valores, datas, códigos */

  --raio: 12px;
  --raio-pilula: 999px;
  --largura-max: 1160px;
}
```

Google Fonts: `Archivo:wdth,wght@75..125,500..800`, `Atkinson+Hyperlegible:wght@400;700`, `IBM+Plex+Mono:wght@400;500`. Considere hospedar as fontes localmente para não depender do Google.

## Escala tipográfica

| Uso | Fonte | Tamanho (desktop / celular) |
| --- | --- | --- |
| H1 da página | Archivo 800, stretch 80% | 52 / 34 px |
| H2 de seção | Archivo 800, stretch 85% | 30 / 24 px |
| Título de cartão | Archivo 700, stretch 90% | 20 / 19 px |
| Número grande (resumo) | Archivo 800, stretch 85%, tabular | 34 / 24 px |
| Texto | Atkinson 400 | 16 px, linha 1,55 |
| Rótulo em caixa alta | Atkinson 700, espaçamento 0,06em | 12–13 px |
| Valores e datas | IBM Plex Mono | 13–18 px |

## Padrões

- **Faixa de independência:** fundo `--tinta`, texto claro, topo de toda página.
- **Resumo:** grade de 4 células separadas por 1 px de `--linha`; "Em risco" e "Perdidas" têm sublinhado interno de 4 px na cor semântica.
- **Cartão em risco:** borda `--risco-borda`, pílula laranja com o motivo curto ("Prazo em 38 dias"), título, uma frase, rodapé com tipo · status e valor em mono.
- **Pílula de status:** fundo e texto dos tokens `--st-*`; "Em risco" é uma pílula extra, laranja, ao lado.
- **Bloco de perda:** borda superior de 6 px `--perda`, título vermelho "Por que esta verba foi perdida", selo de IA, texto em 20 px com citações sobrescritas `[n]`, lista de documentos com trecho em mono e link.
- **Barras de perda por motivo:** trilho `#EEF1F4`, barra `--perda`, largura proporcional ao maior valor.
- **Linha do tempo:** data em mono numa coluna fixa (64–104 px), evento ao lado, separadores de 1 px.
