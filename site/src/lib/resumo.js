// Cálculos da página inicial a partir de verbas.json. Funções puras: nada de leitura de arquivo aqui.
// Valores monetários chegam e saem em centavos (int); só `formatar*` os transforma em texto.

const EM_ANDAMENTO = ["aprovada", "execucao", "prestacao"];
const PRIORIDADE_RISCO = ["prazo_proximo", "obra_parada", "impedimento_emenda", "cauc_sem_comprovacao"];
const SIGLAS = new Set(["UBS", "UPA", "SUS", "CAUC", "SP", "PAC", "FUNDEB", "CRAS", "CREAS", "FNDE", "MAPA", "ONG", "IPTU", "ITR", "FPM"]);

const soma = (verbas, valor) => verbas.reduce((total, v) => total + (valor(v) ?? 0), 0);

/** Os quatro números do resumo (spec §10, Início). */
export function resumir(verbas) {
  const por = (status) => verbas.filter((v) => v.status_site === status);
  const andamento = verbas.filter((v) => EM_ANDAMENTO.includes(v.status_site));
  const risco = verbas.filter((v) => v.em_risco);
  const perdidas = por("perdida");
  return {
    andamento: { n: andamento.length, valor: soma(andamento, (v) => v.valor_total) },
    risco: { n: risco.length, valor: soma(risco, (v) => v.valor_total) },
    perdidas: {
      n: perdidas.length,
      valor: soma(perdidas, (v) => v.perda?.valor_perdido),
      documentadas: perdidas.filter(motivoDocumentado).length,
    },
    concluidas: { n: por("concluida").length, valor: soma(por("concluida"), (v) => v.valor_total) },
    oportunidades: { n: por("oportunidade").length },
  };
}

/** Motivo de perda revisado, com documento citado (qualquer coisa diferente de "em apuração"). */
export function motivoDocumentado(verba) {
  return Boolean(verba.perda && verba.perda.categoria !== "em_apuracao" && verba.perda.citacoes?.length);
}

/** Valor perdido por categoria, do maior para o menor; `largura` é % do maior (barra proporcional). */
export function perdasPorMotivo(verbas, taxonomia) {
  const grupos = new Map();
  for (const v of verbas.filter((x) => x.status_site === "perdida" && x.perda)) {
    const g = grupos.get(v.perda.categoria) ?? { categoria: v.perda.categoria, n: 0, valor: 0 };
    g.n += 1;
    g.valor += v.perda.valor_perdido ?? 0;
    grupos.set(v.perda.categoria, g);
  }
  const lista = [...grupos.values()].sort((a, b) => b.valor - a.valor);
  const maior = lista[0]?.valor || 1;
  return lista.map((g) => ({
    ...g,
    rotulo: g.categoria === "em_apuracao" ? "Motivo em apuração" : (taxonomia.categorias[g.categoria]?.rotulo ?? g.categoria),
    largura: Math.max(2, Math.round((g.valor / maior) * 100)),
  }));
}

/** Das perdas com motivo documentado, quantas a prefeitura poderia ter evitado (`sim`). */
export function evitaveis(verbas) {
  const documentadas = verbas.filter((v) => v.status_site === "perdida" && motivoDocumentado(v));
  return { total: documentadas.length, evitaveis: documentadas.filter((v) => v.perda.evitavel === "sim").length };
}

/** Verbas em risco, as mais urgentes primeiro (prazo, obra parada, emenda, CAUC) e, a seguir, as de maior valor. */
export function emRiscoAgora(verbas, limite = 6) {
  const posicao = (v) => Math.min(...(v.motivos_risco ?? []).map((m) => PRIORIDADE_RISCO.indexOf(m.codigo)).filter((i) => i >= 0), PRIORIDADE_RISCO.length);
  return verbas
    .filter((v) => v.em_risco)
    .sort((a, b) => posicao(a) - posicao(b) || (b.valor_total ?? 0) - (a.valor_total ?? 0))
    .slice(0, limite);
}

/** Mudanças de situação (a entrada inicial de cada verba, sem `de`, não é mudança), da mais recente para a mais antiga. */
export function ultimasMudancas(verbas, limite = 6) {
  return verbas
    .flatMap((v) => (v.historico ?? []).filter((h) => h.de).map((h) => ({ ...h, verba: v })))
    .sort((a, b) => b.data.localeCompare(a.data))
    .slice(0, limite);
}

/** Texto curto do alerta (a pílula laranja do cartão). */
export function rotuloRisco(motivo) {
  if (motivo.codigo === "cauc_sem_comprovacao") return "Pendência no CAUC";
  if (motivo.codigo === "impedimento_emenda") return "Impedimento técnico na emenda";
  return motivo.texto; // "Prazo em 51 dias", "Obra parada há 94 dias"
}

/** "R$ 3,2 mi", "R$ 2,18 mi", "R$ 520 mil", "R$ 950". */
export function formatarCompacto(centavos) {
  const reais = centavos / 100;
  const numero = (x, max) => x.toLocaleString("pt-BR", { maximumFractionDigits: max });
  if (reais >= 1_000_000) return `R$ ${numero(reais / 1_000_000, 2)} mi`;
  if (reais >= 1_000) return `R$ ${numero(reais / 1_000, 0)} mil`;
  return `R$ ${numero(reais, 0)}`;
}

/** Nomes do Siconv vêm em caixa alta: "REFORMA DA UBS" -> "Reforma da UBS". Texto já misto não é tocado. */
export function formatarTitulo(texto) {
  if (!texto || texto !== texto.toUpperCase()) return texto;
  const minusculo = texto
    .toLowerCase()
    .split(/(\s+)/)
    .map((p) => (SIGLAS.has(p.toUpperCase()) ? p.toUpperCase() : p))
    .join("")
    .replace(/neves paulista/g, "Neves Paulista");
  return minusculo.charAt(0).toUpperCase() + minusculo.slice(1);
}

const TIPO_CURTO = {
  voluntaria: "Convênio ou contrato de repasse",
  emenda_finalidade: "Emenda parlamentar",
  emenda_pix: "Emenda Pix",
  fundo_a_fundo: "Fundo a fundo",
  programa_adesao: "Programa por adesão",
  constitucional: "Transferência constitucional",
};

/** "Contrato de repasse" quando o instrumento é conhecido; senão o tipo em poucas palavras. */
export function rotuloInstrumento(verba) {
  if (verba.instrumento) return formatarTitulo(verba.instrumento).replace(/^Convenio$/, "Convênio");
  return TIPO_CURTO[verba.tipo] ?? verba.tipo;
}
