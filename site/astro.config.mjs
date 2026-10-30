import { defineConfig } from "astro/config";

// Domínio e caminho ainda em aberto (docs/decisoes.md): definidos por variável de ambiente no deploy.
export default defineConfig({
  site: process.env.SITE_URL || "http://localhost:4321",
  base: process.env.SITE_BASE || "/",
  trailingSlash: "always",
  build: { format: "directory" },
});
