"""
Optional helper script for listening to Supabase Realtime events.

Not used by the backend app. This file intentionally does NOT ship with any keys.
Configure via env vars if you want to run it manually.
"""

import os

from realtime.connection import Socket


def _required_env(name: str) -> str:
	value = os.environ.get(name)
	if not value or not value.strip():
		raise RuntimeError(f"Missing required env var: {name}")
	return value.strip()


def callback1(payload):
	status = payload['record']['user_id']

	if payload['record']['status'] == 0:
		print("Callback 1: ", status)

if __name__ == "__main__":
    # Example:
    #   export SUPABASE_PROJECT_REF="xuvugcsyyircdjyqsram"
    #   export SUPABASE_API_KEY="sb_publishable_..."  (or anon/service role if appropriate)
    supabase_ref = _required_env("SUPABASE_PROJECT_REF")
    api_key = _required_env("SUPABASE_API_KEY")
    URL = f"wss://{supabase_ref}.supabase.co/realtime/v1/websocket?apikey={api_key}&vsn=1.0.0"
    s = Socket(URL)
    s.connect()

    channel_1 = s.set_channel("realtime:*")
    channel_1.join().on("UPDATE", callback1)
    s.listen()