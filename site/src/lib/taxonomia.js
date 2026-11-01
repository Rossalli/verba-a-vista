// Vocabulário do site: lido de config/taxonomia.yaml, o mesmo arquivo que o pipeline e o CSV usam.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse } from "yaml";

const CAMINHO = process.env.TAXONOMIA || resolve(process.cwd(), "../config/taxonomia.yaml");

export function carregarTaxonomia(caminho = CAMINHO) {
  return parse(readFileSync(caminho, "utf-8"));
}

const CAMINHO_REGRAS = process.env.REGRAS || resolve(process.cwd(), "../config/regras.yaml");

/** Regras do pipeline (config/regras.yaml); o site só precisa de textos como o selo de IA. */
export function carregarRegras(caminho = CAMINHO_REGRAS) {
  return parse(readFileSync(caminho, "utf-8"));
}
