# Changelog

All notable changes to this SDK. Versions follow [semver](https://semver.org).

## 1.2.1 - 2026-10-27

### Security
- The API key is no longer forwarded when the API (or a proxy in front of it) answers with a redirect to another origin, including an https -> http downgrade. Same-origin redirects keep working.
- The source distribution now ships only the package, tests and docs (no CI files).

## 1.2.0 - 2026-10-22

### Added
- `messages.send_batch()` - personalised bulk (`POST /v1/messages/batch`): a template with per-recipient `vars` (or full messages), schedule with timezone or recurrence, throttle, callback URL; an Idempotency-Key is generated per call.
- `campaigns` (create, list, get, update, delete, preview, prepare, review, test, launch, approve, reject, pause, resume, cancel, retry_failed, duplicate, report, stats, recipients, runs).
- `imports` (multipart file upload from a path, bytes or a file object; paste, Google Sheets, get, process, errors, recipients, save_to_group) and `jobs.get`.
- `contacts` (contact book by phone) and `groups` (CRUD + contacts).
- `templates` (CRUD, `starter_pack`, `use_starter`, `render`).
- `messages.cancel(id)` cancels a scheduled message and `messages.cancel_batch(batch_id)` a scheduled bulk batch; the charge is refunded.

### Fixed
- `send_bulk` sends an Idempotency-Key (generated when you do not pass one), so a retried bulk call can never send or charge the batch twice.

## 1.1.0 - 2026-10-14

First release since 1.0.0; it also ships the unreleased work below that was on `main`.

### Added
- Verify (managed OTP): `start` (with `app_id` and an automatic Idempotency-Key), `check`, `get`, `resend`, `cancel`, `list`, and Verify Apps CRUD plus per-app stats.
- Opt-outs: `list`, `add`, `remove`.
- Webhook signature helper (HMAC-SHA256, constant-time).
- Messages: `rate`, `validate`, `statuses`, `getBatch`, inline `recipients` for bulk sends, list filters (`to`, `batch_id`, `date_from`, `date_to`, `environment`).
- Send options `flash`, `validity_period`, `priority`, `binary`; bulk options `flash`, `validity_period`, `priority`, `skip_unavailable`.
- Routes expose `dial_code` and `region`.

### Fixed
- Safe retries: a POST is retried after a 5xx or network error only when it carries an Idempotency-Key (`messages.send` and `verify.start` always do), so a retry can never send or charge twice. 429 is always retried.
- Errors read the `{"error": {code, message, request_id}}` envelope, FastAPI 422 lists and rate-limit bodies; 402 maps to the insufficient-balance error.
- `InsufficientBalanceError.currency` is now filled in for live 402 responses (the API states the currency only in the message text).
- A 2xx response that is not JSON (for example an HTML page from a proxy) raises an SDK error instead of returning empty fields.
- `routes.list()`: a route without a default sender ID now reports `null`/`None` instead of the string `"null"`/`"None"`.
- `pytest` now runs from a fresh checkout without `PYTHONPATH=src`.

## 1.0.0 - 2026-07-29

- Initial release: `messages.send/schedule/list/get/retry/sendBulk`, `balance.get`, `routes.list`.
