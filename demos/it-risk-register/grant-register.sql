-- Runs after init-smithsonian-and-readonly.sql, which creates the omnigate_ro role.
GRANT USAGE ON SCHEMA register TO omnigate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA register TO omnigate_ro;
