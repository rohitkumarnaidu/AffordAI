# AffordAI — OpenCode Master Inspection Prompt
## HackerRank Orchestrate September 2026 — Buy or Wait?

> **Purpose:** Give this prompt to OpenCode before the next implementation phase. It forces a complete, evidence-based read of the project reports, official challenge contract, local dataset, images, current repository state, and transcript state before writing financial/business logic.

---

# 0. YOUR ROLE

Act as the lead repository auditor and technical planning engineer for:

**Project:** AffordAI  
**Full name:** AffordAI — AI Financial Affordability & Payment Planner

**Owner:** `rohitkumarnaidu`

**Implementation repository:**
`https://github.com/rohitkumarnaidu/AffordAI`

**Official challenge repository:**
`https://github.com/interviewstreet/hackerrank-orchestrate-september26`

**Challenge:**
HackerRank Orchestrate September 2026 — Buy or Wait?

**Challenge URL:**
`https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait`

---

# 1. THIS IS AN INSPECTION / UNDERSTANDING PHASE

For this task:

## DO

- read
- inspect
- compare
- verify
- inventory
- map
- identify gaps
- identify contradictions
- produce findings
- produce a build-ready implementation plan

## DO NOT

- start the full implementation
- invent business rules
- redesign the project from assumptions
- add unnecessary dependencies
- add an LLM just because it is available
- change official source datasets
- blindly merge `upstream`
- fabricate transcript history
- mark incomplete work as complete

The purpose is to make sure we fully understand the project before implementing Milestone 2 and beyond.

---

# 2. ABSOLUTE SOURCE PRIORITY

Use this hierarchy:

## Tier 1 — Official September challenge

Highest priority:

1. official September `problem_statement.md`
2. official September `AGENTS.md`
3. official participant-facing files
4. official dataset
5. official submission requirements

## Tier 2 — Current repository evidence

- actual AffordAI source code
- actual tests
- actual docs
- actual Git history
- actual dataset copy
- actual generated reports
- actual `log.txt`

## Tier 3 — Official HackerRank guidance

Use only where relevant:

- official Orchestrate guidance
- judging guidance
- transcript guidance
- AI-fluency guidance
- current September communications

## Tier 4 — First-party prior HackerRank feedback

Use actual evaluator feedback from earlier attempts.

## Tier 5 — Our research reports

Use:

- winner analysis
- top-10 comparisons
- September blueprint
- final integrated research
- action plan
- Blind Spot analysis
- build contract/checklist

## Tier 6 — General engineering knowledge

Use only when the higher tiers do not answer the question.

### Rule

When sources conflict:

> Higher-priority evidence wins.

When something cannot be verified:

> Say `UNKNOWN`.

When something is inferred:

> Say `INFERENCE`.

When something is measured locally:

> Say `LOCAL MEASUREMENT`.

Do not convert inference into fact.

---

# 3. FIRST: INSPECT THE CURRENT REPOSITORY

Before reading or changing anything, inspect:

```text
git status
git branch
git log --oneline --decorate -20
git remote -v
git diff
```

Verify:

### origin

`https://github.com/rohitkumarnaidu/AffordAI.git`

### upstream

`https://github.com/interviewstreet/hackerrank-orchestrate-september26.git`

Run:

```bash
git fetch upstream
```

ONLY if required for inspection.

Do not pull or merge upstream.

---

# 4. READ THE COMPLETE LOCAL REPORT SET

Read every available project/research document relevant to this challenge.

At minimum inspect:

## Existing project docs

- `AGENTS.md`
- `README.md`
- `docs/specification.md`
- `docs/decision-matrix.md`
- `docs/data-model.md`
- `docs/architecture.md`
- `docs/evaluation-strategy.md`
- `docs/threat-model.md`
- `docs/interview-notes.md`
- `docs/build-checklist.md`

## Prior Orchestrate learning docs

Read every file under:

`docs/Learnings/`

Do not skim only filenames.

## Uploaded research / planning materials where available

Read the complete contents of:

