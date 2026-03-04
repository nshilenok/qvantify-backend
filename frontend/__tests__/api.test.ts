import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function makeJsonResponse(data: unknown, status = 200) {
  const text = JSON.stringify(data);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(data),
    body: null,
  } as unknown as Response;
}

describe("fetchProject", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("sends projectId in headers", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({ id: "proj1", name: "Test Project" })
    );

    const { fetchProject } = await import("@/lib/api");
    await fetchProject("proj1");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/project");
    expect(init.headers.projectId).toBe("proj1");
  });

  it("unwraps array response", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse([{ id: "proj1", name: "Test" }])
    );

    const { fetchProject } = await import("@/lib/api");
    const result = await fetchProject("proj1");
    expect(result.id).toBe("proj1");
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({ error: "Not found" }, 404)
    );

    const { fetchProject } = await import("@/lib/api");
    await expect(fetchProject("bad")).rejects.toThrow("Not found");
  });
});

describe("createRespondent", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("sends POST with correct headers and body", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({ uuid: "resp-123", project: "proj1" })
    );

    const { createRespondent } = await import("@/lib/api");
    await createRespondent({
      projectId: "proj1",
      externalId: "ext@test.com",
      email: "ext@test.com",
      consent: true,
    });

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/respondent");
    expect(init.method).toBe("POST");
    expect(init.headers.projectId).toBe("proj1");
    expect(init.headers.externalId).toBe("ext@test.com");

    const body = JSON.parse(init.body);
    expect(body.email).toBe("ext@test.com");
    expect(body.consent).toBe(true);
  });
});

describe("sendReply", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("sends POST with message in JSON body", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({
        response: "Hello",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      })
    );

    const { sendReply } = await import("@/lib/api");
    const result = await sendReply({
      projectId: "proj1",
      uuid: "user-1",
      message: "I love it",
    });

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/reply");
    expect(init.method).toBe("POST");
    expect(init.headers.projectId).toBe("proj1");
    expect(init.headers.uuid).toBe("user-1");

    const body = JSON.parse(init.body);
    expect(body.message).toBe("I love it");
    expect(body.voice_input).toBe(false);
    expect(body.audio_tokens).toBe(0);

    expect(result.response).toBe("Hello");
    expect(result.status).toBe("open");
  });

  it("includes voice_input and audio_tokens when provided", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({ response: "Ok", status: "open" })
    );

    const { sendReply } = await import("@/lib/api");
    await sendReply({
      projectId: "proj1",
      uuid: "user-1",
      message: "voice message",
      voiceInput: true,
      audioTokens: 150,
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.voice_input).toBe(true);
    expect(body.audio_tokens).toBe(150);
  });

  it("zeros audio_tokens when voiceInput is false", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({ response: "Ok", status: "open" })
    );

    const { sendReply } = await import("@/lib/api");
    await sendReply({
      projectId: "proj1",
      uuid: "user-1",
      message: "text",
      voiceInput: false,
      audioTokens: 999,
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.voice_input).toBe(false);
    expect(body.audio_tokens).toBe(0);
  });
});

describe("initInterview", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("sends GET with projectId and uuid headers", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({
        response: "Welcome!",
        status: "open",
        answers: null,
        progress: { current: 1, total: 3, ratio: 0.33 },
      })
    );

    const { initInterview } = await import("@/lib/api");
    await initInterview({ projectId: "proj1", uuid: "user-1" });

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/interview");
    expect(init.headers.projectId).toBe("proj1");
    expect(init.headers.uuid).toBe("user-1");
  });
});

describe("streamReply request shape", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("sends Accept: text/event-stream and stream: true", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({
        response: "Fallback",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      })
    );

    const { streamReply } = await import("@/lib/api");
    await streamReply({ projectId: "proj1", uuid: "user-1", message: "hi" });

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/reply");
    expect(init.method).toBe("POST");
    expect(init.headers.Accept).toBe("text/event-stream");

    const body = JSON.parse(init.body);
    expect(body.stream).toBe(true);
    expect(body.message).toBe("hi");
  });

  it("falls back to JSON when content-type is not event-stream", async () => {
    mockFetch.mockResolvedValue(
      makeJsonResponse({
        response: "JSON fallback",
        status: "open",
        progress: { current: 1, total: 3, ratio: 0.33 },
      })
    );

    const { streamReply } = await import("@/lib/api");
    const result = await streamReply({
      projectId: "proj1",
      uuid: "user-1",
      message: "test",
    });

    expect(result.response).toBe("JSON fallback");
    expect(result.status).toBe("open");
  });
});
