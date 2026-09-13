# Join Integrity — AffordAI — 2026-09-13

Generated from actual `dataset/official/` inspection. Every relationship verified via `csv.DictReader` with partition-aware filtering (`eval 26..275` vs `full 01..275`). Dataset is READ-ONLY; no file modified.

## 1. Primary keys — uniqueness

| Key | Rows | Unique | Nulls | Dups | Verdict |
|---|---:|---:|---:|---:|---|
| `requests.request_id` | 250 | 250 | 0 | 0 | ✓ |
| `financial_profiles.user_id` | 275 | 275 | 0 | 0 | ✓ |
| `financial_events.event_id` | 25342 | 25342 | 0 | 0 | ✓ |
| `messages.message_id` | 215 | 215 | 0 | 0 | ✓ |
| `images.image_id` | 16 | 16 | 0 | 0 | ✓ |
| `request_payment_options.payment_option_id` | 790 | 790 | 0 | 0 | ✓ |
| `exchange_rates.(rate_date,from,to)` | 134 | 134 | 0 | 0 | ✓ |
| `output.request_id` (template) | 250 | 250 | 0 | 0 | ✓ |

0 malformed rows (len(row)==len(header) everywhere).

## 2. Foreign keys — expected vs actual

| Relationship | Expected | Actual (eval) | Orphans | Notes |
|---|---:|---:|---:|---|
| `requests.user_id → profiles.user_id` | 1:1 | 250/250 | 0 | `requests` 250 users ⊂ 275 profiles; `profiles∖requests` = 25 `user_01..user_25` (sample-only) |
| `requests.request_id → request_payment_options.request_id` | 1:2–4 | 250/250 covered, avg 2.876 (`3×165,2×58,4×27`) | 0 eval; 71 superset rows for `01..25` | `790 = 719 eval +71 sample` |
| `financial_events.user_id → profiles.user_id` | n:1 | 25342/25342 | 0 | All users have 56–129 events, avg 92.15 |
| `financial_events.linked_event_id → financial_events.event_id` | lifecycle | 58 links | 0 | 0 self-refs, 0 fan-in, chains intact (refund/valuation) |
| `messages.related_event_id → financial_events.event_id` | 1:1 nullable | 39/39 | 0 | 1 message per event (no many-to-1) |
| `images.related_event_id → financial_events.event_id` | 1:1 | 16/16 | 0 | Exact 1:1 to **blank-amount events** (see §3) |
| `messages.request_id → requests.request_id` | 1:n nullable | 116 distinct eval | 0 eval; 12 superset sample `03,04,06,08,10,11,15,16,18,20,22,23` | 87 blank `request_id` = user-level broadcasts (valid) |
| `images.request_id → requests.request_id` | 1:n nullable | 11 distinct eval | 0 eval; 5 superset sample `03,16,17,19,20` | Cross-check `image.user==request.user==event.user` 11/11 pass |
| `exchange_rates` lookup `(settlement_date,currency→home)` | date FX | 140 foreign events | 0 missing | 5 directed pairs cover all; `latest on/before` A1 |

Partition note: `request_payment_options`/`messages`/`images` contain rows for `request_01..25` (sample). Naïve join to `requests.csv` (eval only) shows 71+12+5 false orphans. Filter to `requests_ids = set(requests.request_id)` before counting; full-universe `requests ∪ sample_requests` = 275 explains all rows.

## 3. Blank-amount ↔ image bijection (critical)

- Blank `financial_events.amount` 16: `event_253,1442,1545,1700,1786,3051,3231,4535,5170,6033,6859,7307,7941,9421,9806,10521`
- `images.csv:related_event_id` 16: same set
- `media/images/*.png` 16: same set, 0 missing either direction
- `blank_ids == image_rels` (16), `images ↔ files` both directions 0 missing
- Overlap `messages ∩ images` on 3 events (`event_4535,7941,10521`) — different evidence types, not a violation (within-type still 1:1)

