# Changelog

All notable changes to this SDK. Versions follow [semver](https://semver.org).

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
