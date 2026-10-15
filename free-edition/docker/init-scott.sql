-- Seeds the classic scott/emp/dept schema used throughout this project's own testing,
-- so `docker compose up` gives a working example out of the box.
CREATE SCHEMA IF NOT EXISTS scott;

CREATE TABLE scott.dept (
    deptno NUMERIC(2) PRIMARY KEY,
    dname  VARCHAR(14),
    loc    VARCHAR(13)
);

CREATE TABLE scott.emp (
    empno    NUMERIC(4) PRIMARY KEY,
    ename    VARCHAR(10),
    job      VARCHAR(9),
    mgr      NUMERIC(4),
    hiredate DATE,
    sal      NUMERIC(7,2),
    comm     NUMERIC(7,2),
    deptno   NUMERIC(2) REFERENCES scott.dept(deptno)
);

INSERT INTO scott.dept VALUES
    (10, 'ACCOUNTING', 'NEW YORK'),
    (20, 'RESEARCH',   'DALLAS'),
    (30, 'SALES',      'CHICAGO'),
    (40, 'OPERATIONS', 'BOSTON');

INSERT INTO scott.emp VALUES
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
