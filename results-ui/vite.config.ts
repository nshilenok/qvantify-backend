import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  base: "/results/",
  plugins: [tailwindcss(), react()],
  server: {
    proxy: {
      "/api": "http://localhost:5059",
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../static/results",
    emptyOutDir: true,
    sourcemap: true
  },
});

