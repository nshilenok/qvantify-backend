import { test, expect } from "@playwright/test";

const PROJECT_ID = "results_portal_demo_2026_01_14";

async function stubAdminRoutes(page, projectId) {
  await page.route("**/api/projects**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        projects: [
          {
            id: projectId,
            name: "Results Portal Demo",
            session_count: 2,
            last_activity_at: "2026-01-14T12:00:00.000Z",
          },
        ],
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project: { id: projectId, name: "Results Portal Demo", voice_enabled: true },
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/usage`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project: { id: projectId },
        totals: { total: 12450, interviews: 9800, summary: 2650, other: 0 },
        totals_usd: { total: 4.82, interviews: 3.6, summary: 1.22, other: 0 },
        services: [
          { service: "interviews", tokens: 9800 },
          { service: "summary", tokens: 2650 },
          { service: "other", tokens: 0 },
        ],
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/share_links`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        links: [
          {
            id: "share_123",
            label: null,
            allowed_exports: true,
            created_at: "2026-01-14T23:47:18.000Z",
            revoked_at: null,
            expires_at: null,
            last_used_at: null,
            status: "active",
            share_url: "https://app.qvantify.com/results/share/tok_demo_123",
            share_path: "/results/share/tok_demo_123",
            password: "demo-pass",
          },
        ],
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/topics`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ topics: [] }),
    });
  });

  await page.route(`**/api/projects/${projectId}/topics_log`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ logs: [] }),
    });
  });

  await page.route(`**/api/projects/${projectId}/sessions**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        sessions: [
          {
            id: "s1",
            created_at: "2026-01-13T12:00:00.000Z",
            external_id: null,
            persona_label: "Competitive min-maxer",
            findings_summary: "Wants transparent stats and hates hidden mechanics.",
            answer_count: 2,
            last_activity_at: "2026-01-13T12:05:00.000Z",
            is_closed: false,
            admin_like: -1,
            admin_note: "Not aligned with casual audience.",
          },
          {
            id: "s2",
            created_at: "2026-01-12T12:00:00.000Z",
            external_id: "ext-001",
            persona_label: "Stylized RPG fan",
            findings_summary: "Prefers stylized visuals and clear progression.",
            answer_count: 3,
            last_activity_at: "2026-01-12T12:06:00.000Z",
            is_closed: true,
            admin_like: 1,
            admin_note: "Strong candidate for stylized art direction.",
          },
        ],
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/sessions/s1`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session: {
          id: "s1",
          created_at: "2026-01-13T12:00:00.000Z",
          external_id: null,
          persona_label: "Competitive min-maxer",
          findings_summary: "Wants transparent stats and hates hidden mechanics.",
          admin_like: -1,
          admin_note: "Not aligned with casual audience.",
        },
        records: [
          {
            id: "r1",
            created_at: "2026-01-13T12:01:00.000Z",
            role: "assistant",
            content: "What do you care about most when choosing a build?",
            topic: "t1",
          },
          {
            id: "r2",
            created_at: "2026-01-13T12:02:00.000Z",
            role: "user",
            content: "Transparent stats and optimization potential. I min-max quickly.",
            topic: "t1",
          },
        ],
        project: {
          id: projectId,
          name: "Results Portal Demo",
        },
      }),
    });
  });

  await page.route(`**/api/projects/${projectId}/sessions/s1/annotation`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });
}

test.describe("results portal (mocked)", () => {
  test("projects list renders", async ({ page }) => {
    await stubAdminRoutes(page, PROJECT_ID);

    await page.goto("/results/projects", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Interview Projects", { exact: true })).toBeVisible();
    await expect(page.getByText("Results Portal Demo", { exact: true })).toBeVisible();
  });

  test("project detail shows transcript + usage + notes", async ({ page }) => {
    await stubAdminRoutes(page, PROJECT_ID);

    await page.goto(`/results/projects/${PROJECT_ID}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: /Competitive min-maxer/ })).toBeVisible();
    await page.getByRole("button", { name: /Competitive min-maxer/ }).click();

    await expect(page.getByText("What do you care about most when choosing a build?")).toBeVisible();
    await expect(page.getByText("Tokens:", { exact: false })).toBeVisible();

    const annotationRequestPromise = page.waitForRequest(
      (req) => req.method() === "PUT" && req.url().includes(`/api/projects/${PROJECT_ID}/sessions/s1/annotation`)
    );
    await page.getByPlaceholder("Admin notes...").fill("Great insight about progression.");
    await page.getByRole("button", { name: "Save" }).click();
    await annotationRequestPromise;
  });
});

