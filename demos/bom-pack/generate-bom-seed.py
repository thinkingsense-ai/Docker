#!/usr/bin/env python3
"""Generates seed-bom.sql: an invented mechanical-BOM / sourcing dataset (schema `bom`) for the BOM demo pack.

Deterministic (fixed seed). Everything is made up: companies, SKUs, prices, quality records. The data carries deliberate traps
(an expired certificate, a facility at capacity, an active fire, a customer who has not approved a supplier, catalog parts that
need the distributor standard) so that sourcing questions have answers that depend on getting those rules right.

    python3 generate-bom-seed.py > seed-bom.sql
"""
import random

R = random.Random(20261105)
out = []


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(round(v, 4)) if isinstance(v, float) else str(v)
    return "'" + str(v).replace("'", "''") + "'"


def table(name, cols, rows, ddl):
    out.append("CREATE TABLE bom.%s (%s);" % (name, ddl))
    if rows:
        out.append("INSERT INTO bom.%s (%s) VALUES" % (name, ", ".join(cols)))
        out.append(",\n".join(" (" + ", ".join(q(v) for v in r) + ")" for r in rows) + ";")
    out.append("")


# ------------------------------------------------------------------ reference data
customers = [(1, "Kestrel Dynamics", "North America"), (2, "Alpenfluss Technik", "Europe")]

materials = [  # id, name, family, density g/cm3, cost per kg, yield strength MPa
    (1, "Aluminum 6061-T6", "Aluminum", 2.70, 4.2, 276), (2, "Aluminum 7075-T6", "Aluminum", 2.81, 6.8, 503),
    (3, "Stainless Steel 304", "Stainless steel", 8.00, 5.1, 215), (4, "Stainless Steel 316", "Stainless steel", 8.00, 6.9, 205),
    (5, "Steel 4140", "Alloy steel", 7.85, 2.6, 655), (6, "Titanium Ti-6Al-4V", "Titanium", 4.43, 38.0, 880),
    (7, "ABS", "Plastic", 1.05, 2.9, 40), (8, "Nylon PA12", "Plastic", 1.01, 9.5, 48),
    (9, "Carbon fiber composite", "Composite", 1.60, 55.0, 600), (10, "Mild steel", "Carbon steel", 7.85, 1.4, 250),
]
MID = {m[1]: m[0] for m in materials}

processes = [(1, "5-axis CNC milling", "Machining"), (2, "CNC turning", "Machining"), (3, "Grinding", "Machining"),
             (4, "Sheet metal", "Forming"), (5, "Die casting", "Casting"), (6, "Injection molding", "Molding"),
             (7, "Additive (SLS)", "Additive"), (8, "Welding", "Joining"), (9, "Composite layup", "Composites")]
PID = {p[1]: p[0] for p in processes}

certifications = [(1, "ISO 9001", "General quality management", "Manufacturers"),
                  (2, "AS9100", "Aerospace quality management for manufacturers of custom parts", "Manufacturers"),
                  (3, "AS9120", "Aerospace quality management for distributors of catalog and standard parts", "Distributors"),
                  (4, "NADCAP", "Special-process accreditation (heat treat, coatings, welding)", "Manufacturers")]

suppliers = [(1, "Great Lakes Fabrication", "Tier 1"), (2, "Northern Tool & Die", "Tier 1"), (3, "Monterrey Sheet Metal SA", "Tier 2"),
             (4, "Lone Star Machining", "Tier 1"), (5, "Sonoran Aerospace Components", "Tier 1"), (6, "Pearl River Precision", "Tier 2"),
             (7, "Mekong Machining", "Tier 2"), (8, "Kansai Precision Works", "Tier 1"), (9, "Swabian Castings AG", "Tier 2"),
             (10, "Jalisco Plastics", "Tier 2"), (11, "Prairie Composites", "Tier 1"), (12, "Erie Additive", "Tier 2"),
             (13, "Ohio Industrial Supply", "Distributor")]

# id, supplier, name, city, country, region, utilization %, status
facilities = [
    (1, 1, "Detroit Plant", "Detroit", "USA", "North America", 82, "Active"),
    (2, 2, "Mississauga Works", "Mississauga", "Canada", "North America", 97, "Active"),
    (3, 3, "Monterrey Plant", "Monterrey", "Mexico", "North America", 70, "Active"),
    (4, 4, "Austin Precision Center", "Austin", "USA", "North America", 78, "Active"),
    (5, 5, "Phoenix Aerospace Works", "Phoenix", "USA", "North America", 88, "Active"),
    (6, 6, "Shenzhen Plant", "Shenzhen", "China", "Asia Pacific", 74, "Active"),
    (7, 7, "Ho Chi Minh Works", "Ho Chi Minh City", "Vietnam", "Asia Pacific", 75, "Active"),
    (8, 8, "Osaka Precision Plant", "Osaka", "Japan", "Asia Pacific", 90, "Active"),
    (9, 9, "Stuttgart Foundry", "Stuttgart", "Germany", "Europe", 85, "Active"),
    (10, 10, "Guadalajara Molding", "Guadalajara", "Mexico", "North America", 60, "Active"),
    (11, 11, "Wichita Composites", "Wichita", "USA", "North America", 96, "Active"),
    (12, 12, "Cleveland Additive Lab", "Cleveland", "USA", "North America", 55, "Active"),
    (13, 6, "Dongguan Plant", "Dongguan", "China", "Asia Pacific", 69, "Active"),
    (14, 13, "Columbus Distribution Center", "Columbus", "USA", "North America", 40, "Active"),
]
FAC = {f[0]: f for f in facilities}

# facility -> (cert -> (issued, expires)); Detroit's AS9100 lapsed on 2026-03-31
fc = {1: {"ISO 9001": ("2024-05-01", "2027-04-30"), "AS9100": ("2023-04-01", "2026-03-31")},
      2: {"ISO 9001": ("2024-02-01", "2027-01-31"), "AS9100": ("2024-02-01", "2027-01-31")},
      3: {"ISO 9001": ("2025-03-01", "2028-02-29")},
      4: {"ISO 9001": ("2025-01-15", "2028-01-14"), "AS9100": ("2025-01-15", "2028-01-14"), "NADCAP": ("2025-06-01", "2027-05-31")},
      5: {"ISO 9001": ("2024-09-01", "2027-08-31"), "AS9100": ("2024-09-01", "2027-08-31"), "NADCAP": ("2024-09-01", "2027-08-31")},
      6: {"ISO 9001": ("2024-06-01", "2027-05-31")},
      7: {"ISO 9001": ("2025-04-01", "2028-03-31")},
      8: {"ISO 9001": ("2024-11-01", "2027-10-31"), "AS9100": ("2024-11-01", "2027-10-31")},
      9: {"ISO 9001": ("2025-02-01", "2028-01-31")},
      10: {"ISO 9001": ("2025-05-01", "2028-04-30")},
      11: {"ISO 9001": ("2024-08-01", "2027-07-31"), "AS9100": ("2024-08-01", "2027-07-31")},
      12: {"ISO 9001": ("2025-07-01", "2028-06-30")},
      13: {"ISO 9001": ("2025-03-01", "2028-02-29")},
      14: {"ISO 9001": ("2025-01-01", "2027-12-31"), "AS9120": ("2025-01-01", "2027-12-31")}}
CID = {c[1]: c[0] for c in certifications}
facility_certs = []
for f, d in fc.items():
    for code, (a, b) in d.items():
        facility_certs.append((len(facility_certs) + 1, f, CID[code], a, b))

# machine capability: facility -> {process: tightest tolerance mm}
cap = {1: {"5-axis CNC milling": .03, "CNC turning": .02, "Welding": .5},
       2: {"5-axis CNC milling": .02, "CNC turning": .01, "Sheet metal": .1},
       3: {"Sheet metal": .1, "Welding": .5, "CNC turning": .05},
       4: {"5-axis CNC milling": .01, "CNC turning": .005, "Grinding": .003},
       5: {"5-axis CNC milling": .01, "CNC turning": .01},
       6: {"5-axis CNC milling": .02, "CNC turning": .01, "Die casting": .15, "Injection molding": .1, "Sheet metal": .1},
       7: {"5-axis CNC milling": .03, "CNC turning": .02, "Sheet metal": .1},
       8: {"5-axis CNC milling": .005, "CNC turning": .005, "Grinding": .002},
       9: {"Die casting": .1, "CNC turning": .01, "5-axis CNC milling": .02},
       10: {"Injection molding": .1},
       11: {"Composite layup": .1, "5-axis CNC milling": .05},
       12: {"Additive (SLS)": .1},
       13: {"Sheet metal": .1, "Injection molding": .1, "5-axis CNC milling": .03}}
machines = []
for f, d in cap.items():
    for p, t in d.items():
        for k in range(1 if f not in (4, 6, 8) else 2):
            machines.append((len(machines) + 1, f, PID[p], "%s %d" % (p, k + 1), t, "Down for maintenance" if len(machines) == 17 else "Running"))

# material restrictions on who can make what
only = {"Titanium Ti-6Al-4V": {5, 8}, "Carbon fiber composite": {11}, "Nylon PA12": {12}}

# ------------------------------------------------------------------ products, assemblies, parts
products = [  # id, customer, sku, name, category, annual volume, target unit cost, cert, region restriction
    (1, 1, "KR-6", "KR-6 Articulated Robot Arm", "Robotics", 1200, 4400.00, "ISO 9001", None),
    (2, 1, "SK-9", "SK-9 Survey Drone", "Aerospace", 800, 3300.00, "AS9100", "North America"),
    (3, 2, "PU-3", "PU-3 Hydraulic Pump Unit", "Industrial", 3000, 650.00, "ISO 9001", None),
]
assemblies = [  # id, product, name, parent
    (1, 1, "KR-6 Top Level", None), (2, 1, "Base and Shoulder Module", 1), (3, 1, "Arm Module", 1), (4, 1, "Wrist and Gripper Module", 1),
    (5, 2, "SK-9 Top Level", None), (6, 2, "Airframe Module", 5), (7, 2, "Propulsion Module", 5), (8, 2, "Payload Module", 5),
    (9, 3, "PU-3 Top Level", None), (10, 3, "Housing Module", 9), (11, 3, "Rotating Group", 9), (12, 3, "Electrical Module", 9),
]

# part_no, name, source, material, process, critical, tol, finish, L, W, H, base cost USD (US plant), assembly, qty
P = [
    ("KR-101", "Base housing", "custom", "Aluminum 6061-T6", "5-axis CNC milling", 0, .05, "anodized", 300, 300, 120, 310.0, 2, 1),
    ("KR-102", "Shoulder bracket", "custom", "Aluminum 6061-T6", "Sheet metal", 0, .2, "anodized", 200, 120, 20, 52.0, 2, 2),
    ("KR-103", "Upper arm tube", "custom", "Aluminum 7075-T6", "CNC turning", 1, .02, "anodized", 520, 55, 55, 190.0, 3, 1),
    ("KR-104", "Elbow gearbox housing", "custom", "Aluminum 7075-T6", "5-axis CNC milling", 1, .03, "anodized", 180, 150, 110, 265.0, 3, 1),
    ("KR-105", "Wrist flange", "custom", "Stainless Steel 304", "CNC turning", 1, .01, "passivated", 140, 140, 25, 96.0, 4, 1),
    ("KR-106", "Motor mount plate", "custom", "Aluminum 6061-T6", "5-axis CNC milling", 0, .1, "anodized", 170, 110, 15, 71.0, 2, 3),
    ("KR-107", "Cable cover", "custom", "ABS", "Injection molding", 0, .2, "raw", 180, 100, 40, 14.0, 3, 2),
    ("KR-108", "Sensor mount bracket", "custom", "Aluminum 6061-T6", "Sheet metal", 0, .2, "anodized", 90, 60, 12, 31.0, 4, 6),
    ("KR-109", "Joint shaft", "custom", "Steel 4140", "CNC turning", 1, .005, "ground", 300, 30, 30, 118.0, 3, 2),
    ("KR-110", "Gripper finger", "custom", "Stainless Steel 316", "5-axis CNC milling", 0, .05, "raw", 100, 40, 25, 66.0, 4, 2),
    ("KR-111", "Gripper palm", "custom", "Aluminum 6061-T6", "5-axis CNC milling", 0, .05, "anodized", 160, 120, 18, 83.0, 4, 1),
    ("KR-201", "Deep groove bearing 6008", "standard", None, None, 0, None, None, 68, 68, 15, 9.5, 3, 4),
    ("KR-202", "M6 socket head screw (pack of 50)", "standard", None, None, 0, None, None, 0, 0, 0, 11.0, 2, 4),
    ("KR-203", "Harmonic drive reducer", "standard", None, None, 1, None, None, 110, 110, 45, 680.0, 3, 3),
    ("KR-204", "Servo motor 400 W", "standard", None, None, 1, None, None, 90, 90, 120, 310.0, 3, 3),
    ("KR-206", "Linear guide rail 35 mm", "catalog", "Steel 4140", None, 0, None, "raw", 400, 35, 20, 88.0, 2, 2),
    ("SK-101", "Fuselage frame", "custom", "Aluminum 7075-T6", "5-axis CNC milling", 1, .05, "anodized", 480, 320, 90, 540.0, 6, 1),
    ("SK-102", "Motor arm", "custom", "Carbon fiber composite", "Composite layup", 1, .1, "raw", 320, 40, 40, 145.0, 6, 4),
    ("SK-103", "Landing gear leg", "custom", "Titanium Ti-6Al-4V", "5-axis CNC milling", 1, .03, "raw", 280, 45, 30, 420.0, 6, 2),
    ("SK-104", "Battery tray", "custom", "Aluminum 6061-T6", "Sheet metal", 0, .2, "anodized", 220, 140, 30, 64.0, 7, 1),
    ("SK-105", "Gimbal bracket", "custom", "Aluminum 6061-T6", "5-axis CNC milling", 0, .05, "anodized", 120, 80, 20, 92.0, 8, 1),
    ("SK-106", "Prop shaft", "custom", "Stainless Steel 316", "CNC turning", 1, .01, "passivated", 150, 20, 20, 105.0, 7, 4),
    ("SK-107", "Pod fairing", "custom", "Nylon PA12", "Additive (SLS)", 0, .1, "raw", 260, 140, 90, 78.0, 8, 1),
    ("SK-108", "Antenna mount", "custom", "Aluminum 6061-T6", "5-axis CNC milling", 0, .1, "anodized", 90, 60, 15, 58.0, 8, 2),
    ("SK-109", "Payload latch", "custom", "Stainless Steel 304", "5-axis CNC milling", 1, .03, "passivated", 80, 50, 20, 124.0, 8, 1),
    ("SK-110", "Vibration damper plate", "custom", "Aluminum 6061-T6", "Sheet metal", 0, .2, "raw", 150, 100, 6, 27.0, 6, 4),
    ("SK-201", "Brushless motor 2814", "standard", None, None, 1, None, None, 35, 35, 40, 54.0, 7, 4),
    ("SK-202", "ESC board 40 A", "standard", None, None, 1, None, None, 60, 25, 10, 38.0, 7, 4),
    ("SK-203", "Propeller 18 inch", "catalog", "Carbon fiber composite", None, 0, None, "raw", 457, 40, 10, 46.0, 7, 4),
    ("SK-204", "M3 fastener kit", "standard", None, None, 0, None, None, 0, 0, 0, 14.0, 6, 2),
    ("PU-101", "Pump body", "custom", "Aluminum 6061-T6", "Die casting", 1, .15, "raw", 240, 200, 160, 118.0, 10, 1),
    ("PU-102", "End cap", "custom", "Aluminum 6061-T6", "CNC turning", 0, .05, "anodized", 100, 100, 35, 33.0, 10, 2),
    ("PU-103", "Impeller", "custom", "Stainless Steel 316", "5-axis CNC milling", 1, .02, "passivated", 120, 120, 40, 142.0, 11, 1),
    ("PU-104", "Drive shaft", "custom", "Steel 4140", "CNC turning", 1, .005, "ground", 280, 25, 25, 97.0, 11, 1),
    ("PU-105", "Inlet manifold", "custom", "Stainless Steel 304", "Welding", 0, .5, "passivated", 220, 150, 90, 160.0, 10, 1),
    ("PU-106", "Mounting foot", "custom", "Steel 4140", "Sheet metal", 0, .3, "raw", 200, 80, 10, 19.0, 10, 2),
    ("PU-107", "Gasket retainer", "custom", "Aluminum 6061-T6", "CNC turning", 0, .05, "anodized", 90, 90, 10, 22.0, 10, 1),
    ("PU-108", "Terminal box cover", "custom", "ABS", "Injection molding", 0, .2, "raw", 150, 100, 45, 9.5, 12, 1),
    ("PU-201", "Mechanical seal", "standard", None, None, 1, None, None, 60, 60, 35, 48.0, 11, 1),
    ("PU-202", "O-ring kit", "standard", None, None, 0, None, None, 0, 0, 0, 12.0, 10, 1),
    ("PU-203", "Deep groove bearing 6205", "standard", None, None, 0, None, None, 52, 52, 15, 7.5, 11, 2),
    ("PU-204", "M8 hex bolt (pack of 25)", "standard", None, None, 0, None, None, 0, 0, 0, 8.0, 10, 3),
]
# catalog (configurable) items: id, sku, name, material, tightest tol, max L, max W, max H, finish, price, lead days, distributor cert
catalog = [
    (1, "HFB-6061", "Flat bracket, 6061", "Aluminum 6061-T6", .10, 250, 150, 25, "anodized", 38.0, 4, "ISO 9001"),
    (2, "HFB-6061A", "Flat bracket, 6061, aerospace-certified distributor", "Aluminum 6061-T6", .10, 250, 150, 25, "anodized", 44.0, 6, "AS9120"),
    (3, "PLT-6061", "Machined plate, 6061", "Aluminum 6061-T6", .05, 400, 300, 20, "anodized", 61.0, 5, "AS9120"),
    (4, "PLT-6061S", "Stock plate, 6061", "Aluminum 6061-T6", .10, 500, 400, 30, "raw", 19.0, 3, "ISO 9001"),
    (5, "SHF-4140", "Ground shaft, 4140", "Steel 4140", .01, 400, 40, 40, "ground", 72.0, 7, "ISO 9001"),
    (6, "FLG-304", "Turned flange, 304", "Stainless Steel 304", .02, 150, 150, 30, "passivated", 55.0, 6, "AS9120"),
    (7, "CAP-6061", "Turned end cap, 6061", "Aluminum 6061-T6", .05, 120, 120, 40, "anodized", 21.0, 4, "ISO 9001"),
    (8, "TUB-7075", "Round tube, 7075", "Aluminum 7075-T6", .05, 600, 60, 60, "anodized", 88.0, 9, "AS9120"),
    (9, "FNG-316", "Machined finger, 316", "Stainless Steel 316", .05, 120, 60, 30, "raw", 47.0, 6, "ISO 9001"),
    (10, "CVR-ABS", "Molded cover, ABS", "ABS", .20, 200, 120, 50, "raw", 6.5, 3, "ISO 9001"),
    (11, "MNT-6061", "Mount plate, 6061", "Aluminum 6061-T6", .10, 180, 120, 20, "anodized", 24.0, 3, "AS9120"),
    (12, "LGR-35", "Linear guide rail, 35 mm", "Steel 4140", .05, 600, 35, 20, "raw", 88.0, 8, "ISO 9001"),
    (13, "PRP-18", "Propeller, 18 inch", "Carbon fiber composite", .1, 457, 40, 10, "raw", 46.0, 10, "AS9120"),
]
CATID = {"KR-206": 12, "SK-203": 13}

SHAPE = {"KR-101": "housing", "KR-102": "bracket", "KR-103": "tube", "KR-104": "housing", "KR-105": "flange", "KR-106": "plate", "KR-107": "cover",
         "KR-108": "bracket", "KR-109": "shaft", "KR-110": "finger", "KR-111": "plate", "KR-206": "rail", "SK-101": "frame", "SK-102": "arm",
         "SK-103": "leg", "SK-104": "tray", "SK-105": "plate", "SK-106": "shaft", "SK-107": "fairing", "SK-108": "plate", "SK-109": "latch",
         "SK-110": "plate", "SK-203": "propeller", "PU-101": "housing", "PU-102": "cap", "PU-103": "impeller", "PU-104": "shaft",
         "PU-105": "manifold", "PU-106": "foot", "PU-107": "ring", "PU-108": "cover"}
CSHAPE = {"HFB-6061": "bracket", "HFB-6061A": "bracket", "PLT-6061": "plate", "PLT-6061S": "plate", "SHF-4140": "shaft", "FLG-304": "flange",
          "CAP-6061": "cap", "TUB-7075": "tube", "FNG-316": "finger", "CVR-ABS": "cover", "MNT-6061": "plate", "LGR-35": "rail", "PRP-18": "propeller"}
parts = []
bom_lines = []
for (no, name, src, mat, proc, crit, tol, fin, L, W, H, base, asm, qty) in P:
    parts.append((no, name, src, SHAPE.get(no), MID.get(mat), PID.get(proc), bool(crit), tol, fin, L, W, H, CATID.get(no)))
    bom_lines.append((len(bom_lines) + 1, asm, no, qty))
# a few parts used in more than one place
for _a, _p, _q in [(11, "KR-202", 2), (10, "KR-202", 2), (4, "KR-201", 2)]:
    bom_lines.append((len(bom_lines) + 1, _a, _p, _q))
BASE = {p[0]: p[11] for p in P}
PART = {p[0]: p for p in P}

# ------------------------------------------------------------------ quotes
factor = {"USA": 1.0, "Canada": .96, "Mexico": .84, "China": .68, "Vietnam": .74, "Japan": 1.22, "Germany": 1.14}
tariff = {"USA": 0, "Canada": 0, "Mexico": 0, "China": 25, "Vietnam": 10, "Japan": 5, "Germany": 4}
ship = {"USA": 12, "Canada": 15, "Mexico": 18, "China": 36, "Vietnam": 33, "Japan": 28, "Germany": 26}
quotes = []
for no, (_, name, src, mat, proc, crit, tol, fin, L, W, H, base, asm, qty) in PART.items():
    if src == "custom":
        cands = []
        for f, caps in cap.items():
            if proc in caps and caps[proc] <= tol and f in only.get(mat, {f}):
                if proc == "Die casting" and f not in (6, 9):
                    continue
                cands.append(f)
        for f in cands:
            c = FAC[f][4]
            cost = base * factor[c] * R.uniform(.95, 1.08)
            if f in (5, 11):
                cost *= 1.08  # aerospace premium
            lead = 10 + R.randint(0, 9) + ship[c]
            quotes.append([len(quotes) + 1, no, f, PID[proc], round(cost, 2), tariff[c], lead, R.choice([25, 50, 100]), "2027-03-31", False])
    else:
        c = "USA"
        quotes.append([len(quotes) + 1, no, 14, None, round(base * R.uniform(.97, 1.05), 2), 0, 3 + R.randint(0, 5), 1, "2027-03-31", False])
