#!/usr/bin/env python3
"""
Build Vigio's local FAERS database from FDA quarterly ASCII extract files.

Usage:
    python tools/build_faers_db.py --out data/faers.db faers_ascii_2026q3.zip [faers_ascii_2026q2.zip ...]

Inputs may be the quarterly ZIP files as downloaded from the FDA portal, or folders containing
the unzipped ASCII/*.txt files. Several quarters can be combined in one build.

What it does:
  1. Reads DEMO, DRUG, REAC and OUTC tables ($-delimited) for every quarter given.
  2. Deduplicates: keeps only the latest version of each case (highest caseversion, then the
     latest FDA receipt date), and drops cases listed in the quarterly DELETE files.
  3. Normalizes drugs to active ingredient(s): uses prod_ai (falls back to drugname), splits
     combination products on '\\', strips common salt forms (WARFARIN SODIUM -> WARFARIN).
  4. Counts each report once per ingredient and event, using SUSPECT drugs only
     (role PS = primary suspect, SS = secondary suspect).
  5. Writes precomputed count tables for disproportionality:
        drug_event_counts(ingredient, pt, n)   a      = reports with drug suspect and event
        drug_counts(ingredient, n)             a + b  = reports with drug suspect
        event_counts(pt, n)                    a + c  = reports with event (any drug)
        meta(key, value)                       N      = total deduplicated reports, quarters, build date
     plus report-level tables (cases, suspect_ingredients, report_events, outcomes) for subgroup
     and outcome breakdowns. Use --keep-raw to also keep the row-level drug and reaction tables.

Standard library only (sqlite3). Expect a few minutes and a few hundred MB per quarter.
"""

import argparse
import io
import re
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Shared with the backend so names are normalized the same way when building and when querying.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.services.faers_normalize import ingredients_for, normalize_ingredient  # noqa: E402

AGE_GROUP_LABELS = {"N": "Neonate", "I": "Infant", "C": "Child", "T": "Adolescent", "A": "Adult", "E": "Elderly"}
OUTCOME_LABELS = {"DE": "Death", "LT": "Life-threatening", "HO": "Hospitalization", "DS": "Disability",
                  "CA": "Congenital anomaly", "RI": "Required intervention", "OT": "Other serious"}
AGE_UNIT_YEARS = {"YR": 1.0, "DEC": 10.0, "MON": 1 / 12, "WK": 1 / 52.18, "DY": 1 / 365.25, "HR": 1 / 8766}


def age_in_years(age: str, unit: str):
    try:
        return round(float(age) * AGE_UNIT_YEARS[unit], 2)
    except (ValueError, KeyError):
        return None


def derive_age_group(code: str, years) -> str:
    if code in AGE_GROUP_LABELS:
        return AGE_GROUP_LABELS[code]
    if years is None:
        return "Unknown"
    if years < 28 / 365.25:
        return "Neonate"
    if years < 2:
        return "Infant"
    if years < 12:
        return "Child"
    if years < 18:
        return "Adolescent"
    if years < 65:
        return "Adult"
    return "Elderly"


# --- Reading quarterly files --------------------------------------------------------------

