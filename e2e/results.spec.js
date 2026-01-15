import { test, expect } from "@playwright/test";

const baseURL = process.env.QVANTIFY_E2E_BASE_URL || "http://127.0.0.1:4173";
const parsedBaseURL = new URL(baseURL);
const isStaticBuild =
  (parsedBaseURL.hostname === "127.0.0.1" || parsedBaseURL.hostname === "localhost") &&
  (parsedBaseURL.port === "" || parsedBaseURL.port === "4173");

const activeShareLink = {
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
};

async function stubAdminRoutes(page, projectId, shareLinks = [activeShareLink]) {
  await page.route("**/api/admin/projects", async (route) => {
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

  await page.route(`**/api/admin/projects/${projectId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ project: { id: projectId, name: "Results Portal Demo" } }),
    });
  });

  await page.route(`**/api/admin/projects/${projectId}/usage`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project: { id: projectId },
        totals: {
          total: 12450,
          interviews: 9800,
          summary: 2650,
          other: 0,
        },
        services: [
          { service: "interviews", tokens: 9800 },
          { service: "summary", tokens: 2650 },
          { service: "other", tokens: 0 },
        ],
      }),
    });
  });

  await page.route(`**/api/admin/projects/${projectId}/share_links`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ links: shareLinks }),
    });
  });

  await page.route(`**/api/admin/projects/${projectId}/topics`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        topics: [
          {
            id: "t1",
            project: projectId,
            system: "What do you care about most when choosing a build?",
            length: 1,
            sequence: 1,
            topic_type: "single_question",
            expiration_strategy: "count",
            defined_answers: ["Transparent stats", "Skill progression"],
          },
          {
            id: "t2",
            project: projectId,
            system: "What makes a game feel fair?",
            length: 2,
            sequence: 2,
            topic_type: "auto",
            expiration_strategy: "time",
            defined_answers: { answers: ["Clear rules", "Predictable outcomes"] },
          },
        ],
      }),
    });
  });

  await page.route(`**/api/admin/projects/${projectId}/topics_log`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        logs: [
          {
            id: 11,
            topic_id: "t1",
            user_id: "19c86d43-0edc-4b95-9f10-cdf04e2da9b4",
            started_at: "2026-01-13T12:00:00.000Z",
            status: 1,
            responses: 2,
          },
          {
            id: 12,
            topic_id: "t2",
            user_id: "19c86d43-0edc-4b95-9f10-cdf04e2da9b4",
            started_at: "2026-01-13T12:04:00.000Z",
            status: 0,
            responses: 1,
          },
        ],
      }),
    });
  });

  await page.route(`**/api/admin/projects/${projectId}/sessions**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        sessions: [
          {
            id: "19c86d43-0edc-4b95-9f10-cdf04e2da9b4",
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
            id: "dfa292fd-947b-4494-a1f4-f54593b835cf",
            created_at: "2026-01-12T12:00:00.000Z",
            external_id: "ext-001",
            persona_label: "Egyptian game style lover",
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

  await page.route(`**/api/admin/projects/${projectId}/sessions/19c86d43-0edc-4b95-9f10-cdf04e2da9b4**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session: {
          id: "19c86d43-0edc-4b95-9f10-cdf04e2da9b4",
          created_at: "2026-01-13T12:00:00.000Z",
          external_id: null,
          persona_label: "Competitive min-maxer",
          findings_summary: "Wants transparent stats and hates hidden mechanics.",
          admin_like: -1,
          admin_note: "Not aligned with casual audience.",
          analyzed_at: "2026-01-13T12:10:00.000Z",
        },
        records: [
          {
            id: "r1",
            created_at: "2026-01-13T12:01:00.000Z",
            role: "assistant",
            content: "What do you care about most when choosing a build?",
            topic: "t1",
            topic_label: "Build preferences. What do you care about most when choosing a build?",
            admin_like: 0,
            admin_note: null,
          },
          {
            id: "r2",
            created_at: "2026-01-13T12:02:00.000Z",
            role: "user",
            content: "Transparent stats and optimization potential. I min-max quickly.",
            topic: "t1",
            topic_label: "Build preferences. What do you care about most when choosing a build?",
            admin_like: 0,
            admin_note: null,
          },
        ],
        project: {
          id: projectId,
          name: "Results Portal Demo",
          model: "gpt-5.2",
          temperature: 1,
          max_tokens: 256,
          top_p: 1,
          api: "openai",
          default_prompt: "Default system prompt",
        },
      }),
    });
  });
}

test.describe("results portal (mocked)", () => {
  test.skip(!isStaticBuild, "Mocked results UI tests run only against local static build.");

  test("admin projects -> project page -> transcript", async ({ page }) => {
    const projectId = "results_portal_demo_2026_01_14";
    await stubAdminRoutes(page, projectId);

    // Load Results SPA root; it should redirect to /projects inside the app
    await page.goto("/results/", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Interview Projects", { exact: true })).toBeVisible();

    // Open the project
    await page.getByText("Results Portal Demo", { exact: true }).click();
    // Wait for the project page shell to mount
    await expect(page.getByText("Filters", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Competitive min-maxer/ })).toBeVisible();
    await expect(page.getByText("Token usage", { exact: true })).toBeVisible();
    await expect(page.getByText("Interviews", { exact: true })).toBeVisible();
    await expect(page.getByText("Topics", { exact: true })).toBeVisible();
    await expect(page.getByText("Topic logs", { exact: true })).toBeVisible();

    // Click into a session and verify transcript content is shown
    await page.getByRole("button", { name: /Competitive min-maxer/ }).click();
    await expect(page.getByText("Narrative summary", { exact: true })).toBeVisible();
    await expect(page.getByText("What do you care about most when choosing a build?", { exact: true })).toBeVisible();
  });

  test("share modal shows separate copy buttons", async ({ page }) => {
    const projectId = "results_portal_demo_2026_01_14";
    await stubAdminRoutes(page, projectId);

    await page.goto("/results/", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Interview Projects", { exact: true })).toBeVisible();
    await page.getByText("Results Portal Demo", { exact: true }).click();
    await expect(page.getByText("Filters", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Share" }).click();
    await expect(page.getByText("Share Results", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy Local" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy Web" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy Password" })).toBeVisible();
  });

  test("session like updates immediately and confirms save", async ({ page }) => {
    const projectId = "results_portal_demo_2026_01_14";
    await stubAdminRoutes(page, projectId);

    await page.route(
      `**/api/admin/projects/${projectId}/sessions/19c86d43-0edc-4b95-9f10-cdf04e2da9b4/annotation`,
      async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 400));
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
      }
    );

    await page.goto("/results/", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Interview Projects", { exact: true })).toBeVisible();
    await page.getByText("Results Portal Demo", { exact: true }).click();
    await expect(page.getByText("Filters", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: /Competitive min-maxer/ }).click();

    const likeButton = page.getByRole("button", { name: /^Like$/ });
    await likeButton.click();
    await expect(likeButton).toHaveClass(/bg-emerald-50/);
    await expect(page.getByText("Saving...", { exact: true })).toBeVisible();
    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  });
});

