import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { copyFileSync, mkdirSync, cpSync } from "fs";

// Plugin to copy extension static files into dist after build
function copyExtensionFiles() {
  return {
    name: "copy-extension-files",
    closeBundle() {
      // manifest.json → dist/
      copyFileSync("manifest.json", "dist/manifest.json");

      // content_scripts/ → dist/content_scripts/
      mkdirSync("dist/content_scripts", { recursive: true });
      cpSync("content_scripts", "dist/content_scripts", { recursive: true });

      // icons/ → dist/icons/ (if exists)
      try {
        mkdirSync("dist/icons", { recursive: true });
        cpSync("icons", "dist/icons", { recursive: true });
      } catch (_) {}

      console.log("[NutriLens] Extension files copied to dist/");
    }
  };
}

export default defineConfig({
  plugins: [react(), copyExtensionFiles()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup:      resolve(__dirname, "popup/index.html"),
        background: resolve(__dirname, "background.js"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
    cssCodeSplit: false,
    minify: false,
  },
});