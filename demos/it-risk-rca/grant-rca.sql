-- Runs after init-smithsonian-and-readonly.sql, which creates the omnigate_ro role.
GRANT USAGE ON SCHEMA rca TO omnigate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA rca TO omnigate_ro;
