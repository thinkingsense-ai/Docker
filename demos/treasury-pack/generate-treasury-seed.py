#!/usr/bin/env python3
"""Generates the Treasury pack's seed files (invented data; no real company, bank, vendor or account).

    python3 generate-treasury-seed.py            writes seed-treasury-postgres.sql and seed-treasury-mariadb.sql
    python3 generate-treasury-seed.py --verify   also writes seed-treasury-verify.sql (both halves in one Postgres, for checking reference SQL)

Deterministic (fixed seed). Dates are relative to the day the seed runs, so "stale" and "due in 14 days" stay true whenever the pack is started.
Traps planted on purpose: a bank feed that stopped, two portal feeds a day or two late, a frozen account, a vendor that switched invoicing
currency, duplicate invoices, an invoice with no purchase order, payments released above the dual-approval limit, an agent that acted outside
policy, a thin covenant, currencies with no hedge, and one entity whose forecasts keep missing.
"""
import os, random, sys

R = random.Random(20261106)
HERE = os.path.dirname(os.path.abspath(__file__))


class D:  # a date n days before the day the seed runs (negative = in the future)
    def __init__(self, n): self.n = n


class T:  # a timestamp h hours before now
    def __init__(self, h): self.h = h


def lit(v, dialect):
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    if isinstance(v, D):
        if dialect == "maria": return "CURDATE() %s INTERVAL %d DAY" % ("-" if v.n >= 0 else "+", abs(v.n))
        return "CURRENT_DATE %s %d" % ("-" if v.n >= 0 else "+", abs(v.n))
    if isinstance(v, T):
        if dialect == "maria": return "NOW() - INTERVAL %d HOUR" % v.h
        return "NOW() - INTERVAL '%d hours'" % v.h
    if isinstance(v, (int, float)): return repr(round(v, 4)) if isinstance(v, float) else str(v)
    return "'" + str(v).replace("'", "''") + "'"


def table(out, dialect, schema, name, cols, rows, ddl):
    out.append("CREATE TABLE %s%s (%s);" % (schema, name, ddl))
    if rows:
        for i in range(0, len(rows), 200):
            out.append("INSERT INTO %s%s (%s) VALUES" % (schema, name, ", ".join(cols)))
            out.append(",\n".join(" (" + ", ".join(lit(v, dialect) for v in r) + ")" for r in rows[i:i + 200]) + ";")
    out.append("")


# ------------------------------------------------------------------ reference data
FX = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "SGD": 0.74, "MXN": 0.055, "JPY": 0.0066}
entities = [(1, "Meridian Industrial Inc", "United States", "USD"), (2, "Meridian Europe GmbH", "Germany", "EUR"),
            (3, "Meridian UK Ltd", "United Kingdom", "GBP"), (4, "Meridian Asia Pte", "Singapore", "SGD"),
            (5, "Meridian Mexico SA", "Mexico", "MXN"), (6, "Meridian Japan KK", "Japan", "JPY")]
banks = [(1, "Atlantic National Bank", "United States"), (2, "Continental Trust AG", "Germany"), (3, "Thames & Co Bank", "United Kingdom"),
         (4, "Pacific Commerce Bank", "Singapore"), (5, "Hinode Mutual Bank", "Japan")]