class Quarter:
    """One quarter's files, from a ZIP or a folder."""

    def __init__(self, path: Path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.is_file() else None
        names = self.zip.namelist() if self.zip else [str(p.relative_to(path)) for p in path.rglob("*")]
        self.names = names
        demo = [n for n in names if re.search(r"DEMO(\d{2}Q\d)\.txt$", n, re.I)]
        if not demo:
            raise SystemExit(f"No DEMOyyQn.txt found in {path}")
        self.code = re.search(r"DEMO(\d{2}Q\d)", demo[0], re.I).group(1).upper()  # e.g. 26Q3
        self.label = f"20{self.code[:2]}{self.code[2:]}"                         # e.g. 2026Q3

    def _find(self, table: str):
        pat = re.compile(rf"(^|/){table}{self.code}\.txt$", re.I)
        return next((n for n in self.names if pat.search(n)), None)

    def _open(self, name):
        raw = self.zip.open(name) if self.zip else open(self.path / name, "rb")
        return io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")

    def rows(self, table: str):
        """Yield dict rows for a $-delimited table (header in first line)."""
        name = self._find(table)
        if not name:
            return
        with self._open(name) as f:
            header = [h.strip().lower() for h in f.readline().rstrip("\r\n").split("$")]
            for line in f:
                vals = line.rstrip("\r\n").split("$")
                if len(vals) < len(header):
                    vals += [""] * (len(header) - len(vals))
                yield dict(zip(header, vals))

    def deleted_case_ids(self) -> set[str]:
        name = next((n for n in self.names if re.search(r"DELETE.*\.txt$", n, re.I)), None)
        if not name:
            return set()
        with self._open(name) as f:
            return {line.strip() for line in f if line.strip().isdigit()}


# --- Build --------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE cases (
    primaryid INTEGER PRIMARY KEY, caseid TEXT, caseversion INTEGER, quarter TEXT, fda_dt TEXT,
    age_years REAL, age_group TEXT, sex TEXT, reporter_type TEXT, occr_country TEXT, rept_cod TEXT
);
CREATE TABLE drugs (
    primaryid INTEGER, drug_seq TEXT, role_cod TEXT, drugname TEXT, prod_ai TEXT,
    ingredient TEXT, dechal TEXT, rechal TEXT, norm_name TEXT
);
CREATE TABLE reactions (primaryid INTEGER, pt TEXT);
CREATE TABLE outcomes (primaryid INTEGER, outc_cod TEXT, PRIMARY KEY (primaryid, outc_cod)) WITHOUT ROWID;
"""

INDEXES = """
-- One row per report and suspect ingredient (roles PS, SS)
CREATE TABLE suspect_ingredients (ingredient TEXT, primaryid INTEGER, PRIMARY KEY (ingredient, primaryid)) WITHOUT ROWID;
INSERT OR IGNORE INTO suspect_ingredients
    SELECT ingredient, primaryid FROM drugs WHERE role_cod IN ('PS','SS') AND ingredient <> '';

-- One row per report and event (MedDRA PT)
CREATE TABLE report_events (pt TEXT, primaryid INTEGER, PRIMARY KEY (pt, primaryid)) WITHOUT ROWID;
INSERT OR IGNORE INTO report_events SELECT pt, primaryid FROM reactions WHERE pt <> '';

CREATE TABLE drug_counts (ingredient TEXT PRIMARY KEY, n INTEGER) WITHOUT ROWID;
INSERT INTO drug_counts SELECT ingredient, COUNT(*) FROM suspect_ingredients GROUP BY ingredient;

CREATE TABLE event_counts (pt TEXT PRIMARY KEY, n INTEGER) WITHOUT ROWID;
INSERT INTO event_counts SELECT pt, COUNT(*) FROM report_events GROUP BY pt;

CREATE INDEX idx_re_pid ON report_events(primaryid);
CREATE TABLE drug_event_counts (ingredient TEXT, pt TEXT, n INTEGER, PRIMARY KEY (ingredient, pt)) WITHOUT ROWID;
INSERT INTO drug_event_counts
    SELECT si.ingredient, re.pt, COUNT(*)
    FROM suspect_ingredients si JOIN report_events re ON re.primaryid = si.primaryid
    GROUP BY si.ingredient, re.pt;
DROP INDEX idx_re_pid;

-- Brand or product name -> most common suspect ingredient (lets 'COUMADIN' find 'WARFARIN')
CREATE TABLE drug_name_map (name TEXT PRIMARY KEY, ingredient TEXT, n INTEGER) WITHOUT ROWID;
INSERT INTO drug_name_map
    SELECT name, ingredient, n FROM (
        SELECT name, ingredient, n, ROW_NUMBER() OVER (PARTITION BY name ORDER BY n DESC) AS rk
        FROM (SELECT norm_name AS name, ingredient, COUNT(*) AS n FROM drugs
              WHERE role_cod IN ('PS','SS') AND ingredient <> '' AND norm_name <> '' AND norm_name NOT LIKE '%\\%'
              GROUP BY norm_name, ingredient)
    ) WHERE rk = 1;
