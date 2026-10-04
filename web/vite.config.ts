/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app is served under a path prefix behind the proxy (dontpanic.ddns.net/memoir/).
// It is baked into the build, so it is a build argument of the image, not a runtime setting.
const base = process.env.VITE_BASE_PATH ?? "/memoir/";

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    // `npm run dev` on the host: the API from `docker compose up` answers on :8000.
    proxy: {
      [`${base}api`]: {
        target: "http://localhost:8000",
        rewrite: (path) => path.slice(base.length - 1),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
  },
});