# entity, bank, currency, type, status, feed, usd-equivalent balance
ACC = [(1, 1, "USD", "Operating", "Open", "API", 14e6), (1, 1, "USD", "Payroll", "Open", "API", 3e6), (1, 1, "USD", "Collection", "Open", "API", 6e6),
       (1, 1, "USD", "Concentration", "Open", "API", 42e6), (1, 2, "EUR", "Operating", "Open", "API", 2.2e6),
       (2, 2, "EUR", "Operating", "Open", "API", 9e6), (2, 2, "EUR", "Payroll", "Open", "API", 2.5e6), (2, 2, "EUR", "Collection", "Open", "File", 4.5e6),
       (2, 3, "GBP", "Operating", "Open", "File", 1.8e6), (2, 1, "USD", "Operating", "Open", "API", 3.1e6),
       (3, 3, "GBP", "Operating", "Open", "API", 7e6), (3, 3, "GBP", "Payroll", "Open", "API", 1.6e6), (3, 3, "GBP", "Collection", "Open", "Portal", 3.4e6),
       (3, 2, "EUR", "Operating", "Open", "API", 1.4e6),
       (4, 4, "SGD", "Operating", "Open", "Portal", 5.2e6), (4, 4, "SGD", "Collection", "Open", "Portal", 2.6e6), (4, 4, "USD", "Operating", "Open", "Portal", 3.8e6),
       (4, 4, "SGD", "Restricted", "Frozen", "Portal", 1.9e6), (4, 5, "JPY", "Operating", "Open", "Portal", 1.1e6),
       (5, 1, "MXN", "Operating", "Open", "File", 2.4e6), (5, 1, "MXN", "Payroll", "Open", "File", 0.9e6), (5, 1, "USD", "Collection", "Open", "File", 1.7e6),
       (6, 5, "JPY", "Operating", "Open", "API", 6.8e6), (6, 5, "JPY", "Payroll", "Open", "API", 1.4e6), (6, 5, "JPY", "Collection", "Open", "File", 3.0e6),
       (6, 5, "USD", "Operating", "Open", "API", 1.2e6), (6, 5, "JPY", "Operating", "Closed", "API", 0)]
accounts = []
for i, (e, b, c, t, s, f, usd) in enumerate(ACC, 1):
    accounts.append((i, e, b, "%s-%04d-%s" % ({"USD": "US", "EUR": "DE", "GBP": "GB", "SGD": "SG", "MXN": "MX", "JPY": "JP"}[c], 1000 + i * 7, t[:3].upper()),
                     c, t, s, f, D(R.randint(400, 3000))))
fx_rates = [(i + 1, c, FX[c], D(0)) for i, c in enumerate(FX)]

# ------------------------------------------------------------------ balances: ten daily snapshots; feeds that lag or stopped
STALE = {18: 6, 15: 2, 16: 2, 13: 2}  # account id -> days since the last balance (the frozen one stops too)
balances = []
for aid, (e, b, c, t, s, f, usd) in enumerate(ACC, 1):
    if s == "Closed":
        continue
    local = usd / FX[c]
    lag = STALE.get(aid, 0 if f == "API" else (1 if f == "File" else 0))
    v = local
    series = []
    for d in range(10, -1, -1):
        v = v * (1 + R.uniform(-.025, .03)) if t != "Restricted" else v
        series.append((d, v))
    for d, v in series:
        if d < lag:
            continue
        led = round(v, 2)
        balances.append((len(balances) + 1, aid, D(d), led, round(led * (0.97 if t in ("Operating", "Payroll") else 1.0), 2), T(d * 24 + R.randint(1, 7))))

# ------------------------------------------------------------------ ERP: vendors, purchase orders, invoices
vendors = [(1, "Kestrel Components Inc", "United States", "USD", 30), (2, "Rhein Stahlwerke GmbH", "Germany", "EUR", 45), (3, "Vogel Praezisionsteile GmbH", "Germany", "EUR", 30),
           (4, "Albion Packaging Ltd", "United Kingdom", "GBP", 30), (5, "Straits Logistics Pte", "Singapore", "SGD", 21), (6, "Sakura Electronics KK", "Japan", "JPY", 60),
           (7, "Azteca Maquila SA", "Mexico", "MXN", 30), (8, "Northern Plastics Inc", "United States", "USD", 45), (9, "Bavaria Gears GmbH", "Germany", "EUR", 30),
           (10, "Pennine Castings Ltd", "United Kingdom", "GBP", 45), (11, "Lion City Chemicals Pte", "Singapore", "USD", 30), (12, "Kansai Bearings KK", "Japan", "JPY", 45),
           (13, "Sonoran Freight LLC", "United States", "USD", 15), (14, "Tejo Cork Lda", "Portugal", "EUR", 30)]
