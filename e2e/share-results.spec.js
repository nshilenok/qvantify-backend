import { test, expect } from "@playwright/test";

const baseURL = process.env.QVANTIFY_E2E_BASE_URL || "http://127.0.0.1:4173";
const parsedBaseURL = new URL(baseURL);
const isStaticBuild =
  (parsedBaseURL.hostname === "127.0.0.1" || parsedBaseURL.hostname === "localhost") &&
  (parsedBaseURL.port === "" || parsedBaseURL.port === "4173");

async function stubShareRoutes(page, token) {
  // When the SPA boots at /results/, it redirects to /projects. Stub that fetch so the app stays stable.
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ projects: [] }) });
  });

  await page.route(`**/api/share/${token}/info`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ project: { id: "p1", name: "Customer Demo Project" }, requires_password: true }),
    });
  });

  await page.route(`**/api/share/${token}/login`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, project: { id: "p1" } }),
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

async function loginToShare(page, token) {
  // Static webServer doesn't support SPA fallback for deep links.
  // Load the SPA root, then navigate via History API.
  await page.goto(`/results/`, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => {
    window.history.pushState({}, "", `/results/share/${t}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, token);
  await expect(page.getByText("Customer Demo Project", { exact: true })).toBeVisible();

  await page.getByPlaceholder("Enter password").fill("demo-pass");
  await page.getByText("View Results", { exact: true }).click();
  await expect(page.getByText("sessions available", { exact: false })).toBeVisible();
}

test.describe("results portal (mocked)", () => {
  test.skip(!isStaticBuild, "Mocked results UI tests run only against local static build.");

  test("share link has no runtime errors (regression)", async ({ page }) => {
    const token = "tok_demo_123";
    const pageErrors = [];
    page.on("pageerror", (err) => pageErrors.push(err));

    await stubShareRoutes(page, token);
    await loginToShare(page, token);

    await page.getByRole("button", { name: /Stylized RPG fan/ }).click();
    await expect(page.getByText("Narrative summary", { exact: true })).toBeVisible();
    await expect(pageErrors, `Page errors: ${pageErrors.map((e) => e.message).join(" | ")}`).toHaveLength(0);
  });

  test("customer share link login -> view transcript -> notes autosave", async ({ page }) => {
    const token = "tok_demo_123";
    await stubShareRoutes(page, token);
    await loginToShare(page, token);

    await expect(page.getByRole("button", { name: /Stylized RPG fan/ })).toBeVisible();
    await page.getByRole("button", { name: /Stylized RPG fan/ }).click();
    await expect(page.getByText("Narrative summary", { exact: true })).toBeVisible();
    await expect(page.getByText("What kind of games do you enjoy most?", { exact: true })).toBeVisible();
    await expect(page.getByText("Export CSV", { exact: true })).toBeVisible();

    const note = "Great insight about progression.";
    const annotationRequestPromise = page.waitForRequest(
      (req) =>
        req.method() === "PUT" &&
        req.url().includes(`/api/share/${token}/sessions/s1/annotation`)
    );
    await page.getByPlaceholder("Add notes...").fill(note);
    const annotationRequest = await annotationRequestPromise;
    expect(annotationRequest.postDataJSON()).toMatchObject({ admin_note: note });
    const status = page.getByText("Notes save automatically", { exact: false });
    await expect(status).toContainText("Saved");
  });
});

