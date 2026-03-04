---
name: qvantify-interview-cleanup
description: Delete all interview data for a Qvantify project by project ID. Use when the user asks to clean up, delete, or remove interviews, respondents, or session data for a project.
---

# Qvantify Interview Cleanup

## MCP Server

Use **`user-supabase for qvantify EU`** with the `execute_sql` tool (parameter: `query`).

## Schema

All tables use `project TEXT` as the project identifier, except `topics_log` which links via `user_id UUID` → `respondents.id`.

| Table | Project filter column | Cascade parent |
|---|---|---|
| `records` | `project` | `respondents(id)` via `user_id` |
| `topics_log` | — (join via `user_id`) | `respondents(id)` via `user_id` |
| `usage_stats` | `project` | `respondents(id)` via `respondent` |
| `interviews_sentences` | `project` | `respondents(id)` via `respondent` |
| `interviews` | `project` | `respondents(id)` via `respondent` |
| `respondents` | `project` | `projects(id)` via `project` |

## Procedure

### 1. Count affected rows

```sql
SELECT 'respondents' AS tbl, count(*) AS cnt FROM respondents WHERE project = '<PROJECT_ID>'
UNION ALL SELECT 'records', count(*) FROM records WHERE project = '<PROJECT_ID>'
UNION ALL SELECT 'interviews', count(*) FROM interviews WHERE project = '<PROJECT_ID>'
UNION ALL SELECT 'interviews_sentences', count(*) FROM interviews_sentences WHERE project = '<PROJECT_ID>'
UNION ALL SELECT 'topics_log', count(*) FROM topics_log WHERE user_id IN (SELECT id FROM respondents WHERE project = '<PROJECT_ID>')
UNION ALL SELECT 'usage_stats', count(*) FROM usage_stats WHERE project = '<PROJECT_ID>'
```

**Show the counts to the user and ask for confirmation before deleting.**

### 2. Delete in FK-safe order

Execute each DELETE sequentially (child tables first):

```sql
DELETE FROM records WHERE project = '<PROJECT_ID>';
DELETE FROM topics_log WHERE user_id IN (SELECT id FROM respondents WHERE project = '<PROJECT_ID>');
DELETE FROM usage_stats WHERE project = '<PROJECT_ID>';
DELETE FROM interviews_sentences WHERE project = '<PROJECT_ID>';
DELETE FROM interviews WHERE project = '<PROJECT_ID>';
DELETE FROM respondents WHERE project = '<PROJECT_ID>';
```

### 3. Verify

Re-run the count query from step 1. All counts should be 0.

Report final result to the user.