VCUR = {v[0]: v[3] for v in vendors}
VENT = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 6, 7: 5, 8: 1, 9: 2, 10: 3, 11: 4, 12: 6, 13: 1, 14: 2}
purchase_orders = []
invoices = []


def add_invoice(v, amount, cur, inv_date, status, po=True, ent=None, no=None):
    iid = len(invoices) + 1
    terms = vendors[v - 1][4]
    ponum = None
    if po:
        ponum = "PO-%05d" % (40000 + len(purchase_orders) + 1)
        purchase_orders.append((ponum, v, ent or VENT[v], round(amount * R.uniform(.98, 1.02), 2), cur, "Closed" if status == "Paid" else "Open"))
    invoices.append([iid, v, ent or VENT[v], no or "INV-%d-%04d" % (v, R.randint(1000, 9999)), D(inv_date), D(inv_date - terms), round(amount, 2), cur, status, ponum])
    return iid


for v in range(1, 15):
    for k in range(R.randint(5, 8)):
        amt = R.choice([12e3, 28e3, 46e3, 83e3, 140e3, 265e3, 410e3]) * R.uniform(.7, 1.3) / FX[VCUR[v]]
        age = R.randint(1, 75)
        status = "Paid" if age > 45 else R.choice(["Open", "Open", "Approved", "Paid"])
        add_invoice(v, amt, VCUR[v], age, status)
# traps
add_invoice(3, 188000, "USD", 4, "Open")            # vendor 3 contracted in EUR now invoicing in USD
add_invoice(3, 96500, "USD", 2, "Open")
for v, amt, age in ((7, 61250.00, 6), (9, 77400.00, 9)):  # duplicate invoices: same vendor, amount and date, different numbers
    a = add_invoice(v, amt / FX[VCUR[v]] * FX[VCUR[v]], VCUR[v], age, "Open", po=False)
    add_invoice(v, amt, VCUR[v], age, "Open", po=False)
add_invoice(2, 520000 / FX["EUR"], "EUR", 3, "On hold")
add_invoice(11, 74000, "USD", 5, "On hold")
add_invoice(1, 305000, "USD", 1, "Open", po=False)   # no purchase order
open_status = ("Open", "Approved", "On hold")
for inv in invoices:
    if inv[8] in ("Open", "Approved") and R.random() < .35:
        inv[5] = D(-R.randint(1, 12))       # due within the next two weeks
invoices = [tuple(i) for i in invoices]

# ------------------------------------------------------------------ bank transactions and the ledger
ledger = []
bank_txns = []
for aid, (e, b, c, t, s, f, usd) in enumerate(ACC, 1):
    if s == "Closed":
        continue
    acct_no = accounts[aid - 1][3]
    for k in range(R.randint(7, 11)):
        day = R.randint(0, 13)
        amt = round(R.choice([-1, -1, 1]) * R.choice([4e3, 9e3, 22e3, 51e3, 120e3, 340e3]) * R.uniform(.5, 1.5) / FX[c], 2)
        lid = None
        if R.random() < .88:
            lid = len(ledger) + 1
            rec = not (day <= 3 and R.random() < .5) and R.random() > .08
            ledger.append((lid, e, "1010" if amt > 0 else "2010", D(day), amt, c, acct_no, "Ref %05d" % R.randint(10000, 99999), rec))
        bank_txns.append((len(bank_txns) + 1, aid, D(day), amt, c, R.choice(["Customer receipt", "Supplier payment", "Payroll", "Tax", "Intercompany", "Bank fee", "Sweep"]), lid))