# select the cheapest landed quote per part (cost + tariff), ignoring certificates and capacity: that is today's sourcing
best = {}
for r in quotes:
    landed = r[4] * (1 + r[5] / 100)
    if r[1] not in best or landed < best[r[1]][0]:
        best[r[1]] = (landed, r)
for _, r in best.values():
    r[9] = True
quotes = [tuple(r) for r in quotes]

# ------------------------------------------------------------------ vendors, orders, quality, events
approved = []
for c in (1, 2):
    for s in suppliers:
        st = "approved"
        if c == 1 and s[0] in (6, 12):
            st = "pending"
        if c == 2 and s[0] == 5:
            st = "blocked"
        approved.append((len(approved) + 1, c, s[0], st))

sel = {r[1]: r for r in quotes if r[9]}
work_orders = []
for no, r in sel.items():
    if PART[no][2] != "custom":
        continue
    for k in range(R.choice([1, 2, 2])):
        qty = R.choice([60, 120, 200, 250, 400])
        scrap = int(qty * R.choice([.005, .01, .015, .02, .03, .045]))
        status = R.choice(["Completed", "Completed", "Completed", "In progress"])
        month = R.randint(5, 10)
        day = R.randint(1, 26)
        planned = "2026-%02d-%02d" % (month, day)
        actual = None if status == "In progress" else "2026-%02d-%02d" % (month, min(28, day + R.choice([0, 0, 1, 2, 4])))
        work_orders.append((len(work_orders) + 1, no, r[2], qty, scrap, status, planned, actual))
causes = ["Tool wear", "Material defect", "Tolerance drift", "Operator error", "Supplier process change", "Fixture misalignment"]
ncrs = []
for k, wo in enumerate(R.sample([w for w in work_orders if w[5] == "Completed"], 10)):
    cause = causes[k % len(causes)]
    ncrs.append((k + 1, wo[0], wo[1], wo[2], cause, R.choice(["Low", "Medium", "Medium", "High"]),
                 round(R.uniform(400, 9000), 2), "2026-%02d-%02d" % (R.randint(6, 10), R.randint(1, 27)),
                 R.choice(["Scrap", "Rework", "Use as is", "Return to supplier"])))
ecos = [(1, "KR-104", "Dimensional change", "Open", "Increase wall thickness at the gearbox bearing seat by 1.5 mm", "2026-10-02"),
        (2, "SK-103", "Material change", "In review", "Replace Ti-6Al-4V with Al 7075 to cut cost; needs structural validation", "2026-10-14"),
        (3, "PU-103", "Tolerance change", "Approved", "Relax vane thickness tolerance from 0.02 mm to 0.05 mm", "2026-09-21"),
        (4, "KR-102", "Finish change", "Open", "Switch from anodized to chromate conversion coating", "2026-10-28")]
events = [(1, 6, "Fire", "High", "Active", "2026-10-19", "Fire at the Shenzhen plant; production halted pending inspection"),
          (2, 1, "Certificate lapse", "Medium", "Active", "2026-04-01", "AS9100 certificate expired on 2026-03-31; renewal audit not yet scheduled"),
          (3, 2, "Capacity constraint", "Medium", "Active", "2026-09-30", "Machine downtime and a labor shortage have pushed utilization to 97%"),
          (4, 8, "Typhoon", "Low", "Resolved", "2026-08-12", "Two days of lost production; fully recovered"),
          (5, 7, "Tariff change", "Low", "Active", "2026-07-01", "Duty on parts imported from Vietnam raised to 10%")]
pos = []
for no, r in sel.items():
    for k in range(R.choice([1, 2])):
        qty = R.choice([100, 200, 400, 800])
        mo = R.randint(3, 10)
        promised = "2026-%02d-%02d" % (mo, R.randint(1, 25))
        rec = None
        if mo < 10 or R.random() < .5:
            y, m, d = promised.split("-")
            rec = "%s-%s-%02d" % (y, m, min(28, int(d) + R.choice([-2, 0, 0, 1, 3, 6, 9])))
        pos.append((len(pos) + 1, no, r[2], qty, round(r[4] * R.uniform(.98, 1.03), 2), promised, rec))
inventory = []
for no, r in sel.items():
    s = R.choice([40, 80, 120, 200])
    on = int(s * R.choice([.3, .6, 1.1, 1.4, 2.0]))
    inventory.append((len(inventory) + 1, no, r[2], on, s))
