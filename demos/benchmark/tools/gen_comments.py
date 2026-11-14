"""gen_comments.py <pack> : prints the COMMENT ON / ALTER TABLE ... COMMENT statements for a pack's table descriptions (its *-knowledge.json),
Postgres statements to stdout and MariaDB statements (erp) to stderr-free second file with --mariadb. Used to test the effect of putting the
descriptions in the database, where the app reads them for its prompts."""
import json, sys, glob, os
pack = sys.argv[1]; mdb = "--mariadb" in sys.argv
f = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", f"{pack}-pack", "*-knowledge.json"))[0]
esc = lambda s: s.replace("'", "''")
pg, m = [], []
for key, desc in json.load(open(f))["entities"].items():
    phys = key.split(":", 1)[1]; schema, tbl = phys.split(".", 1)
    (m if schema == "erp" else pg).append(f"ALTER TABLE erp.{tbl} COMMENT = '{esc(desc)}';" if schema == "erp" else f"COMMENT ON TABLE {phys} IS '{esc(desc)}';")
print(("USE erp;\n" + "\n".join(m)) if mdb else "\n".join(pg))
