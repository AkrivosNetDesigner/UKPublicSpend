"""Find the current file for a GOV.UK statistics release through the GOV.UK content API.

Many releases are republished every month, quarter or year under a new file address. Instead of hard-coding the address,
sources can name the page and the attachment title, and the pipeline looks the current link up (falling back to the last
downloaded copy if the lookup fails).
"""
import re

API = "https://www.gov.uk/api/content"


def attachments(doc):
    return [(a.get("title") or "", a.get("url") or "") for a in (doc.get("details") or {}).get("attachments", []) if a.get("url", "").startswith("http")]


def pick(doc, pattern, newest_by=None):
    """First attachment whose title matches `pattern`; with `newest_by`, a function title -> sortable key, the highest wins."""
    hits = [(t, u) for t, u in attachments(doc) if re.search(pattern, t, re.I)]
    if not hits:
        raise LookupError(f"no attachment matching {pattern!r} on {doc.get('title')!r}")
    if newest_by:
        hits.sort(key=lambda h: newest_by(h[0]))
        return hits[-1][1]
    return hits[0][1]


def latest_document(collection_doc, title_pattern):
    """base_path of the first (newest) document in a collection whose title matches."""
    for d in (collection_doc.get("links") or {}).get("documents", []):
        if re.search(title_pattern, d.get("title", ""), re.I):
            return d["base_path"]
    raise LookupError(f"no document matching {title_pattern!r} in collection")


def fy_key(title):
    """'... financial year 2024-25 ...' -> 2024"""
    m = re.search(r"(\d{4})-(\d{2})", title)
    return int(m.group(1)) if m else 0
