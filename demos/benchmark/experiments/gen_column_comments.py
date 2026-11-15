"""gen_column_comments.py <columns.json> <pack> [--definitions]: SQL that adds column comments (and with --definitions, composite business definitions
appended to a table's existing description). Run after the seed, e.g. run_variant.sh bom cols 3 --extra-sql <file>."""
import json, sys, os, glob
spec = json.load(open(sys.argv[1])); pack = sys.argv[2]; defs = "--definitions" in sys.argv
esc = lambda s: s.replace("'", "''")
out = [f"COMMENT ON COLUMN {k} IS '{esc(v)}';" for k, v in spec["columns"].items()]
if defs:
    know = json.load(open(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", f"{pack}-pack", "*-knowledge.json"))[0]))["entities"]
    for table, text in spec["definitions"].items():
        base = next(v for k, v in know.items() if k.endswith(":" + table))
        out.append(f"COMMENT ON TABLE {table} IS '{esc(base + ' ' + text)}';")
print("\n".join(out))
