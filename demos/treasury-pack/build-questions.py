#!/usr/bin/env python3
"""Writes demo-questions-treasury.json (approved question bank) and probe-questions-treasury.json.
Tables are schema.table: treasury.* (Postgres) and erp.* (MariaDB)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
# the latest balance of every account that is not closed, converted to USD
LATEST = """(SELECT a.account_id, a.entity_id, a.bank_id, a.currency, a.account_type, a.status, a.feed_method, b.as_of_date, b.ledger_balance,
        b.ledger_balance * r.rate_to_usd AS usd
     FROM treasury.bank_accounts a
     JOIN (SELECT account_id, MAX(as_of_date) AS d FROM treasury.balances GROUP BY account_id) l ON l.account_id = a.account_id
     JOIN treasury.balances b ON b.account_id = l.account_id AND b.as_of_date = l.d
     JOIN treasury.fx_rates r ON r.currency = a.currency)"""
OPEN_INV = "i.status IN ('Open', 'Approved', 'On hold')"

Q = [
 ("What is our consolidated cash position in US dollars across all open accounts?",
  f"SELECT COUNT(*) AS accounts, ROUND(SUM(usd), 0) AS total_usd FROM {LATEST} x WHERE status = 'Open'"),
 ("How much cash do we hold in each currency, in the local currency and in US dollars?",
  f"SELECT currency, ROUND(SUM(ledger_balance), 0) AS local_amount, ROUND(SUM(usd), 0) AS usd_amount FROM {LATEST} x WHERE status = 'Open' GROUP BY currency ORDER BY usd_amount DESC"),
 ("What is the cash position of each legal entity in US dollars?",
  f"SELECT e.name AS entity, ROUND(SUM(x.usd), 0) AS usd_amount FROM {LATEST} x JOIN treasury.entities e ON e.entity_id = x.entity_id WHERE x.status = 'Open' GROUP BY e.name ORDER BY usd_amount DESC"),
 ("How much cash is held at each bank, and what share of the total is that?",
  f"SELECT bk.name AS bank, ROUND(SUM(x.usd), 0) AS usd_amount, ROUND(100.0 * SUM(x.usd) / (SELECT SUM(usd) FROM {LATEST} y WHERE y.status = 'Open'), 1) AS share_pct FROM {LATEST} x JOIN treasury.banks bk ON bk.bank_id = x.bank_id WHERE x.status = 'Open' GROUP BY bk.name ORDER BY usd_amount DESC"),
 ("Which accounts have a balance that is more than a day old?",
  "SELECT a.account_no, a.currency, a.feed_method, a.status, MAX(b.as_of_date) AS latest_balance FROM treasury.bank_accounts a JOIN treasury.balances b ON b.account_id = a.account_id GROUP BY a.account_no, a.currency, a.feed_method, a.status HAVING MAX(b.as_of_date) < CURRENT_DATE - INTERVAL '1' DAY ORDER BY latest_balance, a.account_no"),
 ("How much cash is trapped in frozen or restricted accounts, in US dollars?",
  f"SELECT x.account_type, x.status, x.currency, ROUND(x.ledger_balance, 0) AS local_amount, ROUND(x.usd, 0) AS usd_amount FROM {LATEST} x WHERE x.status = 'Frozen' OR x.account_type = 'Restricted'"),
 ("How many open accounts are fed by API, file and portal?",
  "SELECT feed_method, COUNT(*) AS accounts FROM treasury.bank_accounts WHERE status <> 'Closed' GROUP BY feed_method ORDER BY accounts DESC"),
 ("Which ledger entries have been waiting more than 5 days to be reconciled, by entity?",
  "SELECT e.name AS entity, COUNT(*) AS entries, MIN(l.posting_date) AS oldest FROM erp.ledger_entries l JOIN treasury.entities e ON e.entity_id = l.entity_id WHERE l.reconciled = FALSE AND l.posting_date < CURRENT_DATE - INTERVAL '5' DAY GROUP BY e.name ORDER BY entries DESC"),
 ("Which bank transactions in the last 14 days have no matching ledger entry, by account?",
  "SELECT a.account_no, a.currency, COUNT(*) AS unmatched, ROUND(SUM(ABS(t.amount)), 0) AS gross_amount FROM treasury.bank_transactions t JOIN treasury.bank_accounts a ON a.account_id = t.account_id WHERE t.matched_ledger_id IS NULL AND t.booking_date >= CURRENT_DATE - INTERVAL '14' DAY GROUP BY a.account_no, a.currency ORDER BY unmatched DESC, a.account_no"),
 ("How many ledger entries are still unreconciled even though the bank has already booked the transaction, by entity?",
  "SELECT e.name AS entity, COUNT(*) AS entries FROM treasury.bank_transactions t JOIN erp.ledger_entries l ON l.entry_id = t.matched_ledger_id JOIN treasury.entities e ON e.entity_id = l.entity_id WHERE l.reconciled = FALSE GROUP BY e.name ORDER BY entries DESC, e.name"),
 ("What invoices fall due in the next 14 days, by currency?",
  f"SELECT i.currency, COUNT(*) AS invoices, ROUND(SUM(i.amount), 0) AS amount FROM erp.invoices i WHERE {OPEN_INV} AND i.due_date >= CURRENT_DATE AND i.due_date <= CURRENT_DATE + INTERVAL '14' DAY GROUP BY i.currency ORDER BY amount DESC"),
 ("Which invoices are in a different currency from the one in the vendor's contract?",
  "SELECT v.name AS vendor, v.contract_currency, i.invoice_no, i.currency AS invoiced_in, i.amount, i.invoice_date FROM erp.invoices i JOIN erp.vendors v ON v.vendor_id = i.vendor_id WHERE i.currency <> v.contract_currency ORDER BY v.name, i.invoice_date"),
 ("Are there possible duplicate invoices, with the same vendor, amount and date?",
  "SELECT v.name AS vendor, i.amount, i.currency, i.invoice_date, COUNT(*) AS invoices FROM erp.invoices i JOIN erp.vendors v ON v.vendor_id = i.vendor_id GROUP BY v.name, i.amount, i.currency, i.invoice_date HAVING COUNT(*) > 1 ORDER BY v.name"),
 ("Which open or approved invoices have no purchase order?",
  "SELECT v.name AS vendor, i.invoice_no, i.amount, i.currency, i.invoice_date FROM erp.invoices i JOIN erp.vendors v ON v.vendor_id = i.vendor_id WHERE i.po_number IS NULL AND i.status IN ('Open', 'Approved') ORDER BY i.invoice_date DESC"),
 ("Which payments are waiting for approval, and how much is each in US dollars?",
  "SELECT p.payment_id, e.name AS entity, p.amount, p.currency, p.amount_usd, p.value_date, p.initiated_by FROM treasury.payments p JOIN treasury.entities e ON e.entity_id = p.entity_id WHERE p.status = 'Pending approval' ORDER BY p.amount_usd DESC"),
 ("Which released payments were above the dual-approval limit without a second approver?",
  "SELECT p.payment_id, e.name AS entity, p.amount_usd, p.approved_by, p.second_approver, p.value_date FROM treasury.payments p JOIN treasury.entities e ON e.entity_id = p.entity_id JOIN treasury.payment_policies pol ON pol.policy_id = p.policy_id WHERE p.status = 'Released' AND p.amount_usd > pol.dual_approval_above_usd AND p.second_approver IS NULL ORDER BY p.amount_usd DESC"),
 ("What did the treasury agent do outside policy in the last 30 days?",
  "SELECT a.occurred_at, a.action_type, a.detail, a.approved_by FROM treasury.agent_actions a WHERE a.within_policy = FALSE AND a.occurred_at >= CURRENT_TIMESTAMP - INTERVAL '30' DAY ORDER BY a.occurred_at DESC"),
 ("Which payments waiting for approval are for invoices that are on hold?",
  "SELECT p.payment_id, v.name AS vendor, i.invoice_no, p.amount_usd FROM treasury.payments p JOIN erp.invoices i ON i.invoice_id = p.invoice_id JOIN erp.vendors v ON v.vendor_id = i.vendor_id WHERE p.status = 'Pending approval' AND i.status = 'On hold' ORDER BY p.amount_usd DESC"),
 ("For each foreign currency, how much of our open payables is covered by active hedges?",
  f"SELECT pay.currency, pay.payable, COALESCE(h.hedged, 0) AS hedged, ROUND(100.0 * COALESCE(h.hedged, 0) / pay.payable, 0) AS coverage_pct FROM (SELECT i.currency, SUM(i.amount) AS payable FROM erp.invoices i WHERE {OPEN_INV} AND i.currency <> 'USD' GROUP BY i.currency) pay LEFT JOIN (SELECT currency, SUM(notional) AS hedged FROM treasury.hedges WHERE status = 'Active' GROUP BY currency) h ON h.currency = pay.currency ORDER BY coverage_pct, pay.currency"),
 ("Which hedges mature in the next 30 days?",
  "SELECT h.hedge_id, e.name AS entity, h.currency, h.notional, h.rate, h.maturity_date, bk.name AS bank FROM treasury.hedges h JOIN treasury.entities e ON e.entity_id = h.entity_id JOIN treasury.banks bk ON bk.bank_id = h.bank_id WHERE h.status = 'Active' AND h.maturity_date >= CURRENT_DATE AND h.maturity_date <= CURRENT_DATE + INTERVAL '30' DAY ORDER BY h.maturity_date"),
 ("How much headroom does each covenant have, tightest first?",
  "SELECT f.name AS facility, c.name AS covenant, c.test_type, c.threshold, c.current_value, ROUND(100.0 * CASE WHEN c.test_type = 'Maximum' THEN c.threshold - c.current_value ELSE c.current_value - c.threshold END / c.threshold, 1) AS headroom_pct FROM treasury.covenants c JOIN treasury.debt_facilities f ON f.facility_id = c.facility_id ORDER BY headroom_pct, c.covenant_id"),
 ("What is our total liquidity: cash in open accounts plus undrawn revolving credit, in US dollars?",
  f"SELECT ROUND((SELECT SUM(usd) FROM {LATEST} x WHERE x.status = 'Open'), 0) AS cash_usd, ROUND((SELECT SUM((f.commitment - f.drawn) * r.rate_to_usd) FROM treasury.debt_facilities f JOIN treasury.fx_rates r ON r.currency = f.currency WHERE f.facility_type = 'Revolver'), 0) AS undrawn_revolver_usd"),
 ("How accurate were the weekly cash forecasts for each entity over the last 12 weeks?",
  "SELECT e.name AS entity, ROUND(100.0 * AVG(ABS(f.actual_net_cash_usd - f.forecast_net_cash_usd) / f.forecast_net_cash_usd), 1) AS avg_error_pct FROM treasury.cash_forecasts f JOIN treasury.entities e ON e.entity_id = f.entity_id GROUP BY e.name ORDER BY avg_error_pct DESC"),
 ("Which entities' forecasts have missed by more than 15% on average?",
  "SELECT e.name AS entity, ROUND(100.0 * AVG(ABS(f.actual_net_cash_usd - f.forecast_net_cash_usd) / f.forecast_net_cash_usd), 1) AS avg_error_pct FROM treasury.cash_forecasts f JOIN treasury.entities e ON e.entity_id = f.entity_id GROUP BY e.name HAVING AVG(ABS(f.actual_net_cash_usd - f.forecast_net_cash_usd) / f.forecast_net_cash_usd) > 0.15 ORDER BY avg_error_pct DESC"),
]
CAT = "treasury"
json.dump([{"question": q, "referenceSql": s, "category": CAT} for q, s in Q], open(os.path.join(HERE, "demo-questions-treasury.json"), "w"), indent=1)
PARA = [(1, "What's our total cash in USD?"), (2, "Break cash down by currency"), (5, "Which bank feeds have gone stale?"), (8, "Which entities have old unreconciled ledger entries?"),
        (12, "Any invoices where the supplier switched currency?"), (13, "Show me duplicate invoices"), (16, "Who approved payments above the dual-approval threshold with only one signature?"),
        (17, "List the agent's out-of-policy actions this month"), (19, "How well hedged are we against each currency's payables?"), (21, "Which covenant is closest to breaching?"),
        (22, "How much liquidity do we have including undrawn lines?"), (24, "Which entity's cash forecast is least reliable?")]
json.dump({"reworded": [{"question": t, "sameAs": Q[i - 1][0]} for i, t in PARA],
           "shouldDecline": [{"question": "Will we breach a debt covenant in the next 60 days?", "why": "needs a simulation"},
                             {"question": "Should we draw down the revolving credit facility?", "why": "a decision, not a lookup"},
                             {"question": "What is the optimal hedge ratio for the euro?", "why": "needs a model and a policy view"},
                             {"question": "What is the credit rating of Atlantic National Bank?", "why": "no such data"}]},
          open(os.path.join(HERE, "probe-questions-treasury.json"), "w"), indent=1)
print(len(Q), "questions")
