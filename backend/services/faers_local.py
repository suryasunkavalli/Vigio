"""
Local FAERS lookup against the SQLite snapshot built by tools/build_faers_db.py.

The Population lens uses this first; openFDA is the fallback when the database is missing
or the drug is not found. The snapshot is deduplicated (latest case version only) and counts
suspect drugs only, so its figures are more reliable than raw openFDA counts.
"""

import os
import re
import sqlite3
import logging
from functools import lru_cache
from pathlib import Path

from backend.services.faers_normalize import drug_query_candidates, normalize_event, normalize_ingredient

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "faers.db"
OUTCOME_LABELS = {"DE": "Death", "LT": "Life-threatening", "HO": "Hospitalization", "DS": "Disability",
                  "CA": "Congenital anomaly", "RI": "Required intervention", "OT": "Other serious"}


def db_path() -> Path:
    return Path(os.getenv("FAERS_DB_PATH", str(DEFAULT_DB)))


@lru_cache(maxsize=1)
def _connect(path: str):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def available() -> bool:
    return db_path().exists()


def _q(sql: str, *args):
    return _connect(str(db_path())).execute(sql, args).fetchall()


@lru_cache(maxsize=1)
def meta() -> dict:
    return {r["key"]: r["value"] for r in _q("SELECT key, value FROM meta")}


def match_drug(text: str) -> tuple[str | None, str]:
    """Map free-text drug to an ingredient in the snapshot. Returns (ingredient, how it matched)."""
    for cand in drug_query_candidates(text):
        if _q("SELECT 1 FROM drug_counts WHERE ingredient = ?", cand):
            return cand, f"ingredient '{cand}'"
        row = _q("SELECT ingredient FROM drug_name_map WHERE name = ?", cand)
        if row:
            return row[0]["ingredient"], f"product name '{cand}' -> ingredient '{row[0]['ingredient']}'"
    return None, "not found in snapshot"


@lru_cache(maxsize=1)
def _all_pts() -> list[tuple[str, frozenset, int]]:
    return [(r["pt"], frozenset(r["pt"].split()), r["n"]) for r in _q("SELECT pt, n FROM event_counts")]


def _match_one(norm: str, ingredient: str | None) -> tuple[str | None, str, list[str]]:
    if not norm:
        return None, "", []
    if _q("SELECT 1 FROM event_counts WHERE pt = ?", norm):
        return norm, "exact MedDRA PT", []
    words = frozenset(norm.split())
    same = [pt for pt, w, _ in _all_pts() if w == words]
    if same:
        return same[0], "same words as MedDRA PT", []
    contained = [(pt, len(w), n) for pt, w, n in _all_pts() if w and w <= words]
    if not contained:
        return None, "", []
    with_drug = set()
    if ingredient:
        with_drug = {r["pt"] for r in _q(
            f"SELECT pt FROM drug_event_counts WHERE ingredient = ? AND pt IN ({','.join('?' * len(contained))})",
            ingredient, *[c[0] for c in contained])}
    # most specific PT first (most words), then PTs reported with this drug, then most reported
    contained.sort(key=lambda c: (c[1], c[0] in with_drug, c[2]), reverse=True)
    return contained[0][0], "closest MedDRA PT within the reported term (reviewer to confirm)", [c[0] for c in contained[1:4]]


def match_event(text: str, ingredient: str | None = None) -> tuple[str | None, str, list[str]]:
    """
    Map a free-text event to a MedDRA preferred term present in the snapshot.
    Compound descriptions ('myocarditis with cardiogenic shock') are split, and the first
    (primary) event is matched first. Per part: exact -> same words in any order ->
    most specific PT whose words all appear in the text.
    Returns (pt, how it matched, other candidate PTs for the reviewer).
    """
    norm = normalize_event(text)
    if not norm:
        return None, "no event term", []
    parts = [p.strip() for p in re.split(r"\bWITH\b|\bAND\b|\bFOLLOWING\b|\bSECONDARY TO\b|,|;", norm) if p.strip()]
    found = None
    others = []
    for part in parts or [norm]:
        pt, how, alts = _match_one(part, ingredient)
        if pt and not found:
            found = (pt, how, alts)
        elif pt:
            others.append(pt)
    if found:
        pt, how, alts = found
        if len(parts) > 1:
            how += "; matched on the primary event in a compound description"
        return pt, how, list(dict.fromkeys(alts + others))[:4]
    pt, how, alts = _match_one(norm, ingredient)
    return (pt, how, alts) if pt else (None, "no matching MedDRA PT in snapshot", [])


