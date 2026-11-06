-- The image grants the account it creates (MARIADB_USER) everything on the database; narrow that to SELECT.
REVOKE ALL PRIVILEGES ON erp.* FROM 'omnigate_ro'@'%';
GRANT SELECT ON erp.* TO 'omnigate_ro'@'%';
FLUSH PRIVILEGES;