dfm = [(1, "KR-101", "Reduce pocket depth and radius corners to cut machining time", 12, "None"),
       (2, "KR-104", "Replace deep internal pocket with a two-piece design", 18, "Needs engineering validation"),
       (3, "KR-106", "Loosen non-critical hole tolerance from 0.05 mm to 0.1 mm", 7, "None"),
       (4, "SK-101", "Replace 7075 billet with a forged blank", 22, "Needs engineering validation"),
       (5, "SK-105", "Standardize hole sizes to the M3 tooling set", 6, "None"),
       (6, "SK-104", "Combine two bends into one hem", 9, "None"),
       (7, "PU-103", "Open vane spacing to ease 5-axis tool access", 10, "Needs engineering validation"),
       (8, "PU-105", "Use a standard 304 tube instead of a welded plate fabrication", 15, "None"),
       (9, "KR-108", "Use a single bend radius for all flanges", 5, "None"),
       (10, "KR-103", "Switch from solid bar to extruded tube stock", 14, "Needs engineering validation")]

# ------------------------------------------------------------------ emit
out.append("-- Generated by generate-bom-seed.py. Invented data: no real company, part, price or quality record.\n"
           "-- One schema (`bom`) in the shared Postgres, so the pack fits the free edition's three data sources.\n"
           "CREATE SCHEMA bom;\n")
table("customers", ["customer_id", "name", "region"], customers, "customer_id INT PRIMARY KEY, name VARCHAR(60), region VARCHAR(30)")
table("products", ["product_id", "customer_id", "sku", "name", "category", "annual_volume", "target_unit_cost", "required_certification", "region_restriction"], products,
      "product_id INT PRIMARY KEY, customer_id INT REFERENCES bom.customers, sku VARCHAR(20), name VARCHAR(60), category VARCHAR(30), annual_volume INT, target_unit_cost NUMERIC(10,2), required_certification VARCHAR(20), region_restriction VARCHAR(30)")
table("assemblies", ["assembly_id", "product_id", "name", "parent_assembly_id"], assemblies,
      "assembly_id INT PRIMARY KEY, product_id INT REFERENCES bom.products, name VARCHAR(60), parent_assembly_id INT REFERENCES bom.assemblies")
table("materials", ["material_id", "name", "family", "density_g_cm3", "cost_per_kg", "yield_strength_mpa"], materials,
      "material_id INT PRIMARY KEY, name VARCHAR(40), family VARCHAR(30), density_g_cm3 NUMERIC(5,2), cost_per_kg NUMERIC(7,2), yield_strength_mpa INT")
table("processes", ["process_id", "name", "family"], processes, "process_id INT PRIMARY KEY, name VARCHAR(40), family VARCHAR(30)")
table("catalog_items", ["catalog_item_id", "sku", "name", "shape", "material_id", "min_tolerance_mm", "max_length_mm", "max_width_mm", "max_height_mm", "finish", "unit_price", "lead_time_days", "distributor_certification"],
      [(c[0], c[1], c[2], CSHAPE[c[1]], MID[c[3]]) + c[4:] for c in catalog],
      "catalog_item_id INT PRIMARY KEY, sku VARCHAR(20), name VARCHAR(80), shape VARCHAR(20), material_id INT REFERENCES bom.materials, min_tolerance_mm NUMERIC(5,3), max_length_mm INT, max_width_mm INT, max_height_mm INT, finish VARCHAR(20), unit_price NUMERIC(10,2), lead_time_days INT, distributor_certification VARCHAR(20)")
table("parts", ["part_no", "name", "source_type", "shape", "material_id", "process_id", "is_critical", "tolerance_mm", "finish", "length_mm", "width_mm", "height_mm", "catalog_item_id"], parts,
      "part_no VARCHAR(12) PRIMARY KEY, name VARCHAR(60), source_type VARCHAR(10), shape VARCHAR(20), material_id INT REFERENCES bom.materials, process_id INT REFERENCES bom.processes, is_critical BOOLEAN, tolerance_mm NUMERIC(5,3), finish VARCHAR(20), length_mm INT, width_mm INT, height_mm INT, catalog_item_id INT REFERENCES bom.catalog_items")
table("bom_lines", ["bom_line_id", "assembly_id", "part_no", "quantity"], bom_lines,
      "bom_line_id INT PRIMARY KEY, assembly_id INT REFERENCES bom.assemblies, part_no VARCHAR(12) REFERENCES bom.parts, quantity INT")
table("suppliers", ["supplier_id", "name", "tier"], suppliers, "supplier_id INT PRIMARY KEY, name VARCHAR(60), tier VARCHAR(20)")
table("facilities", ["facility_id", "supplier_id", "name", "city", "country", "region", "utilization_pct", "status"], facilities,
      "facility_id INT PRIMARY KEY, supplier_id INT REFERENCES bom.suppliers, name VARCHAR(60), city VARCHAR(40), country VARCHAR(30), region VARCHAR(30), utilization_pct INT, status VARCHAR(20)")
table("certifications", ["certification_id", "code", "description", "applies_to"], certifications,
      "certification_id INT PRIMARY KEY, code VARCHAR(20), description VARCHAR(120), applies_to VARCHAR(20)")
