import { test, expect } from "@playwright/test";

async function stubShareRoutes(page, token) {
  await page.route(`**/api/share/${token}/info`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ project: { name: "Customer Demo Project" }, requires_password: true }),
    });
  });

  await page.route(`**/api/share/${token}/login`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  await page.route(`**/api/share/${token}/sessions**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 1,
        sessions: [
          {
            id: "s1",
            created_at: "2026-01-13T12:00:00.000Z",
            external_id: "ext-123",
            persona_label: "Stylized RPG fan",
            findings_summary: "Wants clear progression and dislikes grind.",
            answer_count: 2,
            last_activity_at: "2026-01-13T12:05:00.000Z",
            is_closed: true,
          },
        ],
        project: { id: "p1" },
      }),
    });
  });

  await page.route(`**/api/share/${token}/sessions/s1`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project: { id: "p1", name: "Customer Demo Project" },
        session: {
          id: "s1",
          created_at: "2026-01-13T12:00:00.000Z",
          external_id: "ext-123",
          persona_label: "Stylized RPG fan",
          findings_summary: "Wants clear progression and dislikes grind.",
          analyzed_at: "2026-01-13T12:10:00.000Z",
        },
        records: [
          {
            id: "m1",
            created_at: "2026-01-13T12:01:00.000Z",
            role: "assistant",
            content: "What kind of games do you enjoy most?",
            topic: "t1",
            topic_label: "Discovery. What kind of games do you enjoy most?",
          },
          {
            id: "m2",
            created_at: "2026-01-13T12:02:00.000Z",
            role: "user",
            content: "Stylized action RPGs with strong art direction.",
            topic: "t1",
            topic_label: "Discovery. What kind of games do you enjoy most?",
          },
        ],
      }),
    });
  });

  await page.route(`**/api/share/${token}/sessions/s1/annotation`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
}

test.describe("share results (mocked)", () => {
  test("share login -> transcript -> notes save", async ({ page }) => {
    const token = "tok_demo_123";
    await stubShareRoutes(page, token);

    await page.goto(`/results/share/${token}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Customer Demo Project", { exact: true })).toBeVisible();

    await page.getByPlaceholder("Enter password").fill("demo-pass");
    await page.getByText("View Results", { exact: true }).click();
    await expect(page.getByText("sessions available", { exact: false })).toBeVisible();
    const sessionRow = page.getByRole("button", { name: /Stylized RPG fan/ });
    await expect(sessionRow).toContainText("External ID: ext-123");

    await sessionRow.click();
    await expect(page.getByText("What kind of games do you enjoy most?", { exact: true })).toBeVisible();
    const headerMeta = page.getByText(/Times shown in your timezone/).locator("..");
    await expect(headerMeta).toContainText("External ID: ext-123");

    const note = "Great insight about progression.";
    const annotationRequestPromise = page.waitForRequest(
      (req) => req.method() === "PUT" && req.url().includes(`/api/share/${token}/sessions/s1/annotation`)
    );
    await page.getByPlaceholder("Add notes...").fill(note);
    await annotationRequestPromise;
    await expect(page.getByText(/Saved/i)).toBeVisible();
  });
});
