import { test, expect } from "@playwright/test";

const PROJECT_ID = process.env.QVANTIFY_PROJECT_ID || "sample_game_funnel_2026_01_14";
const VOICE_PROJECT_ID =
  process.env.QVANTIFY_VOICE_PROJECT_ID || "d0aaae3f-b133-4099-a6fb-9509ed750a24";
const EXTERNAL_ID =
  process.env.QVANTIFY_EXTERNAL_ID || `e2e_user_${Date.now()}_${Math.floor(Math.random() * 1000)}`;

const START_BUTTON_LABEL = /start|begin|continue|next/i;
const SEND_BUTTON_LABEL = /send|submit|next/i;

test("live interview journey: real backend + database", async ({ page }) => {
  const projectResponse = page.waitForResponse(
    (response) => response.url().includes("/api/project/") && response.status() === 200
  );
  const respondentResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/respondent/") &&
      response.request().method() === "POST" &&
      response.status() === 200
  );
  await page.goto(`/?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}`, {
    waitUntil: "domcontentloaded",
  });

  const projectPayload = await (await projectResponse).json();
  expect(Array.isArray(projectPayload)).toBeTruthy();
  expect(projectPayload.length).toBeGreaterThan(0);

  const respondentPayload = await (await respondentResponse).json();
  expect(respondentPayload.uuid).toBeTruthy();

  const interviewResponse = await page.waitForResponse(
    (response) => response.url().includes("/api/interview/"),
    { timeout: 60_000 }
  );
  if (interviewResponse.status() !== 200) {
    const body = await interviewResponse.text();
    throw new Error(`Interview init failed: ${interviewResponse.status()} ${body}`);
  }

  const startButton = page.getByText(START_BUTTON_LABEL);
  if (await startButton.isVisible().catch(() => false)) {
    await startButton.click();
  }

  await expect(page.getByText(/question/i)).toBeVisible();
  await expect(page.locator("#qv-interview-progress")).toBeVisible();
  const input = page.getByRole("textbox");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();

  const replyResponse = page.waitForResponse(
    (response) => response.url().includes("/api/reply/") && response.status() === 200,
    { timeout: 90_000 }
  );
  await input.fill("E2E check: hello from Playwright.");
  await page.getByText(SEND_BUTTON_LABEL).click();
  await replyResponse;

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(input).toBeVisible();
});

test("voice UI: denied permission shows help banner (script-injected)", async ({ page }) => {
  await page.addInitScript(() => {
    const makeDenied = async () => {
      const err = new Error("denied");
      // @ts-ignore
      err.name = "NotAllowedError";
      throw err;
    };
    // @ts-ignore
    if (!navigator.mediaDevices) navigator.mediaDevices = {};
    // @ts-ignore
    navigator.mediaDevices.getUserMedia = makeDenied;
  });

  const projectResponse = page.waitForResponse(
    (response) => response.url().includes("/api/project/") && response.status() === 200
  );
  const respondentResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/respondent/") &&
      response.request().method() === "POST" &&
      response.status() === 200
  );

  await page.goto(
    `/?interview=${encodeURIComponent(VOICE_PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_voice`,
    {
      waitUntil: "domcontentloaded",
    }
  );

  const projectPayload = await (await projectResponse).json();
  expect(Array.isArray(projectPayload)).toBeTruthy();
  expect(projectPayload.length).toBeGreaterThan(0);

  const respondentPayload = await (await respondentResponse).json();
  expect(respondentPayload.uuid).toBeTruthy();

  const startButton = page.getByText(START_BUTTON_LABEL);
  if (await startButton.isVisible().catch(() => false)) {
    await startButton.click();
  }

  const input = page.getByRole("textbox");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();

  const mic = page.locator('[aria-label="Record voice"]');
  await expect(mic).toBeVisible();
  await expect(mic).toBeEnabled();
  await mic.click();

  await expect(page.locator("#qvantify-voice-banner")).toBeVisible();
  await expect(page.getByText(/microphone permission not granted/i)).toBeVisible();
  await expect(page.getByText(/how to enable microphone/i)).toBeVisible();
});