- `AffordAI_AGENTS_Final_Build_Contract_Prompt...`
- `AffordAI_Orchestrate_September_Final_Integrated_Master...`
- `Orchestrate_Integrated_Master_Research...`
- `Orchestrate_Final_Action_Plan...`
- `The Orchestrator's Blind Spot...`
- `From Competitor to Contender...`
- `Anatomy of an Orchestrate Defeat...`
- `Beyond Code...`
- `AffordAI_Complete_Winning_Implementation_Checklist...`

If the current workspace already contains an equivalent integrated copy, prefer the current repository version.

Do not blindly duplicate these reports into the repository.

---

# 5. BUILD A REPORT-RECONCILIATION MATRIX

Create an internal table:

| Topic | Report Claim | Current Repo Evidence | Official Evidence | Final Status |
|---|---|---|---|---|

At minimum inspect:

- deterministic core
- AI boundary
- financial simulation
- payment-plan logic
- evidence grounding
- output validation
- transcript
- interview
- token usage
- hidden-test strategy
- security
- ranking
- plan optimization
- previous mistakes

Do not let old reports override official September rules.

---

# 6. READ THE OFFICIAL SEPTEMBER PROBLEM COMPLETELY

Read the entire official:

`problem_statement.md`

Do not stop after the output schema.

Extract every requirement.

Create a structured understanding of:

### Inputs

### Outputs

### Financial state

### 90-day safety rule

### Payment rules

### Partial payment

### Installments

### Spending changes

### User preferences

### Currency conversion

### Messages

### Images

### Conflicts

### Ranking

### Deadline behavior

### Submission artifacts

### Token/cost reporting

---

# 7. READ OFFICIAL AGENTS.MD COMPLETELY

Read:

`upstream/main:AGENTS.md`

or the fetched official file.

Extract every instruction that affects:

- session startup
- transcript logging
- `log.txt`
- per-turn logging
- tool identity
- secret redaction
- user prompts
- submission artifacts
- allowed tools
- repository behavior
- final submission

Do not replace official instructions with assumptions from the earlier reports.

---

# 8. FULL DATASET INSPECTION

The official challenge dataset is the operational source for implementation.

Inspect every supplied participant-facing CSV.

At minimum:

```text
dataset/official/
```

Inspect:

- `requests.csv`
- `sample_requests.csv`
- `financial_profiles.csv`
- `financial_events.csv`
- `request_payment_options.csv`
- `exchange_rates.csv`
- `messages.csv`
- `images.csv`
- any additional CSV actually present in the official repository

Do NOT alter them.

---

# 9. DATASET INVENTORY — COMPLETE

For every CSV produce:

### File metadata

- row count
- column count
- column names
- encoding
- delimiter
- inferred data types

### Quality

- null counts
- duplicate counts
- unique counts
- unexpected values
- min/max
- date range
- currency distribution

### Relationships

- candidate primary keys
- foreign keys
- one-to-one
- one-to-many
- many-to-one
- invalid references
- orphan records

### Temporal

- earliest date
- latest date
- recurrence patterns
- settlement patterns
- request-to-event relationships

---

# 10. REQUESTS.CSV

Inspect every column.

Determine:

- request identity
- user identity
- requested amount
- currency
- request date
- desired completion date
- payment method preference
- partial-payment preference
- installment preference
- priority fields
- any other field actually present

Create examples of unusual requests.

---

# 11. FINANCIAL_PROFILES.CSV

Determine exactly:

- current balance
- minimum balance
- home currency
- essential categories
- flexible categories
- protected categories
- spending-change preferences
- payment preferences
- installment constraints
- maximum installment months semantics

Do NOT assume blanks mean zero or unlimited.

Measure actual dataset behavior.

---

# 12. FINANCIAL_EVENTS.CSV

Enumerate all actual statuses.

Enumerate all actual event types.

Determine:

- settled
- pending
- scheduled
- cancelled
- failed
- unrealized
- or any other actual values

Inspect:

