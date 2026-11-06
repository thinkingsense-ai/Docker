#!/usr/bin/env python3
"""Writes demo-questions-bom.json (approved question bank) from the list below. Reference SQL uses connector.schema.table names (bom.*)."""
import json, os

LANDED = "q.unit_cost * (1 + q.tariff_pct / 100.0)"
CURRENT = "JOIN bom.quotes q ON q.part_no = bl.part_no AND q.is_current_source"
# facility is usable for a customer who needs `AS9100` in North America: valid certificate today, below 95% utilization, no active high-severity event
OK_FAC = """f.region = 'North America' AND f.utilization_pct < 95
      AND EXISTS (SELECT 1 FROM bom.facility_certifications fc JOIN bom.certifications c ON c.certification_id = fc.certification_id
                  WHERE fc.facility_id = f.facility_id AND c.code = 'AS9100' AND fc.expires_on >= CURRENT_DATE)
      AND NOT EXISTS (SELECT 1 FROM bom.supply_events e WHERE e.facility_id = f.facility_id AND e.status = 'Active' AND e.severity = 'High')
      AND EXISTS (SELECT 1 FROM bom.approved_vendors av WHERE av.supplier_id = f.supplier_id AND av.customer_id = 1 AND av.status = 'approved')"""

FIT = f"""SELECT p.part_no, p.name, ci.sku AS catalog_item, {LANDED} AS current_cost, ci.unit_price AS catalog_price FROM bom.parts p JOIN bom.quotes q ON q.part_no = p.part_no AND q.is_current_source JOIN bom.catalog_items ci ON ci.material_id = p.material_id AND ci.shape = p.shape AND ci.finish = p.finish AND ci.min_tolerance_mm <= p.tolerance_mm AND ci.max_length_mm >= p.length_mm AND ci.max_width_mm >= p.width_mm AND ci.max_height_mm >= p.height_mm WHERE p.source_type = 'custom' AND NOT p.is_critical AND ci.unit_price < {LANDED} AND (ci.distributor_certification = 'AS9120' OR NOT EXISTS (SELECT 1 FROM bom.bom_lines bl JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE bl.part_no = p.part_no AND pr.required_certification = 'AS9100'))"""

