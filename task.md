# nylonpay-py — Python SDK Implementation

**Spec version:** 1.3.0
**Package:** `nylonpay-py` on PyPI
**Reference implementation:** `packages/sdks/typescript/` (TS SDK v1.2.0)
**Canonical spec:** `packages/specs/nylonpay-sdk-spec/`

## Tooling Stack (agreed 2026-06-21)

| Concern | Tool |
|---------|------|
| PM + venv + deps + lockfile + build + publish | uv |
| Lint + format | ruff |
| Type check | ty |
| Test runner | pytest + pytest-asyncio |
| HTTP client (only runtime dep) | httpx |
| Runtime validation | dataclasses + manual fns (no pydantic) |
| Crypto | stdlib (hmac, hashlib, secrets) |
| Result type | custom (~30 lines, mirrors slang-ts) |
| Build backend | hatchling |
| Type marker | py.typed (PEP 561, spec requirement) |
| Task runner | poethepoet (scripts in pyproject.toml) |
| Python floor | 3.10 |

**Runtime deps: 1** (httpx). Dev deps: ruff, ty, pytest, pytest-asyncio, poethepoet.

## Phases

### Phase 1 — Foundation
- [ ] `pyproject.toml` — package config + all tool config + poe tasks
- [ ] Project skeleton — dirs, `py.typed`, `__init__.py` stub, `.env.example`, `LICENSE`, `README.md` stub
- [ ] `result.py` — Result[T, E] + Ok/Err factories + is_ok/is_err/value/error
- [ ] `types.py` — all frozen dataclasses for spec types (27+ types)
- [ ] `config.py` — constants, defaults, SDK_ACTIONS map, RETRYABLE_STATUS_CODES

### Phase 2 — Crypto & Utilities
- [ ] `nonce.py` — generate_nonce (secrets.token_hex, 16 bytes → 32 hex chars)
- [ ] `fingerprint.py` — generate_fingerprint (SHA-256 of OS/runtime metadata)
- [ ] `signature.py` — JCS canonical payload (RFC 8785), HMAC-SHA256 signing
- [ ] `phone.py` — normalize_phone, is_valid_phone_format
- [ ] `verify_response.py` — response HMAC verification (constant-time)
- [ ] `pubsub.py` — event emitter (on/once/off/emit)

### Phase 3 — Transport
- [ ] `transport.py` — async HTTP (httpx), Nile envelope, HMAC signing per attempt, retry with jitter, response verification (fail-closed), error parsing (category suffix split), create_sdk_error

### Phase 4 — SDK Core
- [ ] `factory.py` — create_nylon_pay, singleton cache (key: apiKey:baseUrl:sha256(secret)[:16]), key prefix validation (npk_/nps_)
- [ ] `sdk.py` — 9 operations + validation helpers (validate_collection_amount, validate_payout_amount, validate_non_empty, validate_phone_format, resolve_reference, generate_reference, prepare_collect_payload, prepare_payout_payload, apply_before_hook_mutation, run_hook)
- [ ] `payment.py` — PaymentInstance (async polling, events, wait(), terminal states, late-event guard, jittered interval, humanized timeout message)
- [ ] `verify_webhook.py` — webhook HMAC verification + replay guard (timestamp tolerance)

### Phase 5 — Barrel & Tests
- [ ] `__init__.py` — public exports (create_nylon_pay, verify_webhook_signature, create_sdk_error, parse_error, all types)
- [ ] Unit tests — co-located logic tests (mocked transport), mirror TS SDK test coverage
- [ ] Security tests — S1–S14 (mocked, no network)
- [ ] Integration tests — I1–I19 (real sandbox, .env-gated)
- [ ] README.md — full documentation

### Phase 6 — Quality Gate
- [ ] `uv run poe check` passes (lint + format-check + typecheck + test)
- [ ] All S1–S14 security tests pass
- [ ] All unit tests pass
- [ ] ty check clean
- [ ] ruff check clean
- [ ] `uv build` produces valid sdist + wheel

## Spec Compliance Checklist

- [ ] py.typed marker shipped
- [ ] All public APIs have docstrings (WHY not what)
- [ ] JCS canonical payload (RFC 8785) — code point sort, not locale
- [ ] Sign fresh per retry attempt (D19)
- [ ] Fail-closed response verification (D15)
- [ ] Constant-time comparison (hmac.compare_digest)
- [ ] Humanized error messages (no internal mechanics)
- [ ] Phone normalization (strip ws → strip + → prepend 256 if 0+10 digits)
- [ ] Reference 13–15 chars validation
- [ ] Amount minimums (collections ≥ 500, payouts ≥ 5000)
- [ ] Factory pattern (create_nylon_pay returns object with 9 callables)
- [ ] Named params everywhere (dict/dataclass params, no positional)
- [ ] snake_case public API, PascalCase types, UPPER_SNAKE constants
- [ ] No classes for behavior — functions + closures
- [ ] Dataclasses for data types (frozen=True)
- [ ] Async everywhere (async def for all 9 ops)

## Key Decisions

- **No pydantic** — dataclasses + manual validation, mirrors TS SDK. Add only if response parsing hits a wall.
- **No build step for dev** — Python is interpreted. Lint + type-check + test only. Build (uv build) for PyPI shipping.
- **poethepoet** for scripts — closest to package.json scripts. Defined in pyproject.toml [tool.poe.tasks].
- **Package name: nylonpay-py** on PyPI. Import name: `nylonpay`.
- **Python 3.10+** — X|Y unions, match/case.
- **Version: 0.1.0** — pre-release during development. Bump to 1.0.0 when spec-compliant + all tests pass.
