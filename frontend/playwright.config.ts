import { defineConfig } from "@playwright/test";

// Expects the full stack to be running (see scripts/e2e.sh): backend on :8000, frontend on :3000.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure", screenshot: "only-on-failure" },
});