- amount nulls
- currencies
- dates
- recurrence
- flexibility
- minimum allowed amounts
- linked event IDs
- related event IDs
- user IDs
- source IDs

### Specifically investigate

- duplicate patterns
- linked-event patterns
- contradictory patterns
- blank amount rows
- future events
- past events
- recurring events

---

# 13. REQUEST_PAYMENT_OPTIONS.CSV

Inspect:

- options/request
- payment methods
- option IDs
- number of payments
- intervals
- fees
- schedule dates
- installment months
- supported/unsupported patterns

Determine exact real-world distributions.

Do not infer from one row.

---

# 14. EXCHANGE_RATES.CSV

Inspect:

- all currencies
- all directed pairs
- date ranges
- duplicate date/pair records
- missing dates
- missing pairs
- pre-window coverage
- rate direction

Do NOT decide a fallback policy unless the official challenge or data clearly supports one.

Report the evidence.

---

# 15. MESSAGES.CSV

Inspect:

- all source types
- language distribution
- request linkage
- event linkage
- message chronology
- repeated message patterns
- cancellation wording
- amendment wording
- delay wording
- settlement wording
- preference wording
- suspicious instruction patterns

Determine whether a deterministic parser can safely handle a subset.

Do not add an LLM yet.

---

# 16. IMAGES.CSV + MEDIA FILES

Inspect:

- image count
- event-to-image mapping
- image IDs
- missing images
- duplicate images
- image formats
- dimensions
- file sizes
- linked events

Open/inspect every supplied image if technically possible.

Create a complete image inventory.

For every image, identify:

- event ID
- likely financial value
- currency if visible
- date if visible
- relevance
- whether the image contains the missing amount needed by the challenge

Do NOT store fabricated OCR values.

If OCR/model extraction is uncertain, mark it as uncertain.

---

# 17. BLANK-AMOUNT INVESTIGATION

Determine:

> Exactly how many financial-event rows have blank amounts?

For each blank row identify:

- event ID
- user
- related image
- image existence
- extracted value, if independently verified
- extraction confidence
- downstream impact

Do not treat blank as zero.

---

# 18. IMAGE EXTRACTION PLAN

Before implementing image intelligence, determine:

- how many cases actually require images
- whether image values can be extracted reliably
- whether deterministic preprocessing/OCR is sufficient
- where multimodal AI is truly necessary
- how extracted values will be validated

Do not add vision to every request.

---

# 19. RECURRENCE INVESTIGATION

Determine actual recurrence semantics.

Inspect:

- frequency/cadence fields
- start date
- end date
- next occurrence
- day-of-month
- weekly/monthly/other behavior

Identify all distinct patterns in the actual data.

Document how each maps into the 90-day forecast.

---

# 20. FINANCIAL STATE MODEL

Before coding, build a formal description of the canonical financial state.

At minimum:

```text
home_currency
current_balance
minimum_balance
confirmed_income
essential_expenses
flexible_expenses
existing_commitments
pending_debits
valid future events
resolved evidence
```

Document what is excluded and why.

---

# 21. EVENT-LIFECYCLE MODEL

Build a deterministic state-transition model for financial events.

For every actual status:

```text
status
→ included?
→ amount source?
→ date used?
→ balance impact?
→ forecast impact?
```

Cover:

- settled
- pending
- scheduled
- cancelled
- failed
- unrealized
- all other observed states

---

# 22. CONFLICT-RESOLUTION VALIDATION

Verify the actual September rule and apply it deterministically.

Create concrete examples from the dataset.

For each conflict demonstrate:

```text
source evidence
→ precedence decision
→ normalized state
```

Do not ask an LLM to choose between conflicting financial records.

---

# 23. CURRENCY RULE VALIDATION

Before implementation, verify the actual dataset and official wording around:

- directed pair
- settlement date
- rate availability
- pre-window event
- missing-rate behavior
- output currency

Do not silently implement an invented fallback.

Any assumption must be explicitly documented and marked for verification.

---

# 24. 90-DAY FORECAST SPECIFICATION

