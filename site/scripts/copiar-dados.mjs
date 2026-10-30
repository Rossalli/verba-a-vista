// Copia o CSV publicado para o site servir em /dados/verbas.csv (a fonte continua sendo dados/publicados/).
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const origem = resolve(aqui, "../../dados/publicados/verbas.csv");
const destino = resolve(aqui, "../public/dados/verbas.csv");
mkdirSync(dirname(destino), { recursive: true });
copyFileSync(origem, destino);
console.log(`CSV copiado para ${destino}`);
