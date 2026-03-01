import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Build config for Chrome Extension popup
// Run: vite build --config vite.config.js
// Output goes to extension/popup/dist/

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "popup/dist",
    rollupOptions: {
      input: {
        popup: resolve(__dirname, "popup/index.html"),
      },
    },
    // Extensions can't use dynamic imports — inline everything
    cssCodeSplit: false,
    minify: true,
  },
  root: ".",
});