Produce the mathematical model before implementation.

Define:

```text
opening balance
+ valid inflows
- valid outflows
- candidate payment
= closing balance
```

State the exact dates on which transactions affect balance.

Define:

```text
closing_balance(date) >= minimum_balance
```

for every relevant projected day.

Identify:

- inclusive/exclusive boundaries
- request-date treatment
- settlement-date treatment
- recurring event treatment
- deadline treatment

---

# 25. AMOUNT-SAFE-TO-PAY SPECIFICATION

Define it mathematically.

Verify:

```text
0 <= amount_safe_to_pay <= requested_amount
```

and:

> maximum amount payable today before optional spending changes while preserving all required future constraints.

Determine the safest implementation strategy from the actual constraints.

Do not choose binary search unless the monotonicity required for it is actually established.

---

# 26. EARLIEST FULL-PAYMENT DATE

Define:

> first date on which the full requested amount can be paid safely in one payment without optional spending changes.

Check:

- safe today
- safe later
- never safe
- deadline conflict

Do not mix this calculation with payment-method preference.

---

# 27. PAYMENT-PLAN SPECIFICATION

Define exact candidate types:

- full payment
- partial payment
- installments
- wait
- not recommended

For every type specify:

- eligibility
- payment schedule
- safety
- deadline
- user preference
- output format

---

# 28. PARTIAL-PAYMENT SPECIFICATION

Verify the exact official conditions.

Ensure the implementation will check:

- partial allowed
- user accepts
- safe amount > 0
- safe amount < requested
- earliest full-payment date <= desired completion date
- exactly two payments
- first = safe amount
- second = remainder
- sum = requested amount

---

# 29. INSTALLMENT SPECIFICATION

Ensure installment schedules are copied exactly from supplied payment options.

Never invent a schedule.

Validate:

- option ID
- dates
- payment count
- amount
- fee
- eligibility
- deadline
- safety

---

# 30. SPENDING-CHANGE SPECIFICATION

Verify actual profile semantics before coding.

Investigate:

- flexible
- reducible
- stoppable
- reducible_or_stoppable
- minimum allowed amount
- protected categories

Then implement only officially permitted changes.

---

# 31. PLAN-RANKING SPECIFICATION

Verify the exact official six-step ranking.

The ranker must be deterministic.

Build examples for every tie-break layer.

Do not let an LLM rank plans.

---

# 32. USER-PREFERENCE SPECIFICATION

Verify exactly how:

- accepted payment methods
- partial payment
- installments
- maximum installment months
- flexible spending adjustments
- priorities

affect eligibility.

Separate:

> financial feasibility

from:

> user preference eligibility.

---

# 33. AI-BOUNDARY AUDIT

Before adding any model call, classify each operation:

| Operation | Deterministic | AI Candidate | Why |
|---|---:|---:|---|
| CSV join | ✓ |  | structural |
| balance arithmetic | ✓ |  | exact |
| date calculation | ✓ |  | exact |
| FX | ✓ |  | exact |
| 90-day forecast | ✓ |  | exact |
| plan ranking | ✓ |  | exact |
| message semantics |  | ✓ | unstructured |
| image amount |  | ✓ | visual |
| explanation |  | optional | language generation |

Then verify every AI candidate actually needs AI.

---

# 34. NO-LLM BASELINE

Before any AI integration, the system must have a deterministic baseline.

The baseline should:

- load data
- construct state
- process structured evidence
- forecast
- generate candidate plans
- validate
- rank
- produce output

This becomes E0.

---

# 35. LOCAL EVALUATION BASELINE

Use the 25 solved sample requests as a local proxy where the official sample provides enough information to calculate expected behavior.

Do NOT claim:

> sample accuracy = HackerRank score.

Call it:

> `LOCAL PROXY`

Track:

- structural validity
- decision correctness
- plan correctness
- numerical correctness
- evidence correctness

---

# 36. ABLATION PLAN

Only after E0:

## E1
Add message semantic interpretation.

## E2
Add image interpretation.

