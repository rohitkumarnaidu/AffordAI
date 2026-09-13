# Data Model

## Entities

- **requests** (`request_id` PK): `user_id FK`, `request_date`, `request_type`, `requested_amount`,
  `desired_completion_date`, `allows_partial_payment`, `request_text`.
- **profiles** (`user_id` PK): `home_currency`, `current_available_balance`, `minimum_balance_to_keep`,
  priorities, `expense_categories_to_protect`, `..._willing_to_reduce/_stop`,
  `payment_methods_user_will_consider`, `max_installment_months` (blank = no installments).
- **financial_events** (`event_id` PK): `user_id FK`, `event_type`, `description`, `category`,
  `direction (debit|credit)`, `amount` (nullable → image), `currency`, `event_date`,
  `settlement_date`, `status` (settled|pending|scheduled|failed|cancelled|unrealized… — confirm in inventory),
  `linked_event_id` (→ earlier event, same lifecycle; link alone ≠ cash-flow verdict),
  `flexibility (fixed|flexible…)`, `minimum_allowed_amount`.
- **request_payment_options** (`payment_option_id` PK): `request_id FK`, schedule
  (`payment_amount × number_of_payments`, `first_payment_date`, `payment_frequency_days`),
  `financing_fee`, `total_payable_amount`.
- **exchange_rates**: (`rate_date`, `from_currency`, `to_currency`) → `rate`.
- **messages** (`message_id` PK): `user_id`, `request_id` (nullable), `related_event_id`
  (only when 1:1 to an event row), `sent_at`, `source_type`, `message_text` (multilingual).
- **images** (`image_id` PK): `user_id`, `request_id`, `related_event_id`; file
  `dataset/official/media/images/<image_id>.png`.
- **output** (`request_id` PK): 8 required columns (§spec 3).

## Joins

```text
requests.user_id → profiles.user_id (1:1 per request user)
requests.request_id → payment_options.request_id (1:2–4)
requests.request_id → messages.request_id (1:n, nullable) + users/messages by user_id
financial_events.event_id ↔ messages/images.related_event_id (1:n evidence)
financial_events.linked_event_id → financial_events.event_id (lifecycle chain)
FX: (settlement_date, currency → home_currency) → exchange_rates
```

## Canonical context (preserved end-to-end)

```python
RequestContext(original_index, request_id, user_id, request, profile,
               events, messages, images, payment_options, evidence)
```

## Temporal meaning

`event_date` = occurred/recorded; `settlement_date` = cash movement (forecast uses this).
`request_date` = day-0 of 90-day window. `first_payment_date`/`frequency` define installment cash days.
`sent_at` orders message precedence. `desired_completion_date` = deadline gate.
`rate_date` matched to settlement date per §spec 2.

## Nullability

`financial_events.amount` nullable (→ image); `messages.related_event_id/request_id` nullable;
`max_installment_months` blank = refuse installments; `earliest_date` empty = never safe;
`payment_frequency_days` blank for single-payment options.
