import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  base: "./",   // Critical for Chrome extensions — no server, all paths must be relative
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup:      resolve(__dirname, "popup/index.html"),
        background: resolve(__dirname, "background.js"),
      },
      output: {
        // Keep background.js name stable — manifest references it directly
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
    cssCodeSplit: false,
    minify: false, // Readable during dev — flip to true for production
  },
});