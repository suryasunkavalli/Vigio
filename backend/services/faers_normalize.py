"""
Shared normalization for FAERS drug and event terms.
Used by tools/build_faers_db.py (when building the database) and by the local FAERS lookup,
so both sides normalize names the same way.
"""

import re

# Salt and ester words stripped from ingredient names when something remains after stripping.
SALT_WORDS = {
    "SODIUM", "POTASSIUM", "CALCIUM", "HYDROCHLORIDE", "HCL", "DIHYDROCHLORIDE", "HYDROBROMIDE",
    "OXALATE", "MESYLATE", "MALEATE", "SULFATE", "SULPHATE", "CITRATE", "TARTRATE", "BITARTRATE",
    "ACETATE", "BESYLATE", "FUMARATE", "HEMIFUMARATE", "SUCCINATE", "PHOSPHATE", "BROMIDE",
    "PAMOATE", "PROPANEDIOL", "MONOHYDRATE", "DIHYDRATE", "TRIHYDRATE", "HYDRATE", "ANHYDROUS",
    "TROMETHAMINE", "MEGLUMINE", "LYSINE", "DISODIUM", "MAGNESIUM", "CHLORIDE", "NITRATE",
    "LACTATE", "GLUCONATE", "TOSYLATE", "ESYLATE", "DECANOATE", "PALMITATE", "VALERATE",
}

# Words that never identify a drug in free text ("5 mg orally once daily", etc.)
DOSE_WORDS = {
    "MG", "MCG", "G", "ML", "IU", "UNITS", "UNIT", "ORAL", "ORALLY", "IV", "INTRAVENOUS", "SC",
    "SUBCUTANEOUS", "IM", "TABLET", "TABLETS", "CAPSULE", "CAPSULES", "INJECTION", "ONCE", "TWICE",
    "DAILY", "WEEKLY", "EVERY", "WEEKS", "DAY", "DAYS", "Q3W", "BID", "TID", "QD", "XR", "ER", "SR",
}

# US -> MedDRA (UK) spellings, applied word by word
SPELLING = [
    (r"HEMORRHAG", "HAEMORRHAG"), (r"HEMATOM", "HAEMATOM"), (r"\bEDEMA", "OEDEMA"),
    (r"DIARRHEA", "DIARRHOEA"), (r"ESOPHAG", "OESOPHAG"), (r"LEUKEMIA", "LEUKAEMIA"),
    (r"ISCHEMI", "ISCHAEMI"), (r"TUMOR\b", "TUMOUR"), (r"ANEMIA", "ANAEMIA"),
    (r"HEMOLY", "HAEMOLY"), (r"HEMOGLOBIN", "HAEMOGLOBIN"), (r"PEDIATRIC", "PAEDIATRIC"),
    (r"FETAL", "FOETAL"), (r"([^A])EMIA\b", r"\1AEMIA"), (r"ESTHESIA", "AESTHESIA"),
]


def normalize_ingredient(name: str) -> str:
    """Upper-case, tidy and strip salt words, e.g. 'Warfarin Sodium' -> 'WARFARIN'."""
    s = re.sub(r"[^A-Z0-9 \-]", " ", (name or "").upper())
    words = [w for w in s.split() if w]
    stripped = [w for w in words if w not in SALT_WORDS]
    return " ".join(stripped or words).strip()


def ingredients_for(prod_ai: str, drugname: str) -> list[str]:
    """Active ingredient(s) of a FAERS drug row; combination products are split on '\\'."""
    source = (prod_ai or "").strip() or (drugname or "").strip()
    if not source:
        return []
    return sorted({p for p in (normalize_ingredient(x) for x in source.split("\\")) if p})


def drug_query_candidates(text: str) -> list[str]:
    """
    Candidate ingredient or product names from free text, most specific first.
    'Warfarin sodium (Coumadin) 5 mg orally once daily' -> ['WARFARIN', 'COUMADIN', ...]
    """
    if not text:
        return []
    inside = re.findall(r"\(([^)]*)\)", text)
    outside = re.sub(r"\([^)]*\)", " ", text)
    candidates = []
    for chunk in [outside] + inside:
        words = [w for w in normalize_ingredient(chunk).split()
                 if w not in DOSE_WORDS and not re.fullmatch(r"[\d.,/]+", w)]
        for k in range(len(words), 0, -1):   # longest prefix first
            cand = " ".join(words[:k])
            if cand and cand not in candidates:
                candidates.append(cand)
    return candidates


def normalize_event(text: str) -> str:
    """Upper-case, drop parenthetical detail, map US spellings to MedDRA (UK) spellings."""
    s = re.sub(r"\([^)]*\)", " ", (text or "").upper())
    s = re.sub(r"[^A-Z0-9 \-]", " ", s)
    s = " ".join(s.split())
    for pat, rep in SPELLING:
        s = re.sub(pat, rep, s)
    return s
