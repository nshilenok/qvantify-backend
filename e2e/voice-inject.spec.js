import { test, expect } from "@playwright/test";

test("voice button appends transcript into input", async ({ page }) => {
  await page.addInitScript(() => {
    class FakeRecorder {
      constructor(stream) {
        this.stream = stream;
        this.state = "inactive";
        this.mimeType = "audio/webm";
        this._listeners = {};
        this._hasData = false;
      }

      addEventListener(event, handler) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(handler);
      }

      _emit(event, payload) {
        const handlers = this._listeners[event] || [];
        handlers.forEach((handler) => handler(payload));
      }

      start() {
        this.state = "recording";
        setTimeout(() => {
          const blob = new Blob(["fake-audio"], { type: this.mimeType });
          this._hasData = true;
          this._emit("dataavailable", { data: blob, size: blob.size });
        }, 25);
      }

      stop() {
        if (!this._hasData) {
          const blob = new Blob(["fake-audio"], { type: this.mimeType });
          this._emit("dataavailable", { data: blob, size: blob.size });
        }
        this.state = "inactive";
        this._emit("stop");
      }
    }

    window.MediaRecorder = FakeRecorder;
    if (!navigator.mediaDevices) navigator.mediaDevices = {};
    navigator.mediaDevices.getUserMedia = () =>
      Promise.resolve({
        getTracks: () => [],
      });
  });

  await page.route("**/api/project", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          voice_enabled: true,
          cta_reply: "Send",
          answer_placeholder: "Type your answer",
          cta_next: "Start",
          skip_welcome: true,
          colour: "#684EAD",
        },
      ]),
    });
  });

  await page.route("**/api/respondent", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uuid: "test-uuid", projectId: "test_project" }),
    });
  });

  await page.route("**/api/interview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ response: "Hello there", status: "open", progress: { current: 1, total: 4, ratio: 0.25 } }),
    });
  });

  await page.route("**/api/voice-transcribe", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ text: "Hello from voice" }),
    });
  });

  await page.goto("/interview?interview=test_project", { waitUntil: "domcontentloaded" });

  const startButton = page.getByRole("button", { name: /start/i });
  if (await startButton.isVisible().catch(() => false)) {
    await startButton.click();
  }

  const mic = page.getByRole("button", { name: "Record voice" });
  await expect(mic).toBeVisible();
  await mic.click();

  const stop = page.getByRole("button", { name: "Stop recording" });
  await expect(stop).toBeVisible();
  await stop.click();

  const textarea = page.getByRole("textbox");
  await expect(textarea).toHaveValue(/Hello from voice/);
});

