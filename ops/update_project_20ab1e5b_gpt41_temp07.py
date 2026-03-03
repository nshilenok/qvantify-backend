#!/usr/bin/env python3
"""One-off: set project 20ab1e5b to model gpt-4.1, temperature 0.7. Run from repo root with DATABASE_URL set."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
import credentials

PROJECT_ID = "20ab1e5b-54c4-4f03-8331-4f88132d3b51"
MODEL = "gpt-4.1"
TEMPERATURE = 0.7


def main():
    config = credentials.get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    n = 0
    try:
        cur.execute(
            "UPDATE projects SET model = %s, temperature = %s WHERE id = %s",
            (MODEL, TEMPERATURE, PROJECT_ID),
        )
        conn.commit()
        n = cur.rowcount
        if n:
            print(f"Updated project {PROJECT_ID}: model={MODEL}, temperature={TEMPERATURE}")
        else:
            print(f"No project found with id={PROJECT_ID}. Nothing updated.")
    finally:
        cur.close()
        conn.close()
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
