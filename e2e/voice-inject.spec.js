import { test, expect } from "@playwright/test";

test("voice script injects mic and inserts transcript", async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.removeItem("project_details");
      localStorage.setItem("uuid", JSON.stringify("test-uuid"));
    } catch {
      // ignore
    }

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

  await page.route("**/api/project/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          voice_enabled: true,
          cta_reply: "Send",
          answer_placeholder: "Type your answer",
          colour: "#684EAD",
        },
      ]),
    });
  });

  await page.route("**/api/voice-transcribe/", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ text: "Hello from voice" }),
    });
  });

  await page.goto("/?interview=test_project", { waitUntil: "domcontentloaded" });

  await page.evaluate(() => {
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Type your answer";

    const button = document.createElement("button");
    button.textContent = "Send";

    const wrap = document.createElement("div");
    wrap.appendChild(input);
    wrap.appendChild(button);
    document.body.appendChild(wrap);
  });

  const mic = page.locator("#qvantify-mic-btn");
  await expect(mic).toBeVisible();

  await mic.click();
  await expect(page.locator("#qvantify-voice-helper")).toContainText("Listening");

  await page.locator("#qvantify-voice-stop").click();
  await expect(page.locator("input[type='text']")).toHaveValue(/Hello from voice/);
});
