-- Strip parentheses from topics.system for project 20ab1e5b (e.g. "(For example: ...)" -> "For example: ...")
UPDATE topics
SET system = REPLACE(REPLACE(system, '(', ''), ')', '')
WHERE project = '20ab1e5b-54c4-4f03-8331-4f88132d3b51';
