# AI Telemetry — Methodology

**Version:** 1.0
**Effective:** 2026-05-25
**Repo:** `github.com/ai-telemetry/data`
**Dashboard:** `aitelemetry.org`

This document defines what AI Telemetry tracks, how, from where, and what its data does and does not claim. Every chart on the dashboard and every column in the CSV files traces back here. If you cite the data, also cite the methodology version stamped on each row.

---

## 1. Scope

AI Telemetry maintains a longitudinal, point-in-time-revisioned dataset of:

- Frontier and notable AI models.
- Organizations that train them.
- Standardized evaluation results.
- Publicly documented incidents involving AI systems.

It does not track: inference pricing, adoption / usage metrics, open-source model proliferation counts (Hugging Face repository totals etc.), forecasts, opinion, or subjective safety / alignment ratings of labs.

The dataset is intended for use by researchers, journalists, regulators, and the public. It is not financial advice, a procurement guide, or a safety certification.

---

## 2. Entities

| Entity | Description |
|---|---|
| `model` | A trained AI model meeting the *notable* threshold (§3). |
| `org` | An entity that trained or substantially fine-tuned a tracked model. |
| `eval` | A score from a standardized benchmark, attributed to a model and benchmark version. |
| `incident` | A publicly documented event involving an AI system causing harm, near-harm, or capability surprise. |

A fifth file, `disputes.csv`, records cases where two sources disagree on the value of a tracked field and how the disagreement was resolved.

---

## 3. Definitions (v1.0)

These definitions are *versioned*. Any change increments the definition version; previous-version data remains queryable and is not retrospectively rewritten.

### 3.1 Notable model

A model is *notable* if either:

