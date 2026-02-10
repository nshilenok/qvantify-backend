import { test, expect } from "@playwright/test";

const longNote =
  "Discovered SweepKing via Insta and stayed because the social proof looked authentic and the bonus ladder felt fair across multiple sessions.";
const longNotePreview = `${longNote.slice(0, 100)}...`;

async function stubShareRoutes(page, token) {
  const state = {
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
        admin_note: longNote,
        admin_like: 0,
        is_seen: false,
      },
      {
        id: "s2",
        created_at: "2026-01-13T14:00:00.000Z",
        external_id: "ext-456",
        persona_label: "Skeptic-Turned Slot Seeker",
        findings_summary: "Needs trust signals and payout clarity.",
        answer_count: 4,
        last_activity_at: "2026-01-13T14:10:00.000Z",
        is_closed: true,
        admin_note: "Keeps an eye on payout speed.",
        admin_like: 1,
        is_seen: true,
      },
      {
        id: "s3",
        created_at: "2026-01-13T16:00:00.000Z",
        external_id: "ext-789",
        persona_label: "Quiet Observer",
        findings_summary: "No meaningful responses yet.",
        answer_count: 0,
        last_activity_at: "2026-01-13T16:05:00.000Z",
        is_closed: false,
        admin_note: "",
        admin_like: 0,
        is_seen: false,
      },
    ],
  };

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
    const url = new URL(route.request().url());
    const responsesMinRaw = url.searchParams.get("responses_min");
    const responsesMin = Number.parseInt(responsesMinRaw || "", 10);
    const hideSeen = ["1", "true", "yes", "on"].includes((url.searchParams.get("hide_seen") || "").toLowerCase());

    let sessions = state.sessions.slice();
    if (Number.isFinite(responsesMin)) {
      sessions = sessions.filter((session) => session.answer_count >= responsesMin);
    }
    if (hideSeen) {
      sessions = sessions.filter((session) => !session.is_seen);
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: sessions.length,
        sessions,
        project: { id: "p1" },
      }),
    });
  });

  await page.route(`**/api/share/${token}/sessions/*/annotation`, async (route) => {
    const requestUrl = new URL(route.request().url());
    const pathParts = requestUrl.pathname.split("/");
    const sessionId = pathParts[pathParts.length - 2];
    const session = state.sessions.find((item) => item.id === sessionId);
    const payload = route.request().postDataJSON() || {};
    if (session) {
      if (payload.admin_note !== undefined) {
        session.admin_note = payload.admin_note;
      }
      if (payload.admin_like !== undefined) {
        session.admin_like = payload.admin_like;
      }
      if (payload.is_seen !== undefined) {
        session.is_seen = Boolean(payload.is_seen);
      }
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
  });

  await page.route(`**/api/share/${token}/sessions/*`, async (route) => {
    const requestUrl = new URL(route.request().url());
    const pathParts = requestUrl.pathname.split("/");
    const sessionId = pathParts[pathParts.length - 1];
    const session = state.sessions.find((item) => item.id === sessionId);
    if (!session) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "Session not found" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project: { id: "p1", name: "Customer Demo Project" },
        session: {
          id: session.id,
          created_at: session.created_at,
          external_id: session.external_id,
          persona_label: session.persona_label,
          findings_summary: session.findings_summary,
          analyzed_at: "2026-01-13T12:10:00.000Z",
          is_seen: session.is_seen,
          is_closed: session.is_closed,
          admin_like: session.admin_like,
          admin_note: session.admin_note,
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
}

test.describe("share results (mocked)", () => {
  test("share filters, seen state, and notes preview", async ({ page }) => {
    const token = "tok_demo_123";
    await stubShareRoutes(page, token);

    await page.goto(`/results/share/${token}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Customer Demo Project", { exact: true })).toBeVisible();

    await page.getByPlaceholder("Enter password").fill("demo-pass");
    await page.getByText("View Results", { exact: true }).click();
    await expect(page.getByText("sessions available", { exact: false })).toBeVisible();
    const s1Row = page.getByRole("button", { name: /Stylized RPG fan/ });
    const s2Row = page.getByRole("button", { name: /Skeptic-Turned Slot Seeker/ });
    const s3Row = page.getByRole("button", { name: /Quiet Observer/ });
    await expect(s1Row).toContainText("External ID: ext-123");
    await expect(s1Row).toContainText(longNotePreview);
    await expect(s2Row).toBeVisible();
    await expect(s3Row).toBeVisible();

    const hideEmptyRequestPromise = page.waitForRequest(
      (req) =>
        req.method() === "GET" &&
        req.url().includes(`/api/share/${token}/sessions`) &&
        req.url().includes("responses_min=1")
    );
    await page.getByLabel("Hide empty interviews").check();
    await hideEmptyRequestPromise;
    await expect(s3Row).toHaveCount(0);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByPlaceholder("Enter password").fill("demo-pass");
    await page.getByText("View Results", { exact: true }).click();
    await expect(page.getByLabel("Hide empty interviews")).toBeChecked();
    await expect(page.getByRole("button", { name: /Quiet Observer/ })).toHaveCount(0);

    await s1Row.click();
    await expect(page.getByText("What kind of games do you enjoy most?", { exact: true })).toBeVisible();
    const noteSaveRequestPromise = page.waitForRequest(
      (req) =>
        req.method() === "PUT" &&
        req.url().includes(`/api/share/${token}/sessions/s1/annotation`) &&
        (req.postData() || "").includes('"admin_note":"')
    );
    await page.getByPlaceholder("Add notes...").fill("Updated note for save state regression.");
    await noteSaveRequestPromise;
    const noteStatus = page.getByText(/Notes save automatically/i);
    await expect
      .poll(async () => (await noteStatus.textContent()) || "", { timeout: 5000 })
      .not.toContain("Saving...");

    const seenRequestPromise = page.waitForRequest(
      (req) =>
        req.method() === "PUT" &&
        req.url().includes(`/api/share/${token}/sessions/s1/annotation`) &&
        (req.postData() || "").includes('"is_seen":true')
    );
    await page.getByRole("button", { name: "Mark session as seen" }).click();
    await seenRequestPromise;
    await expect(page.getByRole("button", { name: "Mark session as unseen" })).toBeVisible();

    const hideSeenRequestPromise = page.waitForRequest(
      (req) =>
        req.method() === "GET" &&
        req.url().includes(`/api/share/${token}/sessions`) &&
        req.url().includes("hide_seen=1")
    );
    await page.getByLabel("Hide sessions marked as seen").check();
    await hideSeenRequestPromise;
    await expect(page.getByText("No sessions found")).toBeVisible();
  });
});
