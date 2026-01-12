import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL =
  process.env.SUPABASE_URL || "https://xuvugcsyyircdjyqsram.supabase.co";

// Publishable/anon keys are safe to embed; still allow override via env.
const SUPABASE_KEY =
  process.env.SUPABASE_PUBLISHABLE_KEY ||
  process.env.SUPABASE_ANON_KEY ||
  "sb_publishable_Zl92vpA-p1uv0OeoLBBj_Q_jQUUoaxA";

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: false },
});