def _pair_filter() -> str:
    return ("primaryid IN (SELECT primaryid FROM suspect_ingredients WHERE ingredient = ? "
            "INTERSECT SELECT primaryid FROM report_events WHERE pt = ?)")


def lookup(drug_text: str, event_text: str, event_pt: str | None = None) -> dict | None:
    """
    Counts for the 2x2 table plus breakdowns. Returns None if the snapshot is unavailable
    or the drug is not in it (caller then falls back to openFDA).
    """
    if not available():
        return None
    try:
        ingredient, drug_note = match_drug(drug_text)
        if not ingredient:
            logger.info(f"Local FAERS: drug '{drug_text}' not found")
            return None
        pt, event_note, alternatives = (None, "", [])
        if event_pt:  # MedDRA PT proposed at extraction, if it exists in the snapshot
            pt, event_note, alternatives = match_event(event_pt, ingredient)
            if pt and not event_note.startswith(("exact", "same")):
                pt = None
        if not pt:
            pt, event_note, alternatives = match_event(event_text, ingredient)
        m = meta()
        n_total = int(m["total_reports"])
        drug_total = _q("SELECT n FROM drug_counts WHERE ingredient = ?", ingredient)[0]["n"]
        result = {
            "ingredient": ingredient, "drug_match": drug_note,
            "pt": pt, "event_match": event_note, "alternative_pts": alternatives,
            "a": 0, "drug_total": drug_total, "event_total": 0, "n_total": n_total,
            "by_sex": {}, "by_age_group": {}, "outcomes": {},
            "data_period": m.get("quarters", ""), "data_through": m.get("data_through", ""),
            "source": f"FAERS quarterly files {m.get('quarters', '')}, deduplicated, suspect drugs only (local snapshot)",
        }
        if not pt:
            return result
        result["event_total"] = _q("SELECT n FROM event_counts WHERE pt = ?", pt)[0]["n"]
        row = _q("SELECT n FROM drug_event_counts WHERE ingredient = ? AND pt = ?", ingredient, pt)
        result["a"] = row[0]["n"] if row else 0
        if result["a"]:
            f = _pair_filter()
            result["by_sex"] = {r["sex"]: r["n"] for r in _q(
                f"SELECT sex, COUNT(*) n FROM cases WHERE {f} GROUP BY sex ORDER BY n DESC", ingredient, pt)}
            result["by_age_group"] = {r["age_group"]: r["n"] for r in _q(
                f"SELECT age_group, COUNT(*) n FROM cases WHERE {f} GROUP BY age_group ORDER BY n DESC", ingredient, pt)}
            result["outcomes"] = {OUTCOME_LABELS.get(r["outc_cod"], r["outc_cod"]): r["n"] for r in _q(
                f"SELECT outc_cod, COUNT(*) n FROM outcomes WHERE {f} GROUP BY outc_cod ORDER BY n DESC", ingredient, pt)}
        return result
    except Exception as e:  # never let the snapshot break the pipeline
        logger.warning(f"Local FAERS lookup failed: {e}")
        return None


def top_events_for(drug_text: str, limit: int = 10) -> list[dict]:
    """Most frequently reported events for a drug (useful for context and testing)."""
    ingredient, _ = match_drug(drug_text)
    if not ingredient:
        return []
    return [dict(r) for r in _q(
        "SELECT pt, n FROM drug_event_counts WHERE ingredient = ? ORDER BY n DESC LIMIT ?", ingredient, limit)]


def normalize_drug(text: str) -> str:
    return normalize_ingredient(text)


# --- Search ------------------------------------------------------------------------------

def search_drugs(query: str, limit: int = 10) -> list[dict]:
    """Ingredient and product-name suggestions for a typed query, most relevant first."""
    q = normalize_ingredient(query)
    if len(q) < 2 or not available():
        return []
    like = f"%{q}%"
    rows = {}
    for r in _q("SELECT ingredient, n FROM drug_counts WHERE ingredient LIKE ? ORDER BY n DESC LIMIT 40", like):
        rows[r["ingredient"]] = {"ingredient": r["ingredient"], "label": r["ingredient"], "reports": r["n"],
                                 "prefix": r["ingredient"].startswith(q)}
    for r in _q("""SELECT m.name, m.ingredient, d.n FROM drug_name_map m
                   JOIN drug_counts d ON d.ingredient = m.ingredient
                   WHERE m.name LIKE ? AND m.name <> m.ingredient ORDER BY d.n DESC LIMIT 40""", like):
        if r["ingredient"] not in rows:
            rows[r["ingredient"]] = {"ingredient": r["ingredient"], "label": f"{r['name']} ({r['ingredient']})",
                                     "reports": r["n"], "prefix": r["name"].startswith(q)}
    out = sorted(rows.values(), key=lambda x: (x["prefix"], x["reports"]), reverse=True)[:limit]
    for x in out:
        x.pop("prefix")
    return out


