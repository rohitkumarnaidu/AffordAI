# Decision Matrix — input → output rules

Companion to `specification.md`. No code may contradict this file.

## A. Status × method allowed pairs

| status | allowed methods | notes |
|---|---|---|
| `affordable_now` | `full_payment` | full safe today + user accepts full; `earliest == request_date`; plan = `request_date:requested` |
| `affordable_with_plan` | `partial_payment` (strict 5-conds), `installments` (exact option match), `full_payment` iff spending changes make today safe | full completed via plan/changes |
| `affordable_later` | `wait` | full safe later ≤ forecast; plan = `earliest:requested` (single future payment); `earliest > request_date` |
| `not_affordable` | `not_recommended` | plan `none`, changes `none`; `earliest` empty OR later capacity date (see note); `safe` may be >0 but < requested |

`partial_payment ⇒ affordable_with_plan` (never with other statuses).
`earliest` measures capacity independently of preferences/deadline (Tier 1):
it may be set even for `not_affordable` (capacity exists later, e.g. past the
deadline, but no eligible plan completes safely) or equal `request_date` under
installments. Empty `earliest` ⇔ full payment never safe within forecast.
`wait` plan is a single future full payment on `earliest`, NOT an installment schedule.

## B. Method eligibility (before ranking)

- `full/partial/installments` require membership in `payment_methods_user_will_consider`.
- `installments` additionally require `max_installment_months` non-blank and option term compatible;
  option may still be rejected on preference/term conflict.
- Partial additionally requires `allows_partial_payment == true`, `0 < safe < requested`,
  `earliest <= desired_completion_date`, exact 2-payment shape summing to requested.
- `wait` requires future-safe full + user accepts `full_payment`.
- Else `not_recommended` (`none`, changes `none` unless changes alone can't complete → still `none`).

## C. 90-day gate (every candidate)

Simulate with essentials + recurring + confirmed futures + candidate payments.
REJECT candidate if any day `closing < minimum`, or completion `> desired_completion_date`
(except `not_recommended`), or FX/date arithmetic unvalidated.

## D. Ranking (first match wins)

1. completes by deadline 2. no spending changes 3. min total paid (incl. fees)
4. earlier first-payment date 5. fewer payments 6. lowest `payment_option_id`.

### Diagram 4 — Ranking 6-tuple optimizer rank_key (code-verified, finance optimizer)

Eligible safe candidates are ranked by `optimizer.rank_key(candidate, deadline)` 6-tuple.

```mermaid
flowchart TD
    A["eligible safe candidates"] --> B["Step1 complete by deadline?"]
    B --> C["Step2 no spending changes?"]
    C --> D["Step3 min total_paid incl fees"]
    D --> E["Step4 earlier first payment date"]
    E --> F["Step5 fewer payments"]
    F --> G["Step6 lowest payment_option_id"]
    G --> H["None sorts as tilde last"]
    H --> I["rank_key tuple sorted"]
    I --> J["select winner deterministic"]
    J --> K["tie break lowest option_id"]
```

## E. Spending changes

Only flexible recurring events in willing categories; ≤3; no same-event stop+reduce;
each change re-simulated (must flip an unsafe plan safe or be omitted).

## F. Conflicts

cancel/settle/amend > newer same-source > settled > safer. LLM never reorders this.

## G. Amounts/dates

`0 <= safe <= requested`; `safe` computed WITHOUT optional changes; `earliest` WITHOUT
optional changes; quantized in home currency to 2dp for all five currencies
(sample evidence: IDR amounts carry 2dp, e.g. `15952906.67`).
