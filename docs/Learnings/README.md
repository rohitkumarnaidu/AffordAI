# Learnings — Index & Organization

> No duplicates. Each of the 10 files is distinct (verified via SHA256 — see hashes below).
> This index maps every file to its Tier per `AGENTS.md §1` and to its role in the build.
> **Do not move or duplicate these files** — reference them by path.

## Hash verification (no accidental copies)

All 10 hashes distinct — `AffordAI_Orchestrate_September_Final_Integrated_Master` (e2f4778a) ≠ `Orchestrate_Integrated_Master_Research` (7b720b44) despite similar titles; the former is the deduplicated merge of two source reports, the latter is the pre-merge base with overlapping but narrower content. Keeping both is intentional for provenance; treat the September-labeled merge as the canonical research reference going forward.

| File | SHA | Tier | Purpose |
|---|---|---|---|
| `AffordAI_AGENTS_Final_Build_Contract_Prompt.md` (dbc6bb4) | Tier 4/5 — build contract | Input prompt that shaped current `AGENTS.md` (30 sections). Keep as evidence, never re-apply blindly. |
| `AffordAI_Opencode_Master_Inspection_Prompt.md` (fdd8346) | Tier 4/5 — inspection instruction | Master inspection prompt for this report (§§0–59). The checklist powering `evaluation/reports/master_inspection_report.md`. |
| `AffordAI_Complete_Winning_Implementation_Checklist.md` (d12805) | Tier 5 — execution checklist | 51-section gate (Prior lessons → clean-room → submission). Maps 1:1 to `docs/build-checklist.md` (Modules 0–35); use the build-checklist as the live tracker, this file as reference. |
| `AffordAI_Orchestrate_September_Final_Integrated_Master.md` (e2f4778) | Tier 5 — research synthesis | **Canonical research** (deterministic core, AI boundary, validation, hybrid defense). Absorbed into `docs/specification.md` + `AGENTS.md`; keep for interview citation. |
| `Orchestrate_Integrated_Master_Research.md` (7b720b44) | Tier 5 — source research (pre-merge) | Pre-merge base of the above. Retained for diff; do not edit. Prefer the `AffordAI_Orchestrate_…` merge. |
| `Orchestrate_Final_Action_Plan.md` (9367aa) | Tier 4 — post-mortem plan | 19-section “human defines contract → AI implements” operating plan. Direct ancestor of `AGENTS.md §28`. |
| `Anatomy of an Orchestrate Defeat…` (99848d) | Tier 4 — failure analysis | Root-cause: harness-aware architecture vs fragile prototype, verification loops, hallucination. Use for hidden-test thinking. |
| `Beyond Code…Top 10…` (ced4f36) | Tier 5 — competitive intel | Winner vs runner-up gap analysis (ecosystem, scoring 40% interview, transcript quality). Do not let it override Tier 1. |
| `From Competitor to Contender…` (a4f6b1) | Tier 4 — causal playbook | 60% judging + 40% evaluation causal model, 5 highest-leverage changes, what NOT to build. |
| `The Orchestrator's Blind Spot…` (98e6f4) | Tier 4 — first-party feedback audit | Granular map of prior evaluator praise (separation, retries) vs critical fails (row-order, generic explanations, inverted routing). Single biggest input to `AGENTS.md §14`. |

## Tier reminder (AGENTS.md §1)

Tier 1 official September problem > Tier 2 local evidence > Tier 3 official guidance > Tier 4 prior feedback > Tier 5 prior research > Tier 6 general assumptions. Never invert this.

## How to use

- **Before coding:** AGENTS.md + specification.md (Tier 1/2). The Learnings are *lessons*, not rules.
- **During build:** `docs/build-checklist.md` is the live gate; these files are the *why* behind each checklist item.
- **Before interview:** cite the `AffordAI_Orchestrate…` merge + `Blind Spot` audit; know the hash evidence that no Learning was silently duplicated.

## Organization rule

Keep all 10 files flat in `docs/Learnings/` with this README as the sole index. Do **not** create subfolders or copies — git history tracks provenance. If a new research file arrives, add it here with its SHA and Tier, then note which existing file (if any) it supersedes.