for k in range(14):  # ledger entries the bank has never shown
    aid = R.choice([i for i, a in enumerate(ACC, 1) if a[4] == "Open"])
    c = ACC[aid - 1][2]
    ledger.append((len(ledger) + 1, ACC[aid - 1][0], "2010", D(R.randint(6, 20)), round(-R.choice([8e3, 19e3, 47e3, 95e3]) / FX[c] * R.uniform(.7, 1.3), 2), c,
                   accounts[aid - 1][3], "Ref %05d" % R.randint(10000, 99999), False))

# ------------------------------------------------------------------ payments, policy, audit
policies = [(1, "Standard payments", 50000, 250000)]
payments = []
usd_of = lambda amt, c: round(amt * FX[c], 2)
paid_invoices = [i for i in invoices if i[8] in ("Open", "Approved", "Paid")]
for k in range(34):
    inv = R.choice(paid_invoices)
    amt = inv[6]
    c = inv[7]
    usd = usd_of(amt, c)
    cands = [i for i, a in enumerate(ACC, 1) if a[0] == inv[2] and a[2] == c and a[4] == "Open" and a[3] == "Operating"] or \
            [i for i, a in enumerate(ACC, 1) if a[0] == inv[2] and a[4] == "Open"]
    aid = cands[0]
    if usd <= 50000: st, ap, ap2, by = "Released", "policy-auto", None, "treasury-agent"
    elif usd <= 250000: st, ap, ap2, by = "Released", R.choice(["m.okafor", "j.lindqvist"]), None, R.choice(["treasury-agent", "a.tanaka"])
    else: st, ap, ap2, by = "Released", "m.okafor", "c.dubois", "a.tanaka"
    payments.append([len(payments) + 1, inv[2], aid, inv[0], inv[1], amt, c, usd, D(R.randint(0, 25)), st, by, ap, ap2, 1])
big = [p for p in payments if p[7] > 250000]
if len(big) >= 2:  # released above the dual-approval limit with one approver
    big[0][12] = None
    big[1][12] = None
else:
    for p in payments[:2]:
        p[5] = 410000.0; p[6] = "USD"; p[7] = 410000.0; p[11] = "m.okafor"; p[12] = None
p0 = payments[5]; p0[5] = 129000.0; p0[6] = "USD"; p0[7] = 129000.0; p0[10] = "treasury-agent"; p0[11] = None; p0[12] = None   # agent released above its auto limit
pending = [p for p in payments if p[9] == "Released"][-6:]
for p in pending:
    p[9] = "Pending approval"; p[11] = None; p[12] = None; p[8] = D(-R.randint(0, 3))
hold = [i for i in invoices if i[8] == "On hold"][0]
payments.append([len(payments) + 1, hold[2], [i for i, a in enumerate(ACC, 1) if a[0] == hold[2] and a[4] == "Open"][0], hold[0], hold[1], hold[6], hold[7],
                 usd_of(hold[6], hold[7]), D(-1), "Pending approval", "treasury-agent", None, None, 1])
payments = [tuple(p) for p in payments]
agent_actions = []
acts = ["Matched bank transaction to ledger", "Released payment within limit", "Flagged invoice anomaly", "Proposed hedge", "Held payment", "Reclassified exposure"]
for k in range(34):
    act = R.choice(acts)
    agent_actions.append((k + 1, T(R.randint(1, 24 * 28)), "treasury-agent", act, R.randint(1, 6), None, "%s (automated)" % act, True, "policy-auto"))
rel = [p for p in payments if p[9] == "Released" and p[10] == "treasury-agent"]
bad = [p for p in payments if p[0] == p0[0]]
agent_actions[3] = (4, T(30), "treasury-agent", "Released payment above auto limit", p0[1], p0[0], "Released %.0f USD with no approver" % p0[7], False, None)
agent_actions[11] = (12, T(110), "treasury-agent", "Edited payee bank details", 2, None, "Changed payee account on a vendor record", False, None)
agent_actions[20] = (21, T(260), "treasury-agent", "Released payment within limit", 3, None, "Released after override by a manager", False, "j.lindqvist")
for p in pending[:2]:
    agent_actions.append((len(agent_actions) + 1, T(R.randint(1, 20)), "treasury-agent", "Queued payment for approval", p[1], p[0], "Payment above auto-release limit queued", True, None))