def search_events(query: str, ingredient: str | None = None, limit: int = 10) -> list[dict]:
    """MedDRA PT suggestions, optionally limited to events reported with a drug."""
    q = normalize_event(query)
    if len(q) < 2 or not available():
        return []
    like = f"%{q}%"
    if ingredient:
        rows = _q("""SELECT pt, n FROM drug_event_counts WHERE ingredient = ? AND pt LIKE ?
                     ORDER BY (pt LIKE ?) DESC, n DESC LIMIT ?""", ingredient, like, f"{q}%", limit)
    else:
        rows = _q("""SELECT pt, n FROM event_counts WHERE pt LIKE ?
                     ORDER BY (pt LIKE ?) DESC, n DESC LIMIT ?""", like, f"{q}%", limit)
    return [{"pt": r["pt"], "reports": r["n"]} for r in rows]


def _breakdown(where: str, *args) -> dict:
    return {
        "by_sex": {r["sex"]: r["n"] for r in _q(
            f"SELECT sex, COUNT(*) n FROM cases WHERE {where} GROUP BY sex ORDER BY n DESC", *args)},
        "by_age_group": {r["age_group"]: r["n"] for r in _q(
            f"SELECT age_group, COUNT(*) n FROM cases WHERE {where} GROUP BY age_group ORDER BY n DESC", *args)},
        "outcomes": {OUTCOME_LABELS.get(r["outc_cod"], r["outc_cod"]): r["n"] for r in _q(
            f"SELECT outc_cod, COUNT(*) n FROM outcomes WHERE {where} GROUP BY outc_cod ORDER BY n DESC", *args)},
    }


def drug_profile(drug_text: str, sort: str = "reports", signals_only: bool = False,
                 min_reports: int = 1, limit: int = 50) -> dict | None:
    """Safety profile of one drug: every event reported with it as suspect, with disproportionality."""
    from backend.services.disproportionality import signal_row
    if not available():
        return None
    ingredient, how = match_drug(drug_text)
    if not ingredient:
        return {"found": False, "query": drug_text}
    m = meta()
    n_total = int(m["total_reports"])
    drug_total = _q("SELECT n FROM drug_counts WHERE ingredient = ?", ingredient)[0]["n"]
    events = []
    for r in _q("""SELECT d.pt, d.n, e.n AS event_total FROM drug_event_counts d
                   JOIN event_counts e ON e.pt = d.pt WHERE d.ingredient = ?""", ingredient):
        row = {"pt": r["pt"], **signal_row(r["n"], drug_total, r["event_total"], n_total)}
        events.append(row)
    n_events, n_sdr = len(events), sum(e["is_sdr"] for e in events)
    events = [e for e in events if e["reports"] >= min_reports and (e["is_sdr"] or not signals_only)]
    if sort == "ror":
        events.sort(key=lambda e: (e["ror"] is not None, e["ci_lower"] or 0), reverse=True)
    else:
        events.sort(key=lambda e: e["reports"], reverse=True)
    return {
        "found": True, "query": drug_text, "ingredient": ingredient, "drug_match": how,
        "total_reports": drug_total, "distinct_events": n_events, "signals": n_sdr,
        "events": events[:limit], "events_shown": min(limit, len(events)), "events_matching": len(events),
        **_breakdown("primaryid IN (SELECT primaryid FROM suspect_ingredients WHERE ingredient = ?)", ingredient),
        "data_period": m.get("quarters", ""), "database_total_reports": n_total,
        "source": f"FAERS quarterly files {m.get('quarters', '')}, deduplicated, suspect drugs only",
    }


def pair_detail(drug_text: str, event_text: str) -> dict | None:
    """One drug-event combination: counts, ROR with CI, signal classification and breakdowns."""
    from backend.services.disproportionality import signal_row
    r = lookup(drug_text, event_text)
    if r is None:
        return None if not available() else {"found": False, "query": drug_text}
    out = {"found": True, **r}
    if r["pt"]:
        out.update(signal_row(r["a"], r["drug_total"], r["event_total"], r["n_total"]))
    return out
