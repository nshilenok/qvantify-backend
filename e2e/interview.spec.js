import { test, expect } from "@playwright/test";

const PROJECT_ID = "sample_project_mocked";
const VOICE_PROJECT_ID = "sample_project_voice_mocked";
const EXTERNAL_ID = `e2e_user_${Date.now()}_${Math.floor(Math.random() * 1000)}`;

const START_BUTTON_LABEL = /start|begin|continue|next/i;
const SEND_BUTTON_LABEL = /send|submit|next/i;

const baseProject = {
  name: "Sample Interview",
  answer_placeholder: "Type your answer here…",
  cta_reply: "Send",
  cta_next: "Start",
  cta_abort: "Abort",
  skip_welcome: true,
  colour: "#684EAD",
};

const stubInterviewRoutes = async (page, { projectId, voiceEnabled }) => {
  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          ...baseProject,
          voice_enabled: voiceEnabled,
          id: projectId,
        },
      ]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: "uuid-mocked", projectId }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Are you fine we start now?",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      }),
    });
  });

  await page.route("**/api/reply", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Thanks! Next question.",
        status: "open",
        progress: { current: 2, total: 3, ratio: 0.66 },
      }),
    });
  });
};

test("interview journey (mocked)", async ({ page }) => {
  await stubInterviewRoutes(page, { projectId: PROJECT_ID, voiceEnabled: false });

  await page.goto(
    `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}`,
    {
      waitUntil: "domcontentloaded",
    }
  );

  await expect(page.getByText("Are you fine we start now?")).toBeVisible();
  const input = page.getByRole("textbox");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();

  const replyResponse = page.waitForResponse(
    (response) => response.url().includes("/api/reply") && response.status() === 200,
    { timeout: 30_000 }
  );
  await input.fill("E2E check: hello from Playwright.");
  await page.getByText(SEND_BUTTON_LABEL).click();
  await replyResponse;
  await expect(page.getByText("Thanks! Next question.")).toBeVisible();
});

test("voice UI: denied permission shows hint text (mocked)", async ({ page }) => {
  await stubInterviewRoutes(page, { projectId: VOICE_PROJECT_ID, voiceEnabled: true });

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

  await page.goto(
    `/interview?interview=${encodeURIComponent(VOICE_PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_voice`,
    {
      waitUntil: "domcontentloaded",
    }
  );

  const input = page.getByRole("textbox");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();

  const mic = page.locator('[aria-label="Record voice"]');
  await expect(mic).toBeVisible();
  await expect(mic).toBeEnabled();
  await mic.click();

  await expect(page.getByText(/microphone permission not granted/i)).toBeVisible();
});

test("resume restores the same question on refresh (mocked)", async ({ page }) => {
  let respondentCalls = 0;
  let interviewCalls = 0;
  let lastInterviewUuid = "";

  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          ...baseProject,
          id: PROJECT_ID,
        },
      ]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    respondentCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: `uuid-${respondentCalls}`, projectId: PROJECT_ID }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    interviewCalls += 1;
    lastInterviewUuid = route.request().headers()["uuid"] || "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Resume question check.",
        status: "open",
        progress: { current: 1, total: 2, ratio: 0.5 },
      }),
    });
  });

  await page.goto(
    `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_resume`,
    { waitUntil: "domcontentloaded" }
  );

  await expect(page.getByText("Resume question check.")).toBeVisible();
  expect(respondentCalls).toBe(1);
  expect(interviewCalls).toBe(1);
  expect(lastInterviewUuid).toBe("uuid-1");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("Resume question check.")).toBeVisible();
  expect(respondentCalls).toBe(1);
  expect(interviewCalls).toBe(2);
  expect(lastInterviewUuid).toBe("uuid-1");
});

test("restart after abort starts a new session (mocked)", async ({ page }) => {
  let respondentCalls = 0;

  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          ...baseProject,
          id: PROJECT_ID,
          cta_restart: "Restart",
          abort_title: "Aborted",
          abort_message: "You stopped the interview.",
        },
      ]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    respondentCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: `uuid-${respondentCalls}`, projectId: PROJECT_ID }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Abort flow question.",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      }),
    });
  });

  await page.goto(
    `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_abort`,
    { waitUntil: "domcontentloaded" }
  );

  await expect(page.getByText("Abort flow question.")).toBeVisible();
  await page.getByRole("button", { name: "Abort" }).click();

  const restartButton = page.getByRole("button", { name: "Restart" });
  await expect(restartButton).toBeVisible();

  const waitForRespondent = page.waitForResponse(
    (response) => response.url().includes("/api/respondent") && response.status() === 200,
    { timeout: 30_000 }
  );
  await restartButton.click();
  await waitForRespondent;

  expect(respondentCalls).toBe(2);
});