for i, a in enumerate(agent_actions): agent_actions[i] = (i + 1,) + a[1:]

# ------------------------------------------------------------------ hedges, debt, covenants, forecasts
hedges = [(1, 2, "EUR", 1.5e6, 1.0795, D(-25), D(65), 2, "Active"), (2, 2, "EUR", 0.65e6, 1.0840, D(-10), D(20), 2, "Active"),
          (3, 3, "GBP", 0.11e6, 1.2650, D(-40), D(45), 3, "Active"), (4, 4, "SGD", 0.5e6, 0.7380, D(-20), D(75), 4, "Active"),
          (5, 4, "SGD", 0.23e6, 0.7410, D(-5), D(12), 4, "Active"), (6, 6, "JPY", 180e6, 0.00655, D(2), D(70), 5, "Matured"),
          (7, 3, "GBP", 0.8e6, 1.2700, D(5), D(95), 3, "Matured"), (8, 2, "EUR", 1.1e6, 1.0700, D(30), D(120), 2, "Matured")]
facilities = [(1, "Syndicated revolving credit facility", "Revolver", 1, "USD", 200e6, 60e6, D(-900)), (2, "Term loan A", "Term loan", 1, "USD", 150e6, 150e6, D(-1500)),
              (3, "Euro working-capital line", "Revolver", 2, "EUR", 50e6, 0.0, D(-540))]
covenants = [(1, 1, "Net leverage", "Net debt / EBITDA", "Maximum", 3.5, 3.38, D(20)), (2, 1, "Interest cover", "EBITDA / interest", "Minimum", 3.0, 4.10, D(20)),
             (3, 2, "Net leverage", "Net debt / EBITDA", "Maximum", 3.75, 3.38, D(20)), (4, 3, "Minimum liquidity", "Cash + undrawn lines, USD m", "Minimum", 75.0, 214.0, D(20)),
             (5, 2, "Debt service cover", "Cash flow / debt service", "Minimum", 1.2, 1.31, D(20))]
forecasts = []
for e in range(1, 7):
    base = {1: 8e6, 2: 3e6, 3: 2e6, 4: 1.5e6, 5: .9e6, 6: 2.2e6}[e]
    miss = {4: .26, 5: .12}.get(e, .05)
    for w in range(12, 0, -1):
        f = base * R.uniform(.8, 1.2)
        act = f * (1 + R.choice([-1, 1]) * R.uniform(miss * .6, miss * 1.4))
        forecasts.append((len(forecasts) + 1, e, D(w * 7), 7, round(f, 2), round(act, 2)))

# ------------------------------------------------------------------ emit
pg = ["-- Treasury demo pack, Postgres half (accounts, balances, payments, hedges, debt). Invented. Dates are relative to the day this runs.",
      "CREATE SCHEMA treasury;", ""]
S = "treasury."
table(pg, "pg", S, "entities", ["entity_id", "name", "country", "base_currency"], entities, "entity_id INT PRIMARY KEY, name VARCHAR(60), country VARCHAR(30), base_currency CHAR(3)")
table(pg, "pg", S, "banks", ["bank_id", "name", "country"], banks, "bank_id INT PRIMARY KEY, name VARCHAR(60), country VARCHAR(30)")
table(pg, "pg", S, "bank_accounts", ["account_id", "entity_id", "bank_id", "account_no", "currency", "account_type", "status", "feed_method", "opened_on"], accounts,
      "account_id INT PRIMARY KEY, entity_id INT REFERENCES treasury.entities, bank_id INT REFERENCES treasury.banks, account_no VARCHAR(30), currency CHAR(3), account_type VARCHAR(20), status VARCHAR(10), feed_method VARCHAR(10), opened_on DATE")
