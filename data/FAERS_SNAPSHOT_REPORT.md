# FAERS snapshot report

Built 2026-11-10T21:40:48Z with `tools/build_faers_db.py` from the FDA quarterly ASCII extract **2026Q3**.

## Contents

| Item | Value |
|---|---|
| Quarters included | 2026Q3 |
| DEMO rows read | 421,404 |
| Unique cases | 421,403 |
| Removed (FDA DELETE list) | 2 |
| **Reports in snapshot (N)** | **421,401** |
| Suspect drug–ingredient links | 669,652 |
| Report–event links | 1,339,973 |
| Distinct suspect ingredients | 3,541 |
| Distinct MedDRA PTs | 12,593 |
| Drug–event pairs | 589,234 |
| Product-name → ingredient mappings | 6,978 |

Method: Latest caseversion per caseid; cases in DELETE files removed. Drugs: Active ingredient (prod_ai, else drugname), salts stripped, combinations split; suspect roles PS and SS only. Events: MedDRA preferred term as reported in FAERS (upper-cased).

Reports by sex: Female 214,966, Male 130,343, Unknown 76,092.
Reports by age group: Adult 166,127, Elderly 127,184, Unknown 104,670, Child 10,667, Adolescent 9,580, Infant 2,121, Neonate 1,052.

Most reported suspect ingredients: DUPILUMAB (45,292), TIRZEPATIDE (19,749), SEMAGLUTIDE (10,824), ETONOGESTREL (10,372), LENALIDOMIDE (6,783), BIMEKIZUMAB-BKZX (5,890), RISANKIZUMAB-RZAA (5,743), RITUXIMAB (4,775), UPADACITINIB (4,658), ACETAMINOPHEN (4,575).

## Demo drug–event pairs

ROR with 95% CI; signal of disproportionate reporting requires ≥3 reports and a CI lower bound above 1.

| Ingredient | MedDRA PT | Why checked | Reports (a) | Drug total | Event total | ROR (95% CI) | Classification | Data confidence |
|---|---|---|---|---|---|---|---|---|
| WARFARIN | HAEMORRHAGE INTRACRANIAL | demo case 1 | 9 | 319 | 173 | 74.51 (37.74–147.11) | Strong (ROR ≥ 5) | Low |
| WARFARIN | INTERNATIONAL NORMALISED RATIO INCREASED | known effect | 40 | 319 | 146 | 569.39 (388.53–834.42) | Strong (ROR ≥ 5) | Moderate |
| PEMBROLIZUMAB | IMMUNE-MEDIATED MYOCARDITIS | demo case 2 | 56 | 4,298 | 128 | 76.46 (53.85–108.56) | Strong (ROR ≥ 5) | Moderate |
| PEMBROLIZUMAB | MYOCARDITIS | demo case 2 (broader PT) | 63 | 4,298 | 368 | 20.33 (15.47–26.71) | Strong (ROR ≥ 5) | Moderate |
| METFORMIN | LACTIC ACIDOSIS | demo case 3 | 570 | 2,356 | 837 | 500.57 (429.73–583.1) | Strong (ROR ≥ 5) | High |
| METFORMIN | HEADACHE | comparison: common non-specific event | 103 | 2,356 | 12,451 | 1.51 (1.23–1.84) | Weak (ROR < 2) | High |

## Checks performed

- **Independent recount:** for the three demo pairs, report counts, drug totals, event totals and N were recomputed directly from the raw text files without the database. All matched exactly.
- **Known associations:** the expected drug–event pairs (warfarin–INR increased, metformin–lactic acidosis, pembrolizumab–immune-mediated myocarditis) show strong disproportionality, as they should.
- **Name matching:** free-text names from case reports resolve correctly, e.g. 'Warfarin sodium (Coumadin) 5 mg' → WARFARIN, 'Keytruda' → PEMBROLIZUMAB, 'Intracranial haemorrhage (subdural…)' → HAEMORRHAGE INTRACRANIAL, 'Immune-mediated myocarditis with cardiogenic shock' → IMMUNE-MEDIATED MYOCARDITIS.

## Limitations

- **One quarter only.** Counts for less common pairs are small (warfarin–intracranial haemorrhage: 9 reports), so confidence intervals are wide. Add more quarters for stable estimates; the builder deduplicates across quarters.
- ROR values are very high for well-known pairs. That reflects reporting patterns (stimulated and duplicate-prone reporting, no exposure denominator), not risk magnitude.
- Combination products count toward each ingredient. Product-name mapping uses the most common ingredient for that name (e.g. JANUMET → METFORMIN).
- Some FAERS demographic fields are inconsistent at source (e.g. occasional age-group codes that conflict with the reported context); they are shown as reported.
