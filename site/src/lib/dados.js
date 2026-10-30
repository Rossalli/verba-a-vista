// Leitura do publicado (dados/publicados/verbas.json) e formatação em português do Brasil.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// O build roda dentro de site/ (npm run build); o código empacotado não sabe onde o arquivo-fonte estava.
const CAMINHO_PUBLICADO = process.env.DADOS_PUBLICADOS || resolve(process.cwd(), "../dados/publicados/verbas.json");
const FUSO = "America/Sao_Paulo";

export function carregarPublicado(caminho = CAMINHO_PUBLICADO) {
  return JSON.parse(readFileSync(caminho, "utf-8"));
}

const partes = (iso, opcoes) =>
  Object.fromEntries(
    new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, ...opcoes })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );

/** "2026-10-29T18:19:41-03:00" -> "29/10/2026" (no fuso de São Paulo). */
export function formatarData(iso) {
  const p = partes(iso, { day: "2-digit", month: "2-digit", year: "numeric" });
  return `${p.day}/${p.month}/${p.year}`;
}

/** "2026-10-29T18:19:41-03:00" -> "29/10/2026 às 18:19". */
export function formatarDataHora(iso) {
  const p = partes(iso, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return `${formatarData(iso)} às ${p.hour}:${p.minute}`;
}

/** Centavos inteiros -> "R$ 1.234.567" (a saída é a única que formata dinheiro). */
export function formatarReais(centavos) {
  const reais = Math.round(centavos / 100);
  return `R$ ${reais.toLocaleString("pt-BR")}`;
}

/** Caminho dentro do site respeitando o `base` do deploy: url("/verbas/") -> "/verba-a-vista/verbas/". */
export function url(caminho, base = import.meta.env?.BASE_URL ?? "/") {
  return base.replace(/\/$/, "") + "/" + caminho.replace(/^\//, "");
}