## E3
Add semantic conflict interpretation if actually useful.

## E4
Improve plan optimization.

## E5
Add grounded explanation generation.

## E6
Strengthen validation.

## E7
Optimize model calls/tokens.

For each stage record:

- what changed
- why
- measured result
- token cost
- runtime
- failure delta

---

# 37. VALIDATION LAYERS

Define these explicitly:

## Layer 1 — Input Integrity
- [ ] request count
- [ ] request IDs
- [ ] original index
- [ ] user IDs

## Layer 2 — Join Integrity
- [ ] valid references
- [ ] correct ownership
- [ ] no duplicate joins

## Layer 3 — Evidence Integrity
- [ ] source exists
- [ ] evidence belongs to request
- [ ] normalized fact valid

## Layer 4 — Financial Invariants
- [ ] balance floor
- [ ] payment total
- [ ] date rules
- [ ] deadline

## Layer 5 — Plan Integrity
- [ ] valid plan
- [ ] user eligibility
- [ ] exact supplied installment option
- [ ] spending changes valid

## Layer 6 — Decision Consistency
- [ ] status
- [ ] method
- [ ] plan
- [ ] earliest date
- [ ] spending changes

## Layer 7 — Output Integrity
- [ ] exact columns
- [ ] exact row count
- [ ] exact order
- [ ] no duplicates

---

# 38. OUTPUT-ORDER PROTECTION

Explicitly build:

```text
original_index
request_id
```

into every request context.

At final serialization:

```text
sort by original_index
```

Then compare:

```text
input_request_ids
==
output_request_ids
```

This is a mandatory regression gate.

---

# 39. DECISION TRACE

For each request, provide an inspectable internal trace:

```text
request
→ joined data
→ evidence
→ normalized facts
→ financial state
→ forecast
→ candidate plans
→ rejected plans + reasons
→ selected plan
→ final decision
→ output row
```

Do not rely on LLM reasoning traces.

This is an engineering trace.

---

# 40. REJECTION REASONS

For every rejected plan record a structured reason:

- unsafe
- deadline violation
- user preference violation
- invalid payment option
- spending-change violation
- incomplete
- other official reason

This makes plan ranking auditable.

---

# 41. FAILURE TAXONOMY

Create categories:

### DATA
- malformed
- missing
- duplicate

### JOIN
- missing reference
- wrong ownership
- cross-request contamination

### EVIDENCE
- missing
- irrelevant
- contradictory
- low-confidence extraction

### FINANCE
- balance
- date
- currency
- recurrence

### PLAN
- schedule
- safety
- deadline
- preference

### OUTPUT
- schema
- ordering
- consistency

### AI
- timeout
- invalid JSON
- low-confidence
- hallucinated fact

Every bug must be assigned one category.

---

# 42. REGRESSION POLICY

Every discovered bug becomes a permanent regression test.

Required record:

```text
failure
→ expected
→ actual
→ root cause
→ fix
→ regression test
```

Do not simply patch the failing row.

---

# 43. ADVERSARIAL SUITE

Build test cases for:

## Financial
- [ ] exact balance floor
- [ ] just above floor
- [ ] just below floor
- [ ] zero safe amount
- [ ] full safe amount

## Temporal
- [ ] same-day
- [ ] deadline day
- [ ] day after deadline
- [ ] 90-day boundary
- [ ] future salary

## Evidence
- [ ] conflicting message
- [ ] cancellation
- [ ] amendment
- [ ] misleading message
- [ ] prompt injection
- [ ] image-only amount
- [ ] unreadable image

## Data
- [ ] duplicate event
- [ ] missing event
- [ ] invalid reference
- [ ] missing FX

## Payment
- [ ] partial
- [ ] installment
- [ ] wait
- [ ] impossible plan
- [ ] preference rejection
- [ ] tie-break

---

# 44. SECURITY

Verify:

- [ ] no secrets
- [ ] `.env` ignored
- [ ] `.env.example`
- [ ] no secrets in transcript
- [ ] no secrets in trace
- [ ] prompt injection cannot override financial rules
- [ ] external evidence cannot override system rules

