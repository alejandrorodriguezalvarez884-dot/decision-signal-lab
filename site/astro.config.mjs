// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// Published as a GitHub Pages project site, so every internal link goes through `link()` in
// src/lib/radar.ts, which prefixes `base`.
export default defineConfig({
  site: "https://alejandrorodriguezalvarez884-dot.github.io",
  base: "/decision-signal-lab",
  trailingSlash: "always",
  vite: {
    plugins: [tailwindcss()],
  },
});
