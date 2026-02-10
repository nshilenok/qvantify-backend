import { test, expect } from "@playwright/test";

const PROJECT_ID = "layout_demo_project";
const EXTERNAL_ID = `e2e_layout_${Date.now()}_${Math.floor(Math.random() * 1000)}`;

const stubInterviewRoutes = async (page) => {
  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "Layout Demo Interview",
          answer_placeholder: "Type your answer here…",
          cta_reply: "Send",
          cta_next: "Start",
          cta_abort: "Abort",
          skip_welcome: true,
          voice_enabled: true,
          colour: "#684EAD",
        },
      ]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: "uuid-layout-demo", projectId: PROJECT_ID }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        response: "Tell me about the last time you used a new productivity tool.",
        status: "open",
        progress: { current: 1, total: 4, ratio: 0.25 },
      }),
    });
  });
};

test("interview layout (desktop + mobile screenshots)", async ({ page }, testInfo) => {
  await stubInterviewRoutes(page);
  await page.goto(
    `/interview?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}`,
    {
      waitUntil: "domcontentloaded",
    }
  );

  await expect(
    page.getByText("Tell me about the last time you used a new productivity tool.")
  ).toBeVisible();
  await expect(page.getByRole("textbox")).toBeVisible();
  await expect(page.getByRole("button", { name: "Record voice" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();

  await page.screenshot({
    path: `tmp/interview-layout-${testInfo.project.name}.png`,
    fullPage: true,
  });
});