table(pg, "pg", S, "balances", ["balance_id", "account_id", "as_of_date", "ledger_balance", "available_balance", "received_at"], balances,
      "balance_id INT PRIMARY KEY, account_id INT REFERENCES treasury.bank_accounts, as_of_date DATE, ledger_balance NUMERIC(18,2), available_balance NUMERIC(18,2), received_at TIMESTAMP")
table(pg, "pg", S, "fx_rates", ["fx_rate_id", "currency", "rate_to_usd", "as_of_date"], fx_rates, "fx_rate_id INT PRIMARY KEY, currency CHAR(3), rate_to_usd NUMERIC(12,6), as_of_date DATE")
table(pg, "pg", S, "bank_transactions", ["txn_id", "account_id", "booking_date", "amount", "currency", "description", "matched_ledger_id"], bank_txns,
      "txn_id INT PRIMARY KEY, account_id INT REFERENCES treasury.bank_accounts, booking_date DATE, amount NUMERIC(18,2), currency CHAR(3), description VARCHAR(40), matched_ledger_id INT")
table(pg, "pg", S, "payment_policies", ["policy_id", "name", "auto_release_limit_usd", "dual_approval_above_usd"], policies,
      "policy_id INT PRIMARY KEY, name VARCHAR(40), auto_release_limit_usd NUMERIC(14,2), dual_approval_above_usd NUMERIC(14,2)")
table(pg, "pg", S, "payments", ["payment_id", "entity_id", "account_id", "invoice_id", "vendor_id", "amount", "currency", "amount_usd", "value_date", "status", "initiated_by", "approved_by", "second_approver", "policy_id"], payments,
      "payment_id INT PRIMARY KEY, entity_id INT REFERENCES treasury.entities, account_id INT REFERENCES treasury.bank_accounts, invoice_id INT, vendor_id INT, amount NUMERIC(18,2), currency CHAR(3), amount_usd NUMERIC(18,2), value_date DATE, status VARCHAR(20), initiated_by VARCHAR(30), approved_by VARCHAR(30), second_approver VARCHAR(30), policy_id INT REFERENCES treasury.payment_policies")
table(pg, "pg", S, "agent_actions", ["action_id", "occurred_at", "actor", "action_type", "entity_id", "payment_id", "detail", "within_policy", "approved_by"], agent_actions,
      "action_id INT PRIMARY KEY, occurred_at TIMESTAMP, actor VARCHAR(30), action_type VARCHAR(50), entity_id INT REFERENCES treasury.entities, payment_id INT, detail VARCHAR(120), within_policy BOOLEAN, approved_by VARCHAR(30)")
table(pg, "pg", S, "hedges", ["hedge_id", "entity_id", "currency", "notional", "rate", "maturity_date", "trade_date", "bank_id", "status"], hedges,
      "hedge_id INT PRIMARY KEY, entity_id INT REFERENCES treasury.entities, currency CHAR(3), notional NUMERIC(18,2), rate NUMERIC(12,6), maturity_date DATE, trade_date DATE, bank_id INT REFERENCES treasury.banks, status VARCHAR(10)")
table(pg, "pg", S, "debt_facilities", ["facility_id", "name", "facility_type", "entity_id", "currency", "commitment", "drawn", "maturity_date"], facilities,
      "facility_id INT PRIMARY KEY, name VARCHAR(60), facility_type VARCHAR(20), entity_id INT REFERENCES treasury.entities, currency CHAR(3), commitment NUMERIC(18,2), drawn NUMERIC(18,2), maturity_date DATE")
