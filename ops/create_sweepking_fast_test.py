#!/usr/bin/env python3
"""One-off: duplicate project 20ab1e5b (Swipking3) into SwipkKingFastTest with simplified flow."""
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
import credentials

SOURCE_PROJECT_ID = "20ab1e5b-54c4-4f03-8331-4f88132d3b51"
NEW_PROJECT_NAME = "SwipkKingFastTest"

DEFAULT_PROMPT = (
    "You are conducting a customer development interview with an online casino / sweepstakes casino user.\n"
    'Check previous user response. If it does not make any sense, be nice and ask user what they mean by XYZ. '
    'If makes sense then call interview_topic_over({"status":"done"})'
)

# All project columns except id, name, default_prompt (those are overridden)
PROJECT_COPY_COLS = [
    "logo", "colour",
    "welcome_title", "welcome_message",
    "success_title", "success_message",
    "abort_title", "abort_message",
    "welcome_second_title", "welcome_second_message",
    "consent", "cta_next", "cta_reply", "cta_abort", "cta_restart",
    "question_title", "answer_title", "answer_placeholder", "loading",
    "collect_email", "email_title", "email_placeholder", "consent_link",
    "skip_welcome", "dark_mode", "inline_consent", "voice_enabled",
    "model", "reasoning_effort", "temperature", "api",
]

TOPIC_COLS = ["id", "project", "system", "title", '"group"', "length", "sequence",
              "topic_type", "expiration_strategy", "defined_answers"]


def main():
    config = credentials.get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()

    try:
        # --- Step 1: Copy project row ---
        cur.execute(
            f"SELECT {', '.join(PROJECT_COPY_COLS)} FROM projects WHERE id = %s",
            (SOURCE_PROJECT_ID,),
        )
        row = cur.fetchone()
        if not row:
            print(f"Source project {SOURCE_PROJECT_ID} not found.")
            return 1

        new_project_id = str(uuid.uuid4())
        col_vals = dict(zip(PROJECT_COPY_COLS, row))

        all_cols = ["id", "name", "default_prompt"] + PROJECT_COPY_COLS
        all_vals = [new_project_id, NEW_PROJECT_NAME, DEFAULT_PROMPT] + list(row)

        placeholders = ", ".join(["%s"] * len(all_cols))
        cur.execute(
            f"INSERT INTO projects ({', '.join(all_cols)}) VALUES ({placeholders})",
            all_vals,
        )
        print(f"Created project: {NEW_PROJECT_NAME} ({new_project_id})")

        # --- Step 2: Copy & interleave topics ---
        cur.execute(
            'SELECT id, system, title, "group", length, topic_type, expiration_strategy, defined_answers '
            "FROM topics WHERE project = %s ORDER BY sequence",
            (SOURCE_PROJECT_ID,),
        )
        source_topics = cur.fetchall()
        print(f"Found {len(source_topics)} source topics")

        seq = 1
        for t in source_topics:
            src_id, src_system, src_title, src_group, src_length, src_type, src_exp, src_answers = t

            # Strip "CURRENT TOPIC: " prefix from system
            system_text = src_system or ""
            if system_text.startswith("CURRENT TOPIC: "):
                system_text = system_text[len("CURRENT TOPIC: "):]

            # Main topic (single_question)
            main_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO topics (id, project, system, title, "group", length, sequence, '
                "topic_type, expiration_strategy, defined_answers) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (main_id, new_project_id, system_text, src_title, src_group,
                 src_length, seq, "single_question", src_exp, src_answers),
            )
            print(f"  [{seq:2d}] single_question: {src_title}")

            # Follow-up topic (auto, count-based, length=1)
            followup_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO topics (id, project, system, title, "group", length, sequence, '
                "topic_type, expiration_strategy, defined_answers) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (followup_id, new_project_id, "", "follow-up", src_group,
                 1, seq + 1, "auto", "count", None),
            )
            print(f"  [{seq + 1:2d}] auto:            follow-up")

            seq += 2

        conn.commit()
        print(f"\nDone. New project ID: {new_project_id}")
        print(f"Total topics created: {seq - 1}")
        return 0

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
