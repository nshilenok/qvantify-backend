import { test, expect } from "@playwright/test";

const PROJECT_ID = "recovery_project_mocked";
const EXTERNAL_ID = `e2e_recovery_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
const STALE_UUID = "uuid-stale-expired";
const FRESH_UUID = "uuid-fresh-recovery";

const SEND_BUTTON_LABEL = /send|submit|next/i;

const baseProject = {
  name: "Recovery Interview",
  answer_placeholder: "Type your answer here…",
  cta_reply: "Send",
  cta_next: "Start",
  cta_abort: "Abort",
  skip_welcome: true,
  colour: "#684EAD",
};

test("send works after expired session recovery (mocked)", async ({ page }) => {
  const interviewUrl = `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_expired`;

  const sessionKey = `qv-interview-session:${PROJECT_ID}:${EXTERNAL_ID}_expired`;
  const externalKey = `qv-interview-last-external:${PROJECT_ID}`;

  await page.addInitScript(
    ({ sessionKey, externalKey, staleUuid, externalId }) => {
      localStorage.setItem(sessionKey, JSON.stringify({ uuid: staleUuid, updatedAt: Date.now() }));
      localStorage.setItem(externalKey, externalId);
    },
    { sessionKey, externalKey, staleUuid: STALE_UUID, externalId: `${EXTERNAL_ID}_expired` },
  );

  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ ...baseProject, id: PROJECT_ID }]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: FRESH_UUID, projectId: PROJECT_ID }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    const reqUuid = route.request().headers()["uuid"] || "";
    if (reqUuid === STALE_UUID) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "Session expired" }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          response: "Welcome back! Let's continue.",
          status: "open",
          progress: { current: 1, total: 3, ratio: 0.33 },
        }),
      });
    }
  });

  let replyUuid = "";
  await page.route("**/api/reply", async (route) => {
    replyUuid = route.request().headers()["uuid"] || "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Great answer! Next one.",
        status: "open",
        progress: { current: 2, total: 3, ratio: 0.66 },
      }),
    });
  });

  await page.goto(interviewUrl, { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Welcome back! Let's continue.")).toBeVisible();

  const input = page.getByRole("textbox");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();

  const sendButton = page.getByText(SEND_BUTTON_LABEL);
  await input.fill("Testing expired session recovery.");
  await expect(sendButton).toBeEnabled();

  const replyResponse = page.waitForResponse(
    (r) => r.url().includes("/api/reply") && r.status() === 200,
    { timeout: 30_000 },
  );
  await sendButton.click();
  await replyResponse;

  expect(replyUuid).toBe(FRESH_UUID);
  await expect(page.getByText("Great answer! Next one.")).toBeVisible();
});

test("send error during conversation shows error and allows retry (mocked)", async ({ page }) => {
  let replyCalls = 0;

  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ ...baseProject, id: PROJECT_ID }]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: "uuid-error-test", projectId: PROJECT_ID }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Tell me about yourself.",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      }),
    });
  });

  await page.route("**/api/reply", async (route) => {
    replyCalls += 1;
    if (replyCalls === 1) {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Failed to send reply" }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          response: "Thanks for sharing!",
          status: "open",
          progress: { current: 2, total: 3, ratio: 0.66 },
        }),
      });
    }
  });

  await page.goto(
    `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_error`,
    { waitUntil: "domcontentloaded" },
  );

  await expect(page.getByText("Tell me about yourself.")).toBeVisible();

  const input = page.getByRole("textbox");
  const sendButton = page.getByRole("button", { name: "Send" });
  await input.fill("First attempt that will fail.");
  await sendButton.click();

  const errorAlert = page.locator('p[role="alert"]');
  await expect(errorAlert).toBeVisible();
  await expect(errorAlert).toContainText(/failed/i);

  await expect(input).toBeEnabled();
  await input.fill("Second attempt that should succeed.");

  const retryResponse = page.waitForResponse(
    (r) => r.url().includes("/api/reply") && r.status() === 200,
    { timeout: 30_000 },
  );
  await sendButton.click();
  await retryResponse;

  await expect(page.getByText("Thanks for sharing!")).toBeVisible();
  await expect(errorAlert).not.toBeVisible();
});

test("connection error preserves original question and allows retry (mocked)", async ({ page }) => {
  let replyCalls = 0;

  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ ...baseProject, id: PROJECT_ID }]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: "uuid-stream-test", projectId: PROJECT_ID }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Original question here.",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      }),
    });
  });

  await page.route("**/api/reply", async (route) => {
    replyCalls += 1;
    if (replyCalls === 1) {
      await route.abort("connectionreset");
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          response: "Recovered question after error.",
          status: "open",
          progress: { current: 2, total: 3, ratio: 0.66 },
        }),
      });
    }
  });

  await page.goto(
    `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}_stream`,
    { waitUntil: "domcontentloaded" },
  );

  await expect(page.getByText("Original question here.")).toBeVisible();

  const input = page.getByRole("textbox");
  await input.fill("Trigger connection error.");
  await page.getByText(SEND_BUTTON_LABEL).click();

  const errorAlert = page.locator('p[role="alert"]');
  await expect(errorAlert).toBeVisible({ timeout: 15_000 });

  await expect(page.getByText("Original question here.")).toBeVisible();

  await expect(input).toBeEnabled();
  await input.fill("Retry after connection error.");
  const retryResponse = page.waitForResponse(
    (r) => r.url().includes("/api/reply") && r.status() === 200,
    { timeout: 30_000 },
  );
  await page.getByText(SEND_BUTTON_LABEL).click();
  await retryResponse;

  await expect(page.getByText("Recovered question after error.")).toBeVisible();
  await expect(errorAlert).not.toBeVisible();
});
