"""Fetch and parse one feed (RSS 2.0, RSS 1.0 / RDF, Atom). Standard library only. It stores nothing: it returns items with a headline, a link, a date and a SHORT description that the caller reads
to match on and then drops. Polite by construction: robots.txt is honoured (4xx = no rules, 5xx or unreachable = do not fetch), a request is conditional (ETag / Last-Modified), responses are size-capped,
a document type declaration is refused (no entity expansion), and a host is not hit faster than once a second (or its crawl delay, up to a minute)."""
import datetime as dt, email.utils, gzip, hashlib, html, io, re, time, urllib.error, urllib.parse, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET

AGENT = "ThinkingSenseFeedReader"
UA = AGENT + "/0.1 (+https://thinkingsense.ai)"
MAX_BYTES = 3_000_000
MAX_ITEMS = 200
TIMEOUT = 20
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|oly_|_hs)", re.I)


def canonical_url(u):
    """Same article, same address: lower-case scheme and host, no fragment, no tracking parameters, no trailing slash."""
    p = urllib.parse.urlsplit((u or "").strip())
    if p.scheme not in ("http", "https") or not p.netloc: return ""
    q = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)])
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", q, ""))


def clean_text(s, cap):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:cap]


def seen_hash(source_id, url, title):
    """One hash per article: its canonical address, or (without one) the source and headline. The same address read from two feeds is one item."""
    key = url if url else "%s|%s" % (source_id, re.sub(r"\W+", " ", title.lower()).strip())
    return hashlib.sha256(key.encode()).hexdigest()


def parse_date(s, now=None):
    """A UTC naive datetime, or None. A date more than a day in the future is wrong (one status feed was dated a month ahead), so it is treated as unknown."""
    s = (s or "").strip()
    if not s: return None
    d = None
    try: d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try: d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError: return None
    if d.tzinfo: d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return None if d > now + dt.timedelta(days=1) else d


def _local(tag): return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
def _child(el, *names):
    for c in el:
        if _local(c.tag) in names: return c
    return None
def _text(el, *names):
    c = _child(el, *names)
    return (c.text or "").strip() if c is not None else ""


def parse(body, now=None):
    """Items as dicts {title, url, published, description}. Refuses a document with a type declaration or entities (they can expand without bound)."""
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in body[:65536].lower(): raise ValueError("a feed with a document type declaration or entities is refused")
    try: root = ET.fromstring(body)
    except ET.ParseError as e: raise ValueError("not well-formed XML: %s" % e)
    kind = _local(root.tag)
    if kind == "rss":
        ch = _child(root, "channel"); nodes = [c for c in (ch if ch is not None else []) if _local(c.tag) == "item"]
    elif kind == "feed": nodes = [c for c in root if _local(c.tag) == "entry"]
    elif kind == "RDF": nodes = [c for c in root if _local(c.tag) == "item"]
    else: raise ValueError("not an RSS or Atom feed (root element %r)" % kind)
    out = []
    for n in nodes[:MAX_ITEMS]:
        title = clean_text(_text(n, "title"), 250)
        link = ""
        if kind == "feed":
            ls = [c for c in n if _local(c.tag) == "link"]
            pick = next((c for c in ls if c.get("rel", "alternate") == "alternate"), ls[0] if ls else None)
            link = pick.get("href", "") if pick is not None else ""
        else: link = _text(n, "link")
        if not link:
            g = _child(n, "guid", "id"); gt = (g.text or "").strip() if g is not None else ""
            link = gt if gt.startswith("http") else ""
        url = canonical_url(link)[:500]
        if not title: continue
        out.append({"title": title, "url": url, "published": parse_date(_text(n, "pubDate", "published", "updated", "date"), now),
                    "description": clean_text(_text(n, "description", "summary", "content", "encoded"), 600)})
    return out


class Fetcher:
    """One place for network access, so tests replace it. `get(url, headers)` returns (status, headers, body)."""
    def __init__(self, sleep=time.sleep, clock=time.monotonic):
        self.sleep, self.clock = sleep, clock; self.last = {}; self.robots = {}

    def get(self, url, headers=None):
        req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"}, **(headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read(MAX_BYTES + 1); h = {k.lower(): v for k, v in r.headers.items()}
                if h.get("content-encoding") == "gzip": raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES: raise ValueError("response larger than %d bytes" % MAX_BYTES)
                return r.status, h, raw
        except urllib.error.HTTPError as e: return e.code, {k.lower(): v for k, v in e.headers.items()}, b""

    def _robots(self, url):
        p = urllib.parse.urlsplit(url); base = "%s://%s" % (p.scheme, p.netloc)
        hit = self.robots.get(base)
        if hit and self.clock() - hit[0] < 86400: return hit[1]
        rp = urllib.robotparser.RobotFileParser()
        try: status, _, body = self.get(base + "/robots.txt")
        except Exception: return None                                   # unreachable: do not fetch this round
        if status >= 500: return None
        if status >= 400: rp.parse([])                                 # no robots file: no rules
        else: rp.parse(body.decode("utf-8", "replace").splitlines())
        self.robots[base] = (self.clock(), rp); return rp

    def fetch(self, url, etag=None, last_modified=None):
        """-> {status: ok|not_modified|blocked_by_robots|http_error|unreachable|parse_error, items, etag, last_modified, error}."""
        rp = self._robots(url)
        if rp is None: return {"status": "unreachable", "error": "robots.txt could not be read", "items": []}
        if not rp.can_fetch(AGENT, url): return {"status": "blocked_by_robots", "error": "robots.txt does not allow this feed", "items": []}
        host = urllib.parse.urlsplit(url).netloc
        wait = min(max(1.0, float(rp.crawl_delay(AGENT) or 0)), 60.0) - (self.clock() - self.last.get(host, -1e9))
        if wait > 0: self.sleep(wait)
        self.last[host] = self.clock()
        h = {}
        if etag: h["If-None-Match"] = etag
        if last_modified: h["If-Modified-Since"] = last_modified
        try: status, rh, body = self.get(url, h)
        except Exception as e: return {"status": "unreachable", "error": str(e)[:200], "items": []}
        if status == 304: return {"status": "not_modified", "items": [], "etag": etag, "last_modified": last_modified}
        if status != 200: return {"status": "http_error", "error": "HTTP %d" % status, "items": []}
        try: items = parse(body)
        except ValueError as e: return {"status": "parse_error", "error": str(e)[:200], "items": []}
        return {"status": "ok", "items": items, "etag": rh.get("etag"), "last_modified": rh.get("last-modified")}
