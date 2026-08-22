import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { fs: { allow: [decodeURIComponent(new URL("..", import.meta.url).pathname)] } },
  build: { sourcemap: false },
});
