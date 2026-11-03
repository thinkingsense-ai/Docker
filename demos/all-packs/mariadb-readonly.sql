-- The image grants the account it creates (MARIADB_USER) everything on the database; narrow that to SELECT.
REVOKE ALL PRIVILEGES ON security.* FROM 'omnigate_ro'@'%';
GRANT SELECT ON security.* TO 'omnigate_ro'@'%';
FLUSH PRIVILEGES;
