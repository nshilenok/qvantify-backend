import { test, expect } from "@playwright/test";

const baseURL = process.env.QVANTIFY_E2E_BASE_URL || "";
const shareToken = process.env.QVANTIFY_SHARE_TOKEN || "tok_secretkey_check";

test.describe("results portal share (live)", () => {
  test.skip(!baseURL, "Requires QVANTIFY_E2E_BASE_URL to hit a live deployment.");

  test("share login endpoint is not blocked by missing SECRET_KEY", async ({ request }) => {
    const resp = await request.post(`/api/share/${shareToken}/login`, {
      data: { password: "invalid-pass" },
    });
    const body = await resp.text();

    expect(resp.status(), body).not.toBe(500);
    expect(body).not.toContain("Missing SECRET_KEY");
  });
});
