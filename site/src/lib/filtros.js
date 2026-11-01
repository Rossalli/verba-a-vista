// Filtros da lista de verbas (T4.3). Funções puras, usadas pelo build (contagens iniciais) e pelo script da página.
// O estado vive na URL: ?status=perdida&risco=1&tipo=voluntaria&q=ambulancia

export const STATUS = ["oportunidade", "proposta", "aprovada", "execucao", "prestacao", "concluida", "perdida"];

/** Minúsculas e sem acento, para a busca achar "saude" em "Saúde". */
export function normalizar(texto) {
  return (texto ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/** Filtros a partir de URLSearchParams; valor desconhecido é ignorado em vez de esconder todas as verbas. */
export function lerFiltros(params, tiposValidos = []) {
  const status = params.get("status");
  const tipo = params.get("tipo");
  return {
    status: STATUS.includes(status) ? status : "todas",
    risco: params.get("risco") === "1",
    tipo: tiposValidos.includes(tipo) ? tipo : "",
    q: params.get("q") ?? "",
  };
}

/** URLSearchParams só com o que difere do padrão (URL curta e compartilhável). */
export function paraParametros(filtros) {
  const params = new URLSearchParams();
  if (filtros.status !== "todas") params.set("status", filtros.status);
  if (filtros.risco) params.set("risco", "1");
  if (filtros.tipo) params.set("tipo", filtros.tipo);
  if (filtros.q.trim()) params.set("q", filtros.q.trim());
  return params;
}

/** `linha`: { status, risco, tipo, busca } com `busca` já normalizada. `ignorarStatus` serve à contagem dos chips. */
export function corresponde(linha, filtros, { ignorarStatus = false } = {}) {
  if (!ignorarStatus && filtros.status !== "todas" && linha.status !== filtros.status) return false;
  if (filtros.risco && !linha.risco) return false;
  if (filtros.tipo && linha.tipo !== filtros.tipo) return false;
  const termos = normalizar(filtros.q).split(/\s+/).filter(Boolean);
  return termos.every((t) => linha.busca.includes(t));
}

/** Quantas linhas cada chip mostraria: respeita os outros filtros, mas não o de situação. */
export function contarPorStatus(linhas, filtros) {
  const contagem = { todas: 0, ...Object.fromEntries(STATUS.map((s) => [s, 0])) };
  for (const linha of linhas) {
    if (!corresponde(linha, filtros, { ignorarStatus: true })) continue;
    contagem.todas += 1;
    contagem[linha.status] += 1;
  }
  return contagem;
}

const ORDEM_STATUS = ["execucao", "aprovada", "prestacao", "proposta", "oportunidade", "perdida", "concluida"];

/** Em risco primeiro; depois as etapas em andamento, e dentro de cada uma o maior valor. */
export function ordenarLista(verbas) {
  return [...verbas].sort(
    (a, b) =>
      Number(b.em_risco) - Number(a.em_risco) ||
      ORDEM_STATUS.indexOf(a.status_site) - ORDEM_STATUS.indexOf(b.status_site) ||
      (b.valor_total ?? 0) - (a.valor_total ?? 0),
  );
}
