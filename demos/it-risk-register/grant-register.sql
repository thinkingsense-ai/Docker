-- Runs after init-smithsonian-and-readonly.sql, which creates the omnigate_ro role.
GRANT USAGE ON SCHEMA register TO omnigate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA register TO omnigate_ro;

-- The worker's role (step 8d): may only ADD rows to the register. The trigger on assessments also refuses UPDATE and DELETE for everyone, the owner included.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'register_writer') THEN CREATE ROLE register_writer LOGIN PASSWORD 'register-writer-local'; END IF;
END $$;
GRANT USAGE ON SCHEMA register TO register_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA register TO register_writer;
GRANT INSERT ON register.assessments TO register_writer;
GRANT USAGE ON SEQUENCE register.assessments_assessment_id_seq TO register_writer;
