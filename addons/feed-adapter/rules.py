"""The rule-based filter and the clustering for the Watch feed (docs/agency-it-risk-flow.md, section 5.3). Pure functions, no I/O, so a risk partner can read and challenge each rule.
The terms below are DEMO RULES for Leo's review, not a measured classifier: how well they catch and miss real stories is what the pilot (build step 8) is for.
A model may later propose, the rules gate decides; none is used here."""
import re

CLAIMED, CONFIRMED, ADJACENT = "ai-attack-claimed", "ai-attack-confirmed", "ai-adjacent"
RANK = {CONFIRMED: 3, CLAIMED: 2, ADJACENT: 1}

AI_WORDS = re.compile(r"\bA\.I\.|artificial intelligence|\bLLMs?\b|machine learning|\bagentic\b|\bgenerative\b|deepfake|chatgpt|\bopenai\b|\banthropic\b|\bclaude\b|\bcopilot\b|\bgemini\b|autonomous agents?", re.I)
AI_BARE = re.compile(r"\bAI\b")                                  # "AI" alone is matched capitalised only, so it is not the "ai" in a name or a word


ATTACK = re.compile(r"\battack|\bcyber-?attack|\bhack|\bransomware|\bintrusion|\bcompromis|\bthreat actor|\bespionage|\bexploited\b|\bsabotage", re.I)
INCIDENT = re.compile(r"\boutages?\b|\bdisrupt|\bwent down\b|\bgoes down\b|\bground stop|\bdowntime\b|\bbreach|\bincident\b|\bshutdown\b|\bhalted\b|\bparaly[sz]|\boffline\b|\btaken down\b", re.I)
WEAKNESS = re.compile(r"\bvulnerabilit|\bpatch|\bflaw|\bzero-?day|\bbug\b|\bexploit\b|\bglitch", re.I)


ROUNDUP = re.compile(r"this month in security|\bin other news\b|feedback friday|week in review|weekly (?:roundup|digest|recap)|newsletter|\bpodcast\b|\bwebinar\b|\bwhat we missed\b|\bedition\b", re.I)    # digests and promotions list many stories at once: none is one incident


def has_ai(text): return bool(AI_WORDS.search(text) or AI_BARE.search(text))


def classify(title, description, kind):
    """-> (matched, claim_type or None, terms). A context feed never matches: it is reading, not a lead. A candidate needs AI plus an incident or a weakness; a CLAIM that AI attacked
    needs AI plus an attack plus an incident (so a general 'AI-powered attacks are rising' piece is not a candidate). Reporting says claimed; an official source says confirmed."""
    if kind == "context": return False, None, ""
    if ROUNDUP.search(title or ""): return False, None, ""
    text = "%s. %s" % (title, description or "")
    if not has_ai(text): return False, None, ""
    atk, inc, weak = bool(ATTACK.search(text)), bool(INCIDENT.search(text)), bool(WEAKNESS.search(text))
    terms = "; ".join(x for x in ("ai", "attack" if atk else "", "incident" if inc else "", "weakness" if weak else "") if x)
    if atk and inc: return True, (CONFIRMED if kind == "official" else CLAIMED), terms
    if inc or weak: return True, ADJACENT, terms
    return False, None, ""


MONTHS = "january february march april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday".split()
STOP = set(MONTHS) | set("""the this that these those how why what when where who which new now after before with from over into about report reports hackers hacker attack attacks cyber cyberattack cyberattacks security
data breach outage outages ai using used says say said could will just more most inside behind amid here your their are can has have not but and for its our one two three artificial intelligence agent agents agentic model models
cloud vulnerability vulnerabilities zero critical warns warning flaw flaws bug bugs patch patches update updates attackers threat threats malware ransomware researchers expert experts first latest week day""".split())


def entities(title):
    """The names in a headline: capitalised or all-caps words that are not common words, lower-cased. Two headlines about the same incident usually share one (Microsoft, FAA, Chase)."""
    toks = re.findall(r"\b[A-Z][A-Za-z0-9&-]{2,}\b", title or "")
    return {t.lower() for t in toks if t.lower() not in STOP}


def cluster(rows, window_close_hours=48, window_wide_days=7):
    """Groups matched items into candidates. Items share a candidate when they are within two days and share one name, or within a week and share two. An item already in a candidate keeps it;
    two different existing candidates are never merged (one may already be traced). rows: {item_id, title, when (datetime), claim_type, candidate_id or None, source (name)}. Returns a list of groups
    {candidate_id, item_ids, title, claim_type, first_seen (date), summary}."""
    rows = sorted(rows, key=lambda r: (r["when"], r["item_id"]))
    parent = {r["item_id"]: r["item_id"] for r in rows}; cid = {r["item_id"]: r.get("candidate_id") for r in rows}
    ents = {r["item_id"]: entities(r["title"]) for r in rows}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb: return
        ca, cb = cid[ra], cid[rb]
        if ca is not None and cb is not None and ca != cb: return
        parent[rb] = ra; cid[ra] = ca if ca is not None else cb
    for i, a in enumerate(rows):
        if a.get("candidate_id") is not None:
            for b in rows[:i]:
                if b.get("candidate_id") == a["candidate_id"]: union(b["item_id"], a["item_id"])
    for i, a in enumerate(rows):
        for b in rows[:i]:
            gap = (a["when"] - b["when"]).total_seconds()
            share = len(ents[a["item_id"]] & ents[b["item_id"]])
            if (share >= 1 and gap <= window_close_hours * 3600) or (share >= 2 and gap <= window_wide_days * 86400): union(b["item_id"], a["item_id"])
    groups = {}
    for r in rows: groups.setdefault(find(r["item_id"]), []).append(r)
    out = []
    for g in groups.values():
        lead = g[0]; srcs = sorted({r["source"] for r in g})
        out.append({"candidate_id": next((r["candidate_id"] for r in g if r.get("candidate_id") is not None), None), "item_ids": [r["item_id"] for r in g], "lead_item_id": lead["item_id"],
                    "title": lead["title"][:120], "claim_type": max((r["claim_type"] for r in g), key=lambda t: RANK.get(t, 0)), "first_seen": lead["when"].date().isoformat(),
                    "summary": ("%d headline%s from %s." % (len(g), "" if len(g) == 1 else "s", ", ".join(srcs)))[:300]})
    return out