Q = [
 ("Which parts are in the KR-6 robot arm, and how many of each does it use?",
  """SELECT p.part_no, p.name, p.source_type, SUM(bl.quantity) AS quantity FROM bom.bom_lines bl JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id JOIN bom.parts p ON p.part_no = bl.part_no WHERE pr.sku = 'KR-6' GROUP BY p.part_no, p.name, p.source_type ORDER BY p.part_no"""),
 ("How many custom, catalog and standard parts does each product have?",
  """SELECT pr.sku, p.source_type, COUNT(DISTINCT p.part_no) AS parts FROM bom.products pr JOIN bom.assemblies a ON a.product_id = pr.product_id JOIN bom.bom_lines bl ON bl.assembly_id = a.assembly_id JOIN bom.parts p ON p.part_no = bl.part_no GROUP BY pr.sku, p.source_type ORDER BY pr.sku, p.source_type"""),
 ("What is each product's unit BOM cost at its current sources, including tariffs, compared with its target cost?",
  f"""SELECT pr.sku, ROUND(SUM(bl.quantity * {LANDED}), 2) AS unit_bom_cost, pr.target_unit_cost, ROUND(SUM(bl.quantity * {LANDED}) - pr.target_unit_cost, 2) AS over_target FROM bom.products pr JOIN bom.assemblies a ON a.product_id = pr.product_id JOIN bom.bom_lines bl ON bl.assembly_id = a.assembly_id {CURRENT} GROUP BY pr.sku, pr.target_unit_cost ORDER BY pr.sku"""),
 ("Which material is used by the most parts?",
  """SELECT m.name AS material, COUNT(*) AS parts FROM bom.parts p JOIN bom.materials m ON m.material_id = p.material_id GROUP BY m.name ORDER BY parts DESC, m.name LIMIT 5"""),
 ("Which facilities hold a valid AS9100 certificate today?",
  """SELECT f.name AS facility, f.country, fc.expires_on FROM bom.facilities f JOIN bom.facility_certifications fc ON fc.facility_id = f.facility_id JOIN bom.certifications c ON c.certification_id = fc.certification_id WHERE c.code = 'AS9100' AND fc.expires_on >= CURRENT_DATE ORDER BY f.name"""),
 ("Which facilities are running at 95% utilization or higher?",
  """SELECT name AS facility, city, utilization_pct FROM bom.facilities WHERE utilization_pct >= 95 ORDER BY utilization_pct DESC"""),
 ("Which supply disruptions are active right now, and which facility does each affect?",
  """SELECT e.event_type, e.severity, f.name AS facility, e.started_on, e.note FROM bom.supply_events e JOIN bom.facilities f ON f.facility_id = e.facility_id WHERE e.status = 'Active' ORDER BY CASE e.severity WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, e.started_on"""),
 ("Which parts have only one supplier quote, and which facility is it from?",
  """SELECT q.part_no, p.name, MIN(f.name) AS facility FROM bom.quotes q JOIN bom.parts p ON p.part_no = q.part_no JOIN bom.facilities f ON f.facility_id = q.facility_id GROUP BY q.part_no, p.name HAVING COUNT(*) = 1 ORDER BY q.part_no"""),
 ("A fire hit our Shenzhen plant. Which parts do we currently source there, and which products do they go into?",
  f"""SELECT q.part_no, p.name, pr.sku AS product, (SELECT COUNT(*) FROM bom.quotes q2 WHERE q2.part_no = q.part_no AND q2.facility_id <> q.facility_id) AS alternative_quotes FROM bom.quotes q JOIN bom.facilities f ON f.facility_id = q.facility_id JOIN bom.parts p ON p.part_no = q.part_no JOIN bom.bom_lines bl ON bl.part_no = q.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE q.is_current_source AND f.name = 'Shenzhen Plant' GROUP BY q.part_no, p.name, pr.sku, q.facility_id ORDER BY q.part_no, pr.sku"""),
 ("Which engineering change orders are still open or in review, and which products does each touch?",
  """SELECT e.eco_id, e.part_no, e.change_type, e.status, pr.sku AS product, a.name AS assembly FROM bom.engineering_changes e JOIN bom.bom_lines bl ON bl.part_no = e.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE e.status IN ('Open', 'In review') ORDER BY e.eco_id, pr.sku"""),
 ("Which parts of the SK-9 are currently sourced from a facility without a valid AS9100 certificate?",
  """SELECT p.part_no, p.name, f.name AS facility FROM bom.quotes q JOIN bom.parts p ON p.part_no = q.part_no JOIN bom.facilities f ON f.facility_id = q.facility_id JOIN bom.bom_lines bl ON bl.part_no = p.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE pr.sku = 'SK-9' AND q.is_current_source AND p.source_type = 'custom' AND NOT EXISTS (SELECT 1 FROM bom.facility_certifications fc JOIN bom.certifications c ON c.certification_id = fc.certification_id WHERE fc.facility_id = f.facility_id AND c.code = 'AS9100' AND fc.expires_on >= CURRENT_DATE) GROUP BY p.part_no, p.name, f.name ORDER BY p.part_no"""),
 ("What was the total cost of nonconformances by root cause?",
  """SELECT root_cause, COUNT(*) AS reports, ROUND(SUM(cost), 2) AS total_cost FROM bom.nonconformances GROUP BY root_cause ORDER BY total_cost DESC"""),
 ("Which suppliers deliver late most often, and what share of their purchase orders arrived after the promised date?",
  """SELECT s.name AS supplier, COUNT(*) AS orders_received, SUM(CASE WHEN po.received_date > po.promised_date THEN 1 ELSE 0 END) AS late_orders, ROUND(100.0 * SUM(CASE WHEN po.received_date > po.promised_date THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_pct FROM bom.purchase_orders po JOIN bom.facilities f ON f.facility_id = po.facility_id JOIN bom.suppliers s ON s.supplier_id = f.supplier_id WHERE po.received_date IS NOT NULL GROUP BY s.name ORDER BY late_pct DESC, s.name"""),
 ("Which parts are below their safety stock, and where are they held?",
  """SELECT i.part_no, p.name, f.name AS facility, i.on_hand, i.safety_stock FROM bom.inventory i JOIN bom.parts p ON p.part_no = i.part_no JOIN bom.facilities f ON f.facility_id = i.facility_id WHERE i.on_hand < i.safety_stock ORDER BY i.safety_stock - i.on_hand DESC, i.part_no"""),
 ("What is the scrap rate at each facility?",
  """SELECT f.name AS facility, SUM(w.quantity) AS units_made, SUM(w.scrap_quantity) AS units_scrapped, ROUND(100.0 * SUM(w.scrap_quantity) / SUM(w.quantity), 2) AS scrap_pct FROM bom.work_orders w JOIN bom.facilities f ON f.facility_id = w.facility_id GROUP BY f.name ORDER BY scrap_pct DESC"""),
 ("Which suppliers has Kestrel Dynamics not yet approved?",
  """SELECT s.name AS supplier, av.status FROM bom.approved_vendors av JOIN bom.suppliers s ON s.supplier_id = av.supplier_id JOIN bom.customers c ON c.customer_id = av.customer_id WHERE c.name = 'Kestrel Dynamics' AND av.status <> 'approved' ORDER BY s.name"""),
 ("Which current-source part has the longest lead time for each product?",
  """SELECT DISTINCT ON (pr.sku) pr.sku, q.part_no, p.name, q.lead_time_days FROM bom.quotes q JOIN bom.parts p ON p.part_no = q.part_no JOIN bom.bom_lines bl ON bl.part_no = q.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE q.is_current_source ORDER BY pr.sku, q.lead_time_days DESC, q.part_no"""),
 ("Which custom parts could be replaced by a configurable catalog item, and how much would each save per unit?",
  f"""WITH fit AS ({FIT}) SELECT DISTINCT ON (part_no) part_no, name, catalog_item, ROUND(current_cost, 2) AS current_cost, catalog_price, ROUND(current_cost - catalog_price, 2) AS saving_per_unit FROM fit ORDER BY part_no, catalog_price"""),
 ("How much would those catalog replacements save per year, using each product's annual volume?",
  f"""WITH fit AS ({FIT}), best AS (SELECT DISTINCT ON (part_no) * FROM fit ORDER BY part_no, catalog_price) SELECT COUNT(DISTINCT b.part_no) AS parts_replaced, ROUND(SUM((b.current_cost - b.catalog_price) * bl.quantity * pr.annual_volume), 0) AS annual_saving FROM best b JOIN bom.bom_lines bl ON bl.part_no = b.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id"""),
 ("Which custom parts cannot be replaced by a catalog item, and what rules them out?",
  f"""WITH fit AS ({FIT}) SELECT p.part_no, p.name, CASE WHEN p.is_critical THEN 'critical part' WHEN NOT EXISTS (SELECT 1 FROM bom.catalog_items ci WHERE ci.material_id = p.material_id) THEN 'no catalog item in this material' WHEN NOT EXISTS (SELECT 1 FROM bom.catalog_items ci WHERE ci.material_id = p.material_id AND ci.shape = p.shape) THEN 'no catalog item of this type' WHEN NOT EXISTS (SELECT 1 FROM bom.catalog_items ci WHERE ci.material_id = p.material_id AND ci.shape = p.shape AND ci.finish = p.finish) THEN 'no catalog item with this finish' WHEN NOT EXISTS (SELECT 1 FROM bom.catalog_items ci WHERE ci.material_id = p.material_id AND ci.shape = p.shape AND ci.max_length_mm >= p.length_mm AND ci.max_width_mm >= p.width_mm AND ci.max_height_mm >= p.height_mm) THEN 'too large for any catalog item' ELSE 'tolerance, certification or price rules it out' END AS reason FROM bom.parts p WHERE p.source_type = 'custom' AND p.part_no NOT IN (SELECT part_no FROM fit) ORDER BY p.part_no"""),
 ("To bring the SK-9 under AS9100 and within North America, which facility is cheapest for each custom part?",
  f"""SELECT DISTINCT ON (q.part_no) q.part_no, p.name, f.name AS facility, ROUND({LANDED}, 2) AS landed_cost, q.lead_time_days FROM bom.quotes q JOIN bom.parts p ON p.part_no = q.part_no JOIN bom.facilities f ON f.facility_id = q.facility_id JOIN bom.bom_lines bl ON bl.part_no = q.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE pr.sku = 'SK-9' AND p.source_type = 'custom' AND {OK_FAC} ORDER BY q.part_no, {LANDED}"""),
 ("Which SK-9 custom parts have no North American source that holds a valid AS9100 certificate and has capacity?",
  f"""SELECT p.part_no, p.name FROM bom.parts p JOIN bom.bom_lines bl ON bl.part_no = p.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE pr.sku = 'SK-9' AND p.source_type = 'custom' AND NOT EXISTS (SELECT 1 FROM bom.quotes q JOIN bom.facilities f ON f.facility_id = q.facility_id WHERE q.part_no = p.part_no AND {OK_FAC}) GROUP BY p.part_no, p.name ORDER BY p.part_no"""),
 ("If we moved every SK-9 custom part that has a compliant North American source to it, how would the SK-9 unit BOM cost change?",
  f"""WITH sk AS (SELECT bl.part_no, SUM(bl.quantity) AS qty FROM bom.bom_lines bl JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE pr.sku = 'SK-9' GROUP BY bl.part_no), cur AS (SELECT sk.part_no, sk.qty, {LANDED} AS c FROM sk JOIN bom.quotes q ON q.part_no = sk.part_no AND q.is_current_source), alt AS (SELECT q.part_no, MIN({LANDED}) AS c FROM bom.quotes q JOIN bom.facilities f ON f.facility_id = q.facility_id JOIN sk ON sk.part_no = q.part_no WHERE {OK_FAC} GROUP BY q.part_no) SELECT ROUND(SUM(cur.qty * cur.c), 2) AS current_unit_cost, ROUND(SUM(cur.qty * COALESCE(alt.c, cur.c)), 2) AS resourced_unit_cost, ROUND(100.0 * (SUM(cur.qty * COALESCE(alt.c, cur.c)) - SUM(cur.qty * cur.c)) / SUM(cur.qty * cur.c), 1) AS change_pct, COUNT(alt.part_no) AS parts_with_compliant_source FROM cur LEFT JOIN alt ON alt.part_no = cur.part_no"""),
 ("Which DFM findings would save money on the KR-6 with no performance impact, and how much per unit?",
  f"""SELECT d.part_no, p.name, d.recommendation, d.saving_pct, ROUND(SUM(bl.quantity) * {LANDED} * d.saving_pct / 100.0, 2) AS saving_per_robot FROM bom.dfm_findings d JOIN bom.parts p ON p.part_no = d.part_no JOIN bom.quotes q ON q.part_no = d.part_no AND q.is_current_source JOIN bom.bom_lines bl ON bl.part_no = d.part_no JOIN bom.assemblies a ON a.assembly_id = bl.assembly_id JOIN bom.products pr ON pr.product_id = a.product_id WHERE pr.sku = 'KR-6' AND d.performance_impact = 'None' GROUP BY d.part_no, p.name, d.recommendation, d.saving_pct, q.unit_cost, q.tariff_pct ORDER BY saving_per_robot DESC"""),
]
json.dump([{"question": q, "referenceSql": s, "category": "bom"} for q, s in Q], open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo-questions-bom.json"), "w"), indent=1)
print(len(Q), "questions")

# Questions that are not in the approved bank: reworded versions (to see how far matching reaches) and ones the data cannot answer.
PARA = [(1, "List every part in the KR-6 and the quantity per unit"), (8, "Which parts depend on a single quote?"),
        (11, "For the SK-9 drone, which custom parts come from plants that lack a current AS9100 certificate?"),
        (16, "Which suppliers are pending or blocked for Kestrel Dynamics?"),
        (18, "What custom parts can we swap for a catalog part and what do we save on each?"),
        (19, "What is the yearly saving if we make all the catalog swaps?"),
        (20, "Why can't the rest of the custom parts be swapped for catalog items?"),
        (21, "Cheapest AS9100 North American plant for each SK-9 custom part?"),
        (22, "Which SK-9 parts have no qualified North American source?"),
        (23, "What happens to the SK-9 unit cost if we re-source everything we can within North America under AS9100?"),
        (24, "Which no-risk design-for-manufacturing changes would cut KR-6 cost, and by how much per robot?")]
json.dump({"reworded": [{"question": t, "sameAs": Q[i - 1][0]} for i, t in PARA],
           "shouldDecline": [{"question": "What is the return on ad spend for the SK-9?", "why": "no marketing data"},
                             {"question": "What is the average employee salary at each facility?", "why": "no HR data"},
                             {"question": "What will the lead time for the KR-6 be next quarter?", "why": "a forecast, not a lookup"}]},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe-questions-bom.json"), "w"), indent=1)
