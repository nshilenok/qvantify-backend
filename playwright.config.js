import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.QVANTIFY_E2E_BASE_URL || "http://127.0.0.1:4173";
const isLocal = baseURL.includes("127.0.0.1") || baseURL.includes("localhost");
const skipWebServer = process.env.QVANTIFY_E2E_SKIP_WEB_SERVER === "1";
const parsedBaseURL = new URL(baseURL);
const localPort = parsedBaseURL.port || "4173";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: isLocal && !skipWebServer
    ? {
        command: `npm run dev -- --hostname 127.0.0.1 --port ${localPort}`,
        url: baseURL,
        reuseExistingServer: false,
        timeout: 120_000,
        cwd: "frontend",
        env: {
          QVANTIFY_RAILWAY_URL:
            process.env.QVANTIFY_RAILWAY_URL || "https://qvantify.up.railway.app",
        },
      }
    : undefined,
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 5"] },
    },
  ],
});
