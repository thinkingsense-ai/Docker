-- Backend: procurement (Oracle). Run as SYSTEM. Creates a real, non-system application user --
-- deliberately NOT putting the purchase_orders table under SYSTEM itself: both OmniGate's own
-- SchemaIntrospector and Trino's Oracle connector filter SYSTEM as a system schema (correctly),
-- so a table owned by SYSTEM is invisible to either. This is a real, permanent capability fact,
-- not a workaround for a bug -- see docs/deployment/trino-cluster.md and this fixture's own
-- README for the full explanation.
BEGIN
  EXECUTE IMMEDIATE 'CREATE USER procurement IDENTIFIED BY omnigate';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -1920 THEN -- ORA-01920: user already exists -- fine, idempotent re-run
    RAISE;
  END IF;
END;
/
GRANT CONNECT, RESOURCE, UNLIMITED TABLESPACE TO procurement;
EXIT;
