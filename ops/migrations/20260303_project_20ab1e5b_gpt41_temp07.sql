-- Set project 20ab1e5b-54c4-4f03-8331-4f88132d3b51 to gpt-4.1, temperature 0.7
-- Interview URL: https://app.qvantify.com/interview?interview=20ab1e5b-54c4-4f03-8331-4f88132d3b51&external_id=user_001
UPDATE projects
SET model = 'gpt-4.1',
    temperature = 0.7
WHERE id = '20ab1e5b-54c4-4f03-8331-4f88132d3b51';
