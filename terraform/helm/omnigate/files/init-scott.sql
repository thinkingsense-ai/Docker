-- Seeds the classic scott/emp/dept schema so `docker compose up` gives you real, queryable
-- data out of the box — enough to ask a genuine business question ("who has job SALESMAN in the
-- Chicago department") and see the Ontology/NL2SQL pipeline resolve it end to end, without
-- needing your own database connected first.
--
-- Deliberately in the "public" schema, not a separate "scott" schema: Server's own
-- SchemaIntrospector only introspects the connecting account's own DEFAULT schema
-- (Connection#getSchema(), "public" for a plain Postgres login) — not every schema it can see —
-- specifically to avoid pulling in every table a broadly-privileged shared-database account
-- happens to have SELECT on. A "scott" schema is silently invisible to NL2SQL/the Ontology with
-- zero error (found live), which defeats the point of a demo meant to prove those work out of the
-- box.
CREATE TABLE dept (
    deptno NUMERIC(2) PRIMARY KEY,
    dname  VARCHAR(14),
    loc    VARCHAR(13)
);

CREATE TABLE emp (
    empno    NUMERIC(4) PRIMARY KEY,
    ename    VARCHAR(10),
    job      VARCHAR(9),
    mgr      NUMERIC(4),
    hiredate DATE,
    sal      NUMERIC(7,2),
    comm     NUMERIC(7,2),
    deptno   NUMERIC(2) REFERENCES dept(deptno)
);

INSERT INTO dept VALUES
    (10, 'ACCOUNTING', 'NEW YORK'),
    (20, 'RESEARCH',   'DALLAS'),
    (30, 'SALES',      'CHICAGO'),
    (40, 'OPERATIONS', 'BOSTON');

INSERT INTO emp VALUES
    (7369, 'SMITH',  'CLERK',     7902, '1980-12-17', 800,  NULL, 20),
    (7499, 'ALLEN',  'SALESMAN',  7698, '1981-02-20', 1600, 300,  30),
    (7521, 'WARD',   'SALESMAN',  7698, '1981-02-22', 1250, 500,  30),
    (7566, 'JONES',  'MANAGER',   7839, '1981-04-02', 2975, NULL, 20),
    (7654, 'MARTIN', 'SALESMAN',  7698, '1981-09-28', 1250, 1400, 30),
    (7698, 'BLAKE',  'MANAGER',   7839, '1981-05-01', 2850, NULL, 30),
    (7782, 'CLARK',  'MANAGER',   7839, '1981-06-09', 2450, NULL, 10),
    (7788, 'SCOTT',  'ANALYST',   7566, '1987-04-19', 3000, NULL, 20),
    (7839, 'KING',   'PRESIDENT', NULL, '1981-11-17', 5000, NULL, 10),
    (7844, 'TURNER', 'SALESMAN',  7698, '1981-09-08', 1500, 0,    30),
    (7876, 'ADAMS',  'CLERK',     7788, '1987-05-23', 1100, NULL, 20),
    (7900, 'JAMES',  'CLERK',     7698, '1981-12-03', 950,  NULL, 30),
    (7902, 'FORD',   'ANALYST',   7566, '1981-12-03', 3000, NULL, 20),
    (7934, 'MILLER', 'CLERK',     7782, '1982-01-23', 1300, NULL, 10);
