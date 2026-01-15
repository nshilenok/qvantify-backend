import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.QVANTIFY_E2E_BASE_URL || "http://127.0.0.1:4173";
const isLocal = baseURL.includes("127.0.0.1") || baseURL.includes("localhost");
const parsedBaseURL = new URL(baseURL);
const localPort = parsedBaseURL.port || "5055";
const useStaticServer = isLocal && localPort === "4173";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: isLocal
    ? useStaticServer
      ? {
          command: "python3 -m http.server 4173 --directory static",
          url: "http://127.0.0.1:4173",
          reuseExistingServer: true,
          timeout: 60_000,
        }
      : {
          command: `PORT=${localPort} python3 server.py`,
          url: baseURL,
          reuseExistingServer: true,
          timeout: 60_000,
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