- **Compute criterion.** Estimated training compute ≥ 10²⁴ FLOP, using the methodology of Epoch AI's parameter-and-tokens estimator with their published confidence tiers. Or:
- **First-of-kind criterion.** First public model to demonstrate a qualitatively new capability with published eval evidence (e.g. first to surpass human baseline on a canonical benchmark; first general agent to complete a class of multi-step tasks under METR's protocol).

A model that fails both is not tracked, regardless of press coverage.

### 3.2 Frontier model

A *notable* model is also *frontier* if either:

- **Compute criterion.** Training compute ≥ 10²⁵ FLOP at release. Or:
- **Capability criterion.** At release, top-3 on at least one canonical benchmark from the v1.0 canonical set: MMLU-Pro, GPQA Diamond, SWE-bench Verified, ARC-AGI-2, HumanEval+, AIME (rolling: current-year AIME-I + AIME-II + previous-year combined, 45 problems total).

Frontier status is sticky: a model that was frontier at release remains frontier-at-release in historical data even after others surpass it.

### 3.3 Incident

An *incident* is a publicly documented event in which an AI system:

- Caused, contributed to, or narrowly avoided real-world harm, *or*
- Exhibited a capability or behavior that surprised informed observers, *or*
- Was misused with public consequences.

Sources must be: AI Incident Database, OECD AI Incidents Monitor, or a direct citation from a publication with editorial oversight. Fiction, hypotheticals, opinion essays, and uncorroborated social-media reports are excluded.

### 3.4 Organization

An *org* is an entity that trained or substantially fine-tuned a tracked model. *Substantial fine-tuning* is defined as fine-tuning that (a) materially changes capability (≥ 5 percentage points on any canonical benchmark), or (b) is published as a distinct named model. Pure API-resellers and prompt-wrapper products are not orgs.

### 3.5 Compute estimate

`training_compute_flop` is an estimate, not a measurement, unless the lab publishes the figure directly. Estimates use Epoch AI's `6 × parameters × tokens` heuristic with their published confidence tiers (`confirmed`, `likely`, `estimated`, `speculative`). The confidence is stored in `compute_confidence`.

---

## 4. Sources

### 4.1 Source list (v1.0)

| Source | Domain | Cadence | License |
|---|---|---|---|
| Epoch AI database | compute, models | daily | CC-BY |
| Lab system cards / blog posts | model metadata, evals | on change | varies — link, do not redistribute body text |
| Hugging Face API | model releases (filtered) | hourly | open |
| arXiv (cs.CL, cs.LG, cs.AI) | papers, evals | daily | open metadata |
| AI Incident Database | incidents | daily | CC-BY |
| OECD AI Incidents Monitor | incidents | daily | OECD terms |
| METR autonomy evals | evals | on release | open |
| LMSys leaderboard | evals (chat) | daily | open metadata |
| Per-benchmark leaderboards (MMLU-Pro, GPQA, SWE-bench, ARC-AGI-2, HumanEval+, AIME) | evals | weekly | varies |

Every CSV row records the source used for that field in the `source` column and the upstream URL in `source_url` where applicable.

### 4.2 Per-field source precedence

When sources disagree on the value of a field, the field's declared precedence applies. Precedence is encoded in `precedence.yaml` in the repository root and reviewed quarterly. Current v1.0 rules:

- `training_compute_flop`: Epoch AI > lab disclosure > paper > press estimate.
- `release_date`: lab announcement > paper submission date > Hugging Face commit date.
- Benchmark scores: lab-reported result on the canonical leaderboard > independent reproduction > paper figure.
- Incident metadata: AIID > OECD > press citation.

When the highest-precedence source is silent, the next is used and the source field reflects the actual source used, not the highest-precedence one in the abstract.

### 4.3 Disagreement log

Every case where two sources disagree on a tracked field produces an entry in `disputes.csv` with both values, the resolution, and a brief resolver note. Disputes are public.

---

## 5. Point-in-time integrity

### 5.1 Revisions, not overwrites

Every canonical record carries four time columns:

- `observed_at` — when AI Telemetry first read this value.
- `valid_from` — when this value became the canonical answer.
- `valid_to` — when this value was superseded (`null` if current).
- `source_at` — the upstream's stated effective date for the value, when available.

When a value changes (a benchmark score is corrected; an estimate is revised; a model's release date is moved), the previous row's `valid_to` is set and a new row is appended. Historical values are never rewritten silently.

Researchers can reconstruct "what AI Telemetry knew on date D" by selecting rows where `valid_from ≤ D < valid_to OR (valid_from ≤ D AND valid_to IS NULL)`.

### 5.2 The `current.csv` shortcut

For casual use, a `current.csv` per entity is published alongside the revisioned table. It contains only the rows where `valid_to IS NULL`. It is a build-time export, not a separate source of truth. Researchers should use the revisioned tables.

### 5.3 Definition version stamping

Every row carries `definition_version`. When a definition changes (e.g. the FLOP threshold for *notable* moves), existing rows keep their original `definition_version` and new rows are stamped with the new one. Charts on the dashboard disclose which version they query.

### 5.4 Correcting errors

When AI Telemetry corrects an error (not a revision — an actual mistake), the corrected row is appended with a new `observed_at` and the commit message in git records the reason. The previous (incorrect) row's `valid_to` is set to its original `valid_from`, making it a zero-duration record. This preserves the audit trail.

---

## 6. Data files

```
data/
  models.csv         entity_id, name, org_id, release_date,
                     training_compute_flop, compute_confidence,
                     capability_tier, open_weights, context_window,
                     modalities, system_card_url, paper_url,
                     source, source_url, observed_at, source_at,
                     valid_from, valid_to, definition_version

  orgs.csv           org_id, name, country, type, parent_org_id,
                     source, source_url, observed_at, source_at,
                     valid_from, valid_to, definition_version

  evals.csv          eval_id, model_id, benchmark, benchmark_version,
                     score, score_unit, eval_date, evaluator,
                     source, source_url, observed_at, source_at,
                     valid_from, valid_to, definition_version

  incidents.csv      incident_id, occurred_at, reported_at,
                     models_involved, orgs_involved, category,
                     severity, geography, summary,
                     source, source_url, observed_at, source_at,
                     valid_from, valid_to, definition_version

  disputes.csv       entity_id, field, source_a, value_a,
                     source_b, value_b, resolution, resolved_at,
                     resolver_note

  precedence.yaml    per-field source precedence rules
  aliases.csv        canonical-name ↔ alias mappings
  overrides.yaml     manual canonical-value overrides (with reason)
  schema_version     current schema version (e.g. "1.0")
```

All CSVs are UTF-8 with RFC 4180 quoting. Array fields (`models_involved`, `modalities`) are pipe-separated within a single CSV cell.

---

## 7. Update cadence

- Ingestion runs on schedules described in §4.1.
- The repository is rebuilt and the dashboard redeployed within 15 minutes of any committed data change.
- A daily release tag (`v1.0.YYYY-MM-DD`) is cut at 00:00 UTC with an auto-generated changelog summarizing additions, revisions, and corrections for the prior 24 hours.

If a scheduled ingester has not produced a successful run in 24 hours, the dashboard surfaces a per-source "stale" banner. The data is not removed; it is marked.

---

## 8. License

- **Data** (everything in `data/`): [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Free use with attribution.
- **Code** (everything else): [MIT](https://opensource.org/licenses/MIT).

Some upstream sources impose additional constraints on redistribution of their *body text* (e.g. lab system cards). AI Telemetry stores only metadata, scores, and URLs from such sources, never the full text.

---

## 9. Citation

```
AI Telemetry (2026). AI Telemetry Dataset, v1.0.
github.com/ai-telemetry/data. Methodology v1.0.
Retrieved YYYY-MM-DD.
```

When citing a specific value or chart, include the release tag (`v1.0.YYYY-MM-DD`) so the citation is reproducible against the revisioned tables.

---

## 10. Known limitations

- **Compute estimates are estimates.** Several frontier-model compute figures rely on Epoch AI's methodology in the absence of lab disclosure. Confidence tiers are stored per-row; treat `speculative`-tier values as order-of-magnitude only.
- **Incident reporting is biased toward English-language sources** and toward harms that reach Western press. Non-English and Global-South incident reporting is materially under-represented.
- **Benchmark leaderboards drift.** When a benchmark publishes a v2, AI Telemetry treats v1 and v2 as different `benchmark_version` values; scores are not cross-comparable across versions.
- **Definitions evolve.** "Frontier" in 2026 is not "frontier" in 2030. The version-stamping system (§5.3) is the answer to this, but consumers who use `current.csv` without inspecting `definition_version` will get longitudinal inconsistency.
- **No real-time guarantee.** Update cadences are best-effort. The dashboard surfaces staleness; downstream consumers should too.
- **Single curator.** v1.0 is maintained by one person on a published weekly cadence. Coverage gaps exist and should be reported as issues on the repository.

---

## 11. Versioning

- **Methodology versions** (this document) follow semantic versioning at the major.minor level. Breaking definition changes bump major.
- **Schema versions** (CSV columns) are tracked in `schema_version`. Adding a column is a minor bump; removing or renaming is major.
- **Data release tags** (`v1.0.YYYY-MM-DD`) are immutable. Once cut, they are never amended; corrections appear in subsequent tags.

A `CHANGELOG.md` records every methodology and schema change with date and reason.

---

## 12. Reporting issues

Open an issue on `github.com/ai-telemetry/data` for: missing models, incorrect values, mis-cited sources, definitional ambiguities. Pull requests against `data/` should reference an upstream source for the change.

---

*Methodology v1.0 — 2026-05-25.*