"""


def build(inputs: list[Path], out: Path, keep_raw: bool = False) -> None:
    quarters = [Quarter(p) for p in inputs]
    print(f"Quarters: {', '.join(q.label for q in quarters)}")

    # Pass 1: choose the latest version of each case across all quarters.
    deleted = set().union(*(q.deleted_case_ids() for q in quarters))
    latest: dict[str, tuple] = {}   # caseid -> (caseversion, fda_dt, primaryid, quarter, row)
    demo_rows = 0
    for q in quarters:
        for r in q.rows("DEMO"):
            demo_rows += 1
            cid = r.get("caseid", "")
            try:
                ver = int(r.get("caseversion") or 0)
            except ValueError:
                ver = 0
            key = (ver, r.get("fda_dt", ""), r.get("primaryid", ""))
            if cid not in latest or key > latest[cid][0]:
                latest[cid] = (key, q.label, r)
    kept = {v[2]["primaryid"]: (v[1], v[2]) for cid, v in latest.items() if cid not in deleted}
    print(f"DEMO rows read: {demo_rows:,} | unique cases: {len(latest):,} | "
          f"deleted: {len(deleted & latest.keys()):,} | kept reports: {len(kept):,}")

    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)

    con.executemany(
        "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            (int(pid), r["caseid"], int(r.get("caseversion") or 0), qlabel, r.get("fda_dt", ""),
             (yrs := age_in_years(r.get("age", ""), r.get("age_cod", ""))),
             derive_age_group(r.get("age_grp", ""), yrs),
             {"F": "Female", "M": "Male"}.get(r.get("sex", ""), "Unknown"),
             r.get("occp_cod", ""), r.get("occr_country", ""), r.get("rept_cod", ""))
            for pid, (qlabel, r) in kept.items()
        ),
    )

    def keep(rows):
        return (r for r in rows if r.get("primaryid") in kept)

    n_drug = n_reac = n_outc = 0
    for q in quarters:
        batch = []
        for r in keep(q.rows("DRUG")):
            for ing in ingredients_for(r.get("prod_ai", ""), r.get("drugname", "")) or [""]:
                batch.append((int(r["primaryid"]), r.get("drug_seq", ""), r.get("role_cod", "").strip(),
                              r.get("drugname", "").strip(), r.get("prod_ai", "").strip(), ing,
                              r.get("dechal", ""), r.get("rechal", ""),
                              normalize_ingredient(r.get("drugname", ""))))
            if len(batch) >= 200_000:
                con.executemany("INSERT INTO drugs VALUES (?,?,?,?,?,?,?,?,?)", batch); n_drug += len(batch); batch = []
        con.executemany("INSERT INTO drugs VALUES (?,?,?,?,?,?,?,?,?)", batch); n_drug += len(batch)

        reac = [(int(r["primaryid"]), r.get("pt", "").strip().upper()) for r in keep(q.rows("REAC"))]
        con.executemany("INSERT INTO reactions VALUES (?,?)", reac); n_reac += len(reac)
        outc = [(int(r["primaryid"]), r.get("outc_cod", "").strip()) for r in keep(q.rows("OUTC"))]
        con.executemany("INSERT OR IGNORE INTO outcomes VALUES (?,?)", outc); n_outc += len(outc)
        con.commit()
    print(f"Loaded drug rows: {n_drug:,} | reaction rows: {n_reac:,} | outcome rows: {n_outc:,}")

    print("Building indexes and count tables...")
    con.executescript(INDEXES)

    meta = {
        "quarters": ",".join(sorted(q.label for q in quarters)),
        "data_through": max(q.label for q in quarters),
        "total_reports": str(len(kept)),
        "deduplication": "Latest caseversion per caseid; cases in DELETE files removed",
        "drug_matching": "Active ingredient (prod_ai, else drugname), salts stripped, combinations split; suspect roles PS and SS only",
        "event_coding": "MedDRA preferred term as reported in FAERS (upper-cased)",
        "source": "FDA FAERS / AEMS Quarterly Data Extract Files (ASCII)",
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "vigio tools/build_faers_db.py v1.1",
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    if not keep_raw:
        # The derived tables hold everything the Population lens needs; drop raw rows to save space.
        con.executescript("DROP TABLE drugs; DROP TABLE reactions;")
    con.commit()
    con.execute("VACUUM")
    con.close()
    print(f"Done: {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path, help="Quarterly ZIP files or unzipped folders")
    ap.add_argument("--out", type=Path, default=Path("data/faers.db"))
    ap.add_argument("--keep-raw", action="store_true",
                    help="Keep row-level drug and reaction tables (drug names, dechallenge, etc.); larger file")
    args = ap.parse_args()
    missing = [p for p in args.inputs if not p.exists()]
    if missing:
        sys.exit(f"Not found: {', '.join(map(str, missing))}")
    build(args.inputs, args.out, args.keep_raw)
