#!/usr/bin/env python3
"""
Embed a compact FAERS extract in frontend/standalone.html so Drug Safety Search works in the
published demo without a backend.

Usage:
    python tools/export_search_extract.py [--db data/faers.db] [--html frontend/standalone.html]
                                          [--drugs 500] [--top 25] [--signals 25]

For the most-reported suspect ingredients (plus the demo drugs) it keeps, per drug, the most
reported events and the strongest signals of disproportionate reporting, with the counts needed
to compute the ROR and 95% CI in the browser. The full search (every drug, breakdowns by sex,
age and outcome) needs the backend and the full database.

The extract is written between the markers /*FAERS_EXTRACT_START*/ and /*FAERS_EXTRACT_END*/.
"""

import argparse
import json
import math
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALWAYS_INCLUDE = ["WARFARIN", "PEMBROLIZUMAB", "METFORMIN"]
START, END = "/*FAERS_EXTRACT_START*/", "/*FAERS_EXTRACT_END*/"


def ci_lower(a, dt, et, n):
    b, c = dt - a, et - a
    d = n - a - b - c
    if min(a, b, c, d) <= 0:
        return 0
    ror = (a / b) / (c / d)
    return math.exp(math.log(ror) - 1.96 * math.sqrt(1 / a + 1 / b + 1 / c + 1 / d))


def build(db: Path, n_drugs: int, n_top: int, n_signals: int) -> dict:
    con = sqlite3.connect(db)
    q = lambda s, *a: con.execute(s, a).fetchall()
    meta = dict(q("SELECT key, value FROM meta"))
    n_total = int(meta["total_reports"])
    drugs = [r[0] for r in q("SELECT ingredient FROM drug_counts ORDER BY n DESC LIMIT ?", n_drugs)]
    drugs += [d for d in ALWAYS_INCLUDE if d not in drugs and q("SELECT 1 FROM drug_counts WHERE ingredient=?", d)]
    event_totals = dict(q("SELECT pt, n FROM event_counts"))

    pts, pt_index, out_drugs = [], {}, {}
    for ing in drugs:
        dt = q("SELECT n FROM drug_counts WHERE ingredient=?", ing)[0][0]
        rows = q("SELECT pt, n FROM drug_event_counts WHERE ingredient=?", ing)
        top = sorted(rows, key=lambda r: r[1], reverse=True)[:n_top]
        sig = sorted((r for r in rows if r[1] >= 3), key=lambda r: ci_lower(r[1], dt, event_totals[r[0]], n_total),
                     reverse=True)
        sig = [r for r in sig if round(ci_lower(r[1], dt, event_totals[r[0]], n_total), 2) > 1][:n_signals]
        keep = {r[0]: r[1] for r in top + sig}
        enc = []
        for pt, a in sorted(keep.items(), key=lambda kv: kv[1], reverse=True):
            if pt not in pt_index:
                pt_index[pt] = len(pts)
                pts.append(pt)
            enc.append([pt_index[pt], a])
        n_sdr = sum(1 for pt, a in rows if a >= 3 and round(ci_lower(a, dt, event_totals[pt], n_total), 2) > 1)
        out_drugs[ing] = {"n": dt, "k": len(rows), "s": n_sdr, "e": enc}

    names = {name: ing for name, ing, n in q("SELECT name, ingredient, n FROM drug_name_map WHERE n >= 3")
             if ing in out_drugs and name != ing and len(name) <= 40}
    return {
        "period": meta.get("quarters", ""), "N": n_total, "built": meta.get("built_at", ""),
        "pts": pts, "et": [event_totals[p] for p in pts], "drugs": out_drugs, "names": names,
        "note": f"Top {len(drugs)} suspect ingredients; per drug the {n_top} most reported events and up to "
                f"{n_signals} strongest signals. Full search requires the backend.",
    }


def inject(html: Path, extract: dict) -> None:
    s = html.read_text(encoding="utf-8")
    payload = "window.FAERS_EXTRACT = " + json.dumps(extract, separators=(",", ":")) + ";"
    block = f"{START}{payload}{END}"
    if START in s:
        s = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: block, s, flags=re.S)
    else:
        s = s.replace("<script type=\"text/babel\">", f"<script>{block}</script>\n<script type=\"text/babel\">", 1)
    html.write_text(s, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "faers.db")
    ap.add_argument("--html", type=Path, default=ROOT / "frontend" / "standalone.html")
    ap.add_argument("--drugs", type=int, default=1000)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--signals", type=int, default=25)
    args = ap.parse_args()
    ex = build(args.db, args.drugs, args.top, args.signals)
    inject(args.html, ex)
    size = len(json.dumps(ex, separators=(",", ":")))
    print(f"Embedded {len(ex['drugs'])} drugs, {len(ex['pts'])} event terms, "
          f"{sum(len(d['e']) for d in ex['drugs'].values())} drug-event rows, {len(ex['names'])} product names "
          f"({size / 1e6:.2f} MB) into {args.html}")