table("facility_certifications", ["facility_certification_id", "facility_id", "certification_id", "issued_on", "expires_on"], facility_certs,
      "facility_certification_id INT PRIMARY KEY, facility_id INT REFERENCES bom.facilities, certification_id INT REFERENCES bom.certifications, issued_on DATE, expires_on DATE")
table("machines", ["machine_id", "facility_id", "process_id", "name", "tightest_tolerance_mm", "status"], machines,
      "machine_id INT PRIMARY KEY, facility_id INT REFERENCES bom.facilities, process_id INT REFERENCES bom.processes, name VARCHAR(50), tightest_tolerance_mm NUMERIC(5,3), status VARCHAR(30)")
table("quotes", ["quote_id", "part_no", "facility_id", "process_id", "unit_cost", "tariff_pct", "lead_time_days", "min_order_qty", "valid_until", "is_current_source"], quotes,
      "quote_id INT PRIMARY KEY, part_no VARCHAR(12) REFERENCES bom.parts, facility_id INT REFERENCES bom.facilities, process_id INT REFERENCES bom.processes, unit_cost NUMERIC(10,2), tariff_pct NUMERIC(5,2), lead_time_days INT, min_order_qty INT, valid_until DATE, is_current_source BOOLEAN")
table("approved_vendors", ["approved_vendor_id", "customer_id", "supplier_id", "status"], approved,
      "approved_vendor_id INT PRIMARY KEY, customer_id INT REFERENCES bom.customers, supplier_id INT REFERENCES bom.suppliers, status VARCHAR(20)")
table("work_orders", ["work_order_id", "part_no", "facility_id", "quantity", "scrap_quantity", "status", "planned_end", "actual_end"], work_orders,
      "work_order_id INT PRIMARY KEY, part_no VARCHAR(12) REFERENCES bom.parts, facility_id INT REFERENCES bom.facilities, quantity INT, scrap_quantity INT, status VARCHAR(20), planned_end DATE, actual_end DATE")
table("nonconformances", ["nonconformance_id", "work_order_id", "part_no", "facility_id", "root_cause", "severity", "cost", "opened_on", "disposition"], ncrs,
      "nonconformance_id INT PRIMARY KEY, work_order_id INT REFERENCES bom.work_orders, part_no VARCHAR(12) REFERENCES bom.parts, facility_id INT REFERENCES bom.facilities, root_cause VARCHAR(40), severity VARCHAR(10), cost NUMERIC(10,2), opened_on DATE, disposition VARCHAR(30)")
table("engineering_changes", ["eco_id", "part_no", "change_type", "status", "description", "opened_on"], ecos,
      "eco_id INT PRIMARY KEY, part_no VARCHAR(12) REFERENCES bom.parts, change_type VARCHAR(30), status VARCHAR(20), description VARCHAR(200), opened_on DATE")
table("supply_events", ["event_id", "facility_id", "event_type", "severity", "status", "started_on", "note"], events,
      "event_id INT PRIMARY KEY, facility_id INT REFERENCES bom.facilities, event_type VARCHAR(30), severity VARCHAR(10), status VARCHAR(15), started_on DATE, note VARCHAR(200)")
table("purchase_orders", ["purchase_order_id", "part_no", "facility_id", "quantity", "unit_cost", "promised_date", "received_date"], pos,
      "purchase_order_id INT PRIMARY KEY, part_no VARCHAR(12) REFERENCES bom.parts, facility_id INT REFERENCES bom.facilities, quantity INT, unit_cost NUMERIC(10,2), promised_date DATE, received_date DATE")
table("inventory", ["inventory_id", "part_no", "facility_id", "on_hand", "safety_stock"], inventory,
      "inventory_id INT PRIMARY KEY, part_no VARCHAR(12) REFERENCES bom.parts, facility_id INT REFERENCES bom.facilities, on_hand INT, safety_stock INT")
table("dfm_findings", ["finding_id", "part_no", "recommendation", "saving_pct", "performance_impact"], dfm,
      "finding_id INT PRIMARY KEY, part_no VARCHAR(12) REFERENCES bom.parts, recommendation VARCHAR(200), saving_pct NUMERIC(5,1), performance_impact VARCHAR(40)")

out.append("-- The app reads as a SELECT-only account, so no question can change the data.\n"
           "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omnigate_ro') THEN CREATE ROLE omnigate_ro LOGIN PASSWORD 'omnigate_ro'; END IF; END $$;\n"
           "GRANT CONNECT ON DATABASE postgres TO omnigate_ro;\nGRANT USAGE ON SCHEMA bom TO omnigate_ro;\nGRANT SELECT ON ALL TABLES IN SCHEMA bom TO omnigate_ro;")
print("\n".join(out))
