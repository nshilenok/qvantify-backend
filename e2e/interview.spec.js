import { test, expect } from "@playwright/test";

const PROJECT_ID = process.env.QVANTIFY_PROJECT_ID || "sample_game_funnel_2026_01_14";
const EXTERNAL_ID = process.env.QVANTIFY_EXTERNAL_ID || "sample@user.com";

test("full journey: enter via url, chat, refresh, restart", async ({ page }) => {
  // Mock backend API so FE e2e can run deterministically without relying on a live deployment.
  let respondentCounter = 0;
  let replyCounter = 0;
  let currentQuestion = "Are you fine we start now?";

  const projectConfig = [
    {
      name: "Sample Interview",
      logo: "https://xuvugcsyyircdjyqsram.supabase.co/storage/v1/object/public/files/Qvantify.png",
      colour: "#5A45FF",
      welcome_title: "Welcome",
      welcome_message: "Welcome",
      success_title: "Thank you!",
      success_message: "Thanks for your time — your session was recorded.",
      welcome_second_title: "",
      welcome_second_message: "",
      consent: "",
      cta_next: "Start",
      cta_reply: "Send",
      cta_abort: "Abort",
      cta_restart: "Restart",
      question_title: "Question",
      answer_title: "Your answer",
      answer_placeholder: "Type your answer here…",
      loading: "Loading…",
      collect_email: false,
      email_title: "",
      email_placeholder: "",
      consent_link: "",
      skip_welcome: true,
      dark_mode: false,
      inline_consent: "",
    },
  ];

  await page.route("**/api/project/", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projectConfig) });
  });

  await page.route("**/api/respondent/", async (route) => {
    respondentCounter += 1;
    const uuid = `00000000-0000-4000-8000-${String(respondentCounter).padStart(12, "0")}`;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ uuid, projectId: PROJECT_ID }) });
  });

  await page.route("**/api/interview/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ response: currentQuestion, status: "open", answers: [] }),
    });
  });

  await page.route("**/api/reply/", async (route) => {
    replyCounter += 1;
    // Progress through a couple of questions, then allow abort/restart to be tested.
    const nextQuestions = [
      "Before you quit, what were you trying to do in the game and what motivated you to sign up?",
      "Can you walk me through what happened from the moment you decided to sign up until you stopped at the pre-payment step?",
      "What felt unclear, annoying, or risky about the pre-payment step?",
    ];
    currentQuestion = nextQuestions[Math.min(replyCounter - 1, nextQuestions.length - 1)];

    // Return SSE stream with a couple of deltas and a final event.
    const finalPayload = { type: "final", response: currentQuestion, status: "open", answers: [] };
    const sse =
      `data: ${JSON.stringify({ type: "delta", delta: "…" })}\n\n` +
      `data: ${JSON.stringify({ type: "delta", delta: "" })}\n\n` +
      `data: ${JSON.stringify(finalPayload)}\n\n`;

    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: sse,
    });
  });

  // Enter via URL (with external_id)
  await page.goto(`/?interview=${encodeURIComponent(PROJECT_ID)}&external_id=${encodeURIComponent(EXTERNAL_ID)}`, {
    waitUntil: "domcontentloaded",
  });

  // Expect we're on the Topic screen and see a question
  await expect(page.getByText("Question", { exact: true })).toBeVisible();

  // Send 2 replies to advance through single_question topics
  for (const msg of ["Yes", "I wanted to try it"]) {
    const input = page.locator("textarea");
    await expect(input).toBeVisible();
    await input.fill(msg);
    await page.locator("text=Send").click();
    // Wait for next assistant question to show up (any non-empty content)
    await expect(page.locator("text=Question")).toBeVisible();
  }

  // Refresh mid-session: should not crash / should still show the UI
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("Question", { exact: true })).toBeVisible();

  // Abort -> Success screen (this is the existing UX path)
  await page.locator("text=Abort").click();
  await expect(page.getByText(/thank you/i)).toBeVisible();

  // Restart -> back to flow
  await page.locator("text=Restart").click();
  // IndexRedirect routes to Welcome/Topic automatically; just assert app is alive.
  await expect(page.getByText("Question", { exact: true })).toBeVisible();
});