table(pg, "pg", S, "covenants", ["covenant_id", "facility_id", "name", "measure", "test_type", "threshold", "current_value", "tested_on"], covenants,
      "covenant_id INT PRIMARY KEY, facility_id INT REFERENCES treasury.debt_facilities, name VARCHAR(40), measure VARCHAR(60), test_type VARCHAR(10), threshold NUMERIC(10,3), current_value NUMERIC(10,3), tested_on DATE")
table(pg, "pg", S, "cash_forecasts", ["forecast_id", "entity_id", "week_start", "horizon_days", "forecast_net_cash_usd", "actual_net_cash_usd"], forecasts,
      "forecast_id INT PRIMARY KEY, entity_id INT REFERENCES treasury.entities, week_start DATE, horizon_days INT, forecast_net_cash_usd NUMERIC(18,2), actual_net_cash_usd NUMERIC(18,2)")
pg.append("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omnigate_ro') THEN CREATE ROLE omnigate_ro LOGIN PASSWORD 'omnigate_ro'; END IF; END $$;\n"
          "GRANT CONNECT ON DATABASE postgres TO omnigate_ro;\nGRANT USAGE ON SCHEMA treasury TO omnigate_ro;\nGRANT SELECT ON ALL TABLES IN SCHEMA treasury TO omnigate_ro;")


def erp(out, dialect, schema):
    table(out, dialect, schema, "vendors", ["vendor_id", "name", "country", "contract_currency", "payment_terms_days"], vendors,
          "vendor_id INT PRIMARY KEY, name VARCHAR(60), country VARCHAR(30), contract_currency CHAR(3), payment_terms_days INT")
    table(out, dialect, schema, "purchase_orders", ["po_number", "vendor_id", "entity_id", "amount", "currency", "status"], purchase_orders,
          "po_number VARCHAR(12) PRIMARY KEY, vendor_id INT, entity_id INT, amount DECIMAL(18,2), currency CHAR(3), status VARCHAR(10)")
    table(out, dialect, schema, "invoices", ["invoice_id", "vendor_id", "entity_id", "invoice_no", "invoice_date", "due_date", "amount", "currency", "status", "po_number"], invoices,
          "invoice_id INT PRIMARY KEY, vendor_id INT, entity_id INT, invoice_no VARCHAR(30), invoice_date DATE, due_date DATE, amount DECIMAL(18,2), currency CHAR(3), status VARCHAR(10), po_number VARCHAR(12)")
    table(out, dialect, schema, "ledger_entries", ["entry_id", "entity_id", "gl_account", "posting_date", "amount", "currency", "bank_account_no", "reference", "reconciled"], ledger,
          "entry_id INT PRIMARY KEY, entity_id INT, gl_account VARCHAR(10), posting_date DATE, amount DECIMAL(18,2), currency CHAR(3), bank_account_no VARCHAR(30), reference VARCHAR(20), reconciled BOOLEAN")


my = ["-- Treasury demo pack, MariaDB half (the ERP: vendors, purchase orders, invoices, general-ledger cash entries). Invented.",
      "-- Dates are relative to the day this runs (CURDATE()). Registered under the database name \"erp\".", "CREATE DATABASE IF NOT EXISTS erp;", "USE erp;", ""]
erp(my, "maria", "")
open(os.path.join(HERE, "seed-treasury-postgres.sql"), "w").write("\n".join(pg) + "\n")
open(os.path.join(HERE, "seed-treasury-mariadb.sql"), "w").write("\n".join(my) + "\n")
if "--verify" in sys.argv:
    v = list(pg[:-1]) + ["CREATE SCHEMA erp;", ""]
    erp(v, "pg", "erp.")
    open(os.path.join(HERE, "seed-treasury-verify.sql"), "w").write("\n".join(v) + "\n")
print("accounts %d balances %d txns %d ledger %d invoices %d payments %d" % (len(accounts), len(balances), len(bank_txns), len(ledger), len(invoices), len(payments)))
