import { defineConfig } from "@playwright/test";

// The smoke test runs against a gateway that serves the built site (local mode):
//   uv run python -m runtime.main   (with web/out built)   then   pnpm test:e2e
// CI starts the gateway itself; locally the installed Chrome is used (no download).
export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.PITCHSIDE_URL ?? "http://localhost:8000",
    channel: process.env.CI ? undefined : "chrome",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  reporter: process.env.CI ? "github" : "list",
});
