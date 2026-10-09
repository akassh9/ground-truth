import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [preact()],
  // in development the Check API runs locally: .venv/bin/python -m gt.serve
  server: { proxy: { "/api": "http://127.0.0.1:8787" } },
});