---

# 45. TOKEN / COST SYSTEM

Before production model use define:

- how calls are counted
- how tokens are measured
- how provider/model are recorded
- how per-request usage is tracked
- how total usage is calculated
- how cost is estimated

Do not fabricate cost estimates.

---

# 46. PERFORMANCE / PARALLELISM

Before introducing parallel processing:

verify:

- request isolation
- deterministic output ordering
- no shared mutable state
- trace safety
- reproducibility

Parallelism must never reintroduce the row-order bug.

---

# 47. CLEAN-ROOM PLAN

Define exact final workflow:

```text
fresh environment
→ install
→ configure environment
→ load official dataset
→ run pipeline
→ generate output.csv
→ validate output
→ run evaluation
→ produce usage_report.md
```

Identify every external dependency.

---

# 48. TRANSCRIPT STATUS — CRITICAL

Now inspect the current transcript.

## FIRST CHECK

Determine whether:

```text
log.txt
```

already exists in the current AffordAI repository root.

If it exists:

> KEEP IT.

Do NOT create a second transcript.

Do NOT rename it.

Do NOT rewrite it.

Do NOT truncate it.

Do NOT replace it with a summary.

If the official September instructions specify a different exact transcript path/handling, follow those official instructions.

---

# 49. SHOULD WE CREATE THE TRANSCRIPT NOW OR LATER?

## ANSWER

**NOW.**

The transcript is part of the actual competition build process.

Do not wait until the end.

The remaining OpenCode sessions should be recorded continuously.

The official Orchestrate guidance says the transcript is evidence of how the participant directed AI: planning, constraints, implementation, review, debugging, iteration, and architectural decisions.

Therefore:

> Start/continue transcript logging immediately.

---

# 50. WHAT ABOUT EVERYTHING WE ALREADY DID?

Do NOT fabricate historical transcript entries.

This is critical.

If `log.txt` already contains the previous OpenCode sessions:

> preserve everything exactly.

If previous sessions were logged but incomplete:

> preserve existing content and continue from now.

If there is NO usable historical log:

> do not invent exact prompts, tool names, timestamps, or actions.

Instead append ONE clearly labelled historical context entry such as:

```text
PREVIOUS WORK CONTEXT — NOT A RETROACTIVE TRANSCRIPT

This entry summarizes previously completed repository work.
It is not presented as a verbatim transcript.

Known completed work:
- repository initialization
- origin/upstream configuration
- official dataset inventory
- specification documents
- AGENTS.md
- validators
- tests
- research/learning documentation
- build checklist

Exact prior prompts/timestamps/tool interactions are not reconstructed.
Future sessions will follow the official transcript format.
```

Only use this summary if it is genuinely necessary.

Never fabricate a fake turn-by-turn history.

---

# 51. TRANSCRIPT CONTENT WE WANT FROM NOW ON

The genuine build should naturally demonstrate:

```text
PROBLEM
→ SPEC
→ DATA INSPECTION
→ ARCHITECTURE
→ IMPLEMENTATION
→ TEST
→ FAILURE
→ DIAGNOSIS
→ FIX
→ REGRESSION
→ EVALUATION
→ FINAL VALIDATION
```

Good examples:

> "Implement the timeline engine according to `docs/specification.md`. Do not change the business rules. Add tests for the exact minimum-balance boundary."

Then:

> "Run the 25 solved samples. Show mismatches grouped by rule."

Then:

> "This failure appears to be a recurrence-date issue. Identify the root cause before changing the code."

This is much stronger evidence of human-led engineering than:

> "Build everything."

---

# 52. GIT COMMIT / TRANSCRIPT RELATIONSHIP

Commits should reflect genuine implementation milestones.

Recommended style:

```text
chore: initialize project
docs: define challenge specification
data: add dataset inventory
feat: add canonical financial state
feat: add forecast engine
test: add forecast boundary cases
feat: add payment plan engine
test: add plan invariants
feat: add evidence layer
test: add adversarial evidence cases
```

