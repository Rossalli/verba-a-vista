// Montagem da página de uma verba (T4.4). Funções puras: recebem a verba de verbas.json e devolvem dados prontos.
import { formatarData, formatarReais } from "./dados.js";
import { formatarTitulo } from "./resumo.js";

export const ROTULO_PRAZO = {
  proposta: "Proposta enviada em",
  adesao: "Adesão até",
  assinatura: "Assinatura em",
  fim_vigencia: "Fim da vigência",
  prestacao_contas: "Prestação de contas até",
};

export const ROTULO_EVITAVEL = { sim: "Sim", em_parte: "Em parte", nao: "Não", indeterminado: "Indeterminado" };

const dia = (iso) => formatarData(`${iso}T12:00:00-03:00`);

/** Texto da perda em pedaços: { texto } ou { cita: n }, para virar `<sup><a href="#cN">N</a></sup>` sem usar HTML cru. */
export function partesComCitacoes(texto) {
  const partes = [];
  let resto = texto;
  for (let m = /\[(\d+)\]/.exec(resto); m; m = /\[(\d+)\]/.exec(resto)) {
    if (m.index > 0) partes.push({ texto: resto.slice(0, m.index) });
    partes.push({ cita: Number(m[1]) });
    resto = resto.slice(m.index + m[0].length);
  }
  if (resto) partes.push({ texto: resto });
  return partes;
}

/** Valores em destaque (o quadro de números do topo): [{ rotulo, valor, mono }] só com o que existe. */
export function valoresDaVerba(verba) {
  const itens = [{ rotulo: "Valor da verba", valor: verba.valor_total != null ? formatarReais(verba.valor_total) : "A definir", mono: verba.valor_total != null }];
  if (verba.valor_liberado !== undefined) itens.push({ rotulo: "Valor liberado", valor: formatarReais(verba.valor_liberado), mono: true });
  if (verba.valor_devolvido !== undefined) itens.push({ rotulo: "Valor devolvido", valor: formatarReais(verba.valor_devolvido), mono: true });
  if (verba.valor_contrapartida !== undefined) {
    itens.push(verba.valor_contrapartida > 0 ? { rotulo: "Contrapartida", valor: formatarReais(verba.valor_contrapartida), mono: true } : { rotulo: "Contrapartida", valor: "Não exige", mono: false });
  }
  for (const [chave, rotulo] of Object.entries(ROTULO_PRAZO)) {
    if (verba.prazos?.[chave]) itens.push({ rotulo, valor: dia(verba.prazos[chave]), mono: true });
  }
  if (verba.parlamentar) itens.push({ rotulo: "Autor da emenda", valor: verba.parlamentar, mono: false });
  if (verba.perda) itens.push({ rotulo: "Perdida em", valor: dia(verba.perda.data), mono: true });
  return itens;
}

/** Histórico do mais recente para o mais antigo (na mesma data, mantém a ordem de gravação invertida). */
export function historicoOrdenado(verba) {
  return [...(verba.historico ?? [])].map((h, i) => ({ ...h, i })).sort((a, b) => b.data.localeCompare(a.data) || b.i - a.i);
}

/** Descrição para o preview do WhatsApp e dos buscadores (até ~200 caracteres, sem inventar nada). */
export function descricaoMeta(verba, rotuloStatus, rotuloCategoria) {
  const partes = [`${formatarTitulo(verba.nome)}: ${rotuloStatus}`];
  if (verba.valor_total != null) partes[0] += `, ${formatarReais(verba.valor_total)}`;
  if (verba.perda) {
    partes.push(verba.perda.categoria === "em_apuracao" ? "Motivo da perda em apuração" : `Motivo da perda: ${rotuloCategoria}`);
  } else if (verba.em_risco && verba.motivos_risco?.length) {
    partes.push(`Em risco: ${verba.motivos_risco[0].texto}`);
  }
  partes.push("Com os documentos oficiais citados");
  const texto = partes.join(". ") + ".";
  return texto.length > 200 ? texto.slice(0, 197).trimEnd() + "…" : texto;
}

/** Selo de autoria da explicação: com IA (texto da config) ou só revisão humana; vazio se não houve revisão. */
export function seloDaPerda(perda, textoSeloIa) {
  if (!perda.revisado_por) return null;
  const revisao = `revisada por ${perda.revisado_por} em ${dia(perda.revisado_em)}`;
  return perda.gerado_por_ia ? `${textoSeloIa} · ${revisao}` : `Explicação ${revisao}`;
}

/** O histórico guarda a chave do status ("perdida") ou a situação da fonte; a chave vira o rótulo do site. */
export function rotuloSituacao(valor, taxonomia) {
  return taxonomia.status[valor] ?? valor;
}
