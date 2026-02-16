-- Add logical cascade deletion for interview/project data.
-- Safe on existing DBs: clean orphans first, then add FK constraints.

-- 1) Cleanup invalid references before adding constraints.

-- Project-level invalid rows
DELETE FROM project_share_links l
WHERE l.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = l.project);

DELETE FROM interviews_sentences s
WHERE s.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = s.project);

DELETE FROM interviews i
WHERE i.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = i.project);

DELETE FROM usage_stats u
WHERE u.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = u.project);

DELETE FROM records r
WHERE r.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = r.project);

DELETE FROM topics t
WHERE t.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = t.project);

DELETE FROM respondents r
WHERE r.project IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = r.project);

-- Respondent-level invalid rows
DELETE FROM interviews_sentences s
WHERE s.respondent IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM respondents r WHERE r.id = s.respondent);

DELETE FROM interviews i
WHERE i.respondent IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM respondents r WHERE r.id = i.respondent);

DELETE FROM usage_stats u
WHERE u.user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM respondents r WHERE r.id = u.user_id);

DELETE FROM topics_log t
WHERE t.user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM respondents r WHERE r.id = t.user_id);

DELETE FROM records r
WHERE r.user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM respondents x WHERE x.id = r.user_id);

-- Topic invalid rows for FK topics_log.topic_id -> topics.id
UPDATE topics_log t
SET topic_id = NULL
WHERE t.topic_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM topics tp WHERE tp.id = t.topic_id);

-- 2) Helpful indexes for FK performance.
CREATE INDEX IF NOT EXISTS respondents_project_idx ON respondents(project);
CREATE INDEX IF NOT EXISTS topics_project_idx ON topics(project);
CREATE INDEX IF NOT EXISTS records_user_id_idx ON records(user_id);
CREATE INDEX IF NOT EXISTS records_project_idx ON records(project);
CREATE INDEX IF NOT EXISTS topics_log_user_id_idx ON topics_log(user_id);
CREATE INDEX IF NOT EXISTS topics_log_topic_id_idx ON topics_log(topic_id);
CREATE INDEX IF NOT EXISTS usage_stats_user_id_idx ON usage_stats(user_id);
CREATE INDEX IF NOT EXISTS usage_stats_project_idx ON usage_stats(project);
CREATE INDEX IF NOT EXISTS interviews_respondent_idx ON interviews(respondent);
CREATE INDEX IF NOT EXISTS interviews_project_idx ON interviews(project);
CREATE INDEX IF NOT EXISTS interviews_sentences_respondent_idx ON interviews_sentences(respondent);
CREATE INDEX IF NOT EXISTS interviews_sentences_project_idx ON interviews_sentences(project);

-- 3) Add FK constraints with ON DELETE behavior.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'respondents_project_fkey') THEN
    ALTER TABLE respondents
      ADD CONSTRAINT respondents_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'topics_project_fkey') THEN
    ALTER TABLE topics
      ADD CONSTRAINT topics_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'project_share_links_project_fkey') THEN
    ALTER TABLE project_share_links
      ADD CONSTRAINT project_share_links_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'records_user_id_fkey') THEN
    ALTER TABLE records
      ADD CONSTRAINT records_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES respondents(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'records_project_fkey') THEN
    ALTER TABLE records
      ADD CONSTRAINT records_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'topics_log_user_id_fkey') THEN
    ALTER TABLE topics_log
      ADD CONSTRAINT topics_log_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES respondents(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'topics_log_topic_id_fkey') THEN
    ALTER TABLE topics_log
      ADD CONSTRAINT topics_log_topic_id_fkey
      FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'usage_stats_user_id_fkey') THEN
    ALTER TABLE usage_stats
      ADD CONSTRAINT usage_stats_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES respondents(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'usage_stats_project_fkey') THEN
    ALTER TABLE usage_stats
      ADD CONSTRAINT usage_stats_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'interviews_respondent_fkey') THEN
    ALTER TABLE interviews
      ADD CONSTRAINT interviews_respondent_fkey
      FOREIGN KEY (respondent) REFERENCES respondents(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'interviews_project_fkey') THEN
    ALTER TABLE interviews
      ADD CONSTRAINT interviews_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'interviews_sentences_respondent_fkey') THEN
    ALTER TABLE interviews_sentences
      ADD CONSTRAINT interviews_sentences_respondent_fkey
      FOREIGN KEY (respondent) REFERENCES respondents(id) ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'interviews_sentences_project_fkey') THEN
    ALTER TABLE interviews_sentences
      ADD CONSTRAINT interviews_sentences_project_fkey
      FOREIGN KEY (project) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;
