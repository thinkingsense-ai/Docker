-- Slack event: a message in a public channel with a credential for the production gateway. The token is an invented placeholder, not a secret.
INSERT INTO estate.slack_messages VALUES
 (5, '#eng-general', 'public', 1240, 'j.patel', 'credential', 1,
  'Pasting the gateway admin token here so the night shift can fail over: [invented demo token].', '2026-11-20 14:05', 'slack.messages', 0, 205)
ON CONFLICT (message_id) DO UPDATE SET excerpt = EXCLUDED.excerpt, kafka_offset = EXCLUDED.kafka_offset;
