// @ts-check
import { existsSync, readFileSync } from "node:fs";
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// The site moves to its own domain by adding one file: public/CNAME, holding the domain name
// (for example "example.com"). GitHub Pages reads that file to serve the domain, and this
// config reads it to build the links. Without it the site is the GitHub Pages project site.
const cname = new URL("./public/CNAME", import.meta.url);
const domain = existsSync(cname) ? readFileSync(cname, "utf8").trim() : "";

// Every internal link goes through `link()` in src/lib/radar.ts, which prefixes `base`.
export default defineConfig({
  site: domain ? `https://${domain}` : "https://alejandrorodriguezalvarez884-dot.github.io",
  base: domain ? "/" : "/decision-signal-lab",
  trailingSlash: "always",
  vite: {
    plugins: [tailwindcss()],
  },
});
