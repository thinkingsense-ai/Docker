"""MCP tool list generated from contract.json: one tool per implemented operation marked tool=true. Approving a workflow is never a tool (spec FR-29)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))

def load_contract():
    with open(os.path.join(HERE, "contract.json")) as f: return json.load(f)

def tool_list(contract=None):
    c = contract or load_contract()
    return [{"name": o["name"], "description": o["description"], "inputSchema": o["input"]} for o in c["operations"] if o.get("implemented") and o.get("tool")]
