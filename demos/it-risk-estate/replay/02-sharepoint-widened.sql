-- SharePoint event: the credentials sheet for the production gateway is re-shared with the whole company (upsert: the latest state replaces the earlier one).
INSERT INTO estate.sharepoint_items VALUES
 (2, 'Payments Engineering', 'Runbooks', 'Gateway admin credentials (shared sheet)', 'credential', 'company', 3100, 1, '2026-11-20 14:20', 'sharepoint.items', 0, 107)
ON CONFLICT (item_id) DO UPDATE SET shared_with = EXCLUDED.shared_with, audience = EXCLUDED.audience, modified_at = EXCLUDED.modified_at, kafka_offset = EXCLUDED.kafka_offset;
