-- Fix SwipkKingFastTest follow-up topics: prompt → auto
-- The streaming reply path doesn't support tool-call detection for prompt type,
-- causing raw interview_topic_over(...) text to leak to the frontend.
-- Changing to auto routes through _handle_auto_non_stream which handles tools properly.

UPDATE topics
SET    topic_type = 'auto'
WHERE  project IN (SELECT id FROM projects WHERE name = 'SwipkKingFastTest')
  AND  title = 'follow-up'
  AND  topic_type = 'prompt'
  AND  expiration_strategy = 'count';
