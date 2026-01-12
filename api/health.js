import { json } from "./_utils.js";

export default async function handler(req, res) {
  return json(res, 200, { ok: true });
}