```python
import csv
blanks = {r['event_id'] for r in csv.DictReader(open('dataset/official/financial_events.csv')) if not r['amount'].strip()}
rels = {r['related_event_id'] for r in csv.DictReader(open('dataset/official/images.csv'))}
assert blanks == rels and len(blanks)==16
# disk check
import pathlib
assert len(list(pathlib.Path('dataset/official/media/images').glob('*.png')))==16
```

## 4. Payment-option integrity

- `payment_option_id` unique 790, no duplicate `(request_id,first_payment_date,number_of_payments)`
- Per-eval-request: `250 = 3×165 +2×58 +4×27`
- Exactly 1 `full_payment` per request (275/275 including sample)
- `installments` `total == amount * count` exactly; `financing_fee` 0 for singles, >0 for multis
- Foreign: 0 unsupported currencies, 0 events before `2023-10-15` need FX, 0 `settlement < event_date`

## 5. Message integrity

- `message_id` unique, `user_id` 0 orphans, `related_event_id` 0 orphans
- `request_id` nullable: 128 linked, 87 unlinked (user-level). Distribution `both 28, req_only 100, evt_only 11, neither 76` — all valid
- `sent_at` ISO `T09:30:00Z`, `source_type` 5 values, `message_text` 0 prompt-injection markup, 1 fraud lure `message_67` correctly untrusted
- 60 non-ASCII (ID), 0 replacement chars

## 6. Exchange-rate integrity

- 134 rows, 5 directed pairs, 39 dates `2023-10-15→2026-11-15` + `2025-10-01` outlier, 0 duplicate pairs, gaps 14–31d
- Foreign events 140 need FX: `USD→INR 54, USD→IDR 28, USD→EUR 22, EUR→ZAR 20, EUR→USD 16` — all covered, 0 missing prior rate
- Pre-window `702` events `<2023-10-15`: 0 need FX (by design); tail `request_113 2026-09-04+89d` exceeds `max_rate 2026-11-15` but 0 scheduled foreign beyond that

## 7. Orphan summary

- **True orphans (eval partition):** 0 in every relationship
- **False orphans (superset artifact):** `71` options + `12` messages + `5` images for `01..25` — valid against `sample_requests.csv`, not errors
- **Duplicate signatures:** 0 by `(user,desc,amount,currency,event_date,settlement,status)`
- **Many-to-many:** 0 unexpected; `messages`/`images` per-event strictly 1:0..1 (co-ref on 3 events allowed across types)

## 8. Verification commands

```bash
python3 -c "
import csv, pathlib
# superset check
req=set(r['request_id'] for r in csv.DictReader(open('dataset/official/requests.csv')))
samp=set(r['request_id'] for r in csv.DictReader(open('dataset/official/sample_requests.csv')))
opts=set(r['request_id'] for r in csv.DictReader(open('dataset/official/request_payment_options.csv')))
print('opts minus (req|samp)', opts-(req|samp))  # expect set()
# blank bijection
blanks={r['event_id'] for r in csv.DictReader(open('dataset/official/financial_events.csv')) if not r['amount'].strip()}
rels={r['related_event_id'] for r in csv.DictReader(open('dataset/official/images.csv'))}
print('blank==rels', blanks==rels)
"
# via validator (structural + plan layers)
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
```

## 9. Risks & mitigations

- **Superset join pitfall:** filter to `eval_ids` explicitly; log 88 superset rows as partition artifacts, not errors (see pipeline `RequestContext` and `output:serializer`).
- **FX inverse temptation:** never synthesize `IDR→USD` from `USD→IDR`; implement exact directed `latest on/before` (A1) with `FAIL CLOSED`.
- **1:1 assumption brittleness:** `related_event_id` not schema-enforced 1:1; code must not `dict[event]=message` (would drop second evidence).
- **Blank misdirected to requests:** 0 blank `requested_amount` — image resolver indexed by `financial_events.amount == ''`, not request.