Do not manufacture commits simply to create an appearance of activity.

---

# 53. DO NOT COMMIT `log.txt`

Unless the official September instructions explicitly require it in source control:

- keep `log.txt` local
- keep it append-only
- submit it through the prescribed HackerRank mechanism

Follow the official current instruction if it differs.

---

# 54. FINAL INSPECTION REPORT

Before beginning Milestone 2, produce:

# SECTION A — Repository State

- branch
- status
- remotes
- commit count
- current tree

# SECTION B — Documentation State

- docs present
- docs missing
- contradictions

# SECTION C — Official Challenge State

- official files read
- official rules captured
- unresolved official ambiguities

# SECTION D — Dataset State

- all CSV counts
- all schemas
- nulls
- duplicates
- joins
- unusual cases

# SECTION E — Image State

- image count
- mappings
- blank amounts
- extraction plan

# SECTION F — Deterministic Core

- required modules
- exact responsibilities
- invariants
- open questions

# SECTION G — AI Boundary

- AI tasks
- deterministic tasks
- prohibited AI tasks

# SECTION H — Validation

- validators
- tests
- regression
- adversarial

# SECTION I — Evaluation

- local proxy
- baseline
- ablation plan

# SECTION J — Transcript

- log path
- exists?
- current state
- whether logging is functioning
- whether historical entries exist
- whether any reconstruction is necessary

# SECTION K — Risk Register

For each risk:

- likelihood
- impact
- detectability
- mitigation
- status

---

# 55. FINAL GO / NO-GO

At the end of the inspection say:

## GO

Only when:

- official contract understood
- dataset understood
- open ambiguities identified
- deterministic core specified
- AI boundary specified
- validation strategy specified
- transcript functioning
- Milestone 2 scope is clear

## NO-GO

If:

- a critical official rule is unknown
- a key dataset relationship is unresolved
- a major financial invariant is undefined
- transcript logging is not functioning
- implementation would require guessing

---

# 56. IMPORTANT: DO NOT ASK ME TO REPEAT KNOWN INFORMATION

Use the repository and supplied reports first.

Do not ask me to restate:

- project name
- repository
- challenge
- architecture philosophy
- previous lessons
- checklist
- known feedback

Only ask a question if the actual evidence cannot resolve it.

---

# 57. AFTER INSPECTION

Do NOT automatically start implementing everything.

After the inspection, recommend the exact next build sequence.

Default expectation:

```text
1. typed ingestion
2. canonical request context
3. financial state
4. currency engine
5. temporal engine
6. 90-day simulator
7. candidate payment plans
8. invariants
9. optimizer
10. 25-sample local evaluation
```

Then stop for review before adding LLMs.

---

# 58. ULTIMATE PRINCIPLE

The project should follow:

```text
UNDERSTAND
→ SPECIFY
→ VERIFY DATA
→ BUILD DETERMINISTIC CORE
→ TEST
→ MEASURE
→ ADD TARGETED AI
→ VALIDATE
→ REGRESSION
→ ADVERSARIAL TEST
→ FULL RUN
→ CLEAN ROOM
→ PACKAGE
→ INTERVIEW
→ SUBMIT
```

The objective is not maximum complexity.

The objective is maximum reliable correctness under the exact September challenge.

---

# 59. FINAL COMMAND

Start the inspection now.

Read:

1. current `AGENTS.md`
2. all current project docs
3. every `docs/Learnings/*` report
4. all supplied Orchestrate research reports
5. official September `AGENTS.md`
6. official September `problem_statement.md`
7. every participant-facing CSV
8. every supplied image
9. current source skeleton
10. existing tests/validators
11. current Git history
12. current `log.txt`, if present

Then produce the complete inspection report.

Do not implement the full financial engine during this inspection.

Do not invent missing information.

Do not overwrite or fabricate transcript history.

After the report, provide the exact Milestone 2 implementation order and the first bounded coding task.

# END
