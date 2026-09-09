# Bilibili translation recovery implementation plan

**Goal:** Keep successful work across translation failures and restarts, reduce duplicate requests, and bound network waits.

**Architecture:** Preserve the existing web/CLI entry points. Add a local SQLite store for translation chunks, audio transcripts, and cross-process provider scheduling; add explicit HTTP adapters; integrate partial results into the existing pipeline. Library extraction follows on a separate branch after this change is verified.

**Spec:** The project analysis and implementation sequence approved in the conversation on 2026-09-09.

**Constraints:** Python >=3.10; existing CLI/web behavior remains available; no paid backend; no live translation calls in automated tests; no cookies/email saved in tracked files; preserve unrelated untracked directories. Work in the user-authorized feature branch, not a new worktree. Tasks share interfaces and execute sequentially in this session.

## Task 1: Durable work and request scheduling

Files: `tools/bilibili-subtitles/translation_store.py`, `tests/test_bilibili_translation_recovery.py`.

- [x] Write failing tests for reopening a cache, language/backend isolation, transcript persistence, shared request spacing and cooldown.
- [x] Run `python -m pytest tests/test_bilibili_translation_recovery.py -q` and verify missing behavior.
- [x] Implement `TranslationStore(path).get/put(namespace, key, value)`, `wait_turn(provider, interval)`, `cooldown(provider, seconds, reason)` using SQLite transactions. No lock held during sleep/network IO.
- [x] Verify tests. Default store lives under ignored `outputs/.cache/`; `BILIBILI_CACHE_DIR` isolates tests/custom storage.

## Task 2: HTTP adapters and translation recovery

Files: `translation_backends.py`, `direct_generate.py`, recovery tests.

- [x] Write failing tests: request timeout, HTTP/JSON quota errors, Retry-After, UTF-8 byte split, repeated text deduplication, partial success followed by failure and rerun.
- [x] Implement Google web/MyMemory HTTPS adapters with explicit connect/read timeouts, typed permanent/quota/rate-limit errors, and bounded retries. Preserve existing injectable tuple backend API for compatibility.
- [x] Persist validated chunks before proceeding; cache identity includes provider version and language direction. Only cache success. Return partial results in a RuntimeError subtype on incomplete batches.
- [x] Verify existing backend-chain and retry tests plus new recovery tests.

Expected recovery behavior:

```python
# Backend succeeds for A and fails for B on run 1.
# Run 2 requests only B; cache provides A.
assert requested.count('A') == 1
assert recovered == ['译A', '译B']
```

## Task 3: Web/CLI and transcript recovery

Files: `direct_generate.py`, `app.py`, `static/app.js`, README, tests.

- [x] Write failing tests for cached audio transcripts across calls/model isolation, partial web/CLI export, and incomplete-language status.
- [x] Save audio transcript immediately after successful recognition, before translation. Repeating the same URL/model reuses it; log cache hits. Translation cache restores successful chunks on rerun after restart.
- [x] On translation exceptions retain partial rows and provenance; display the retry action even if some Chinese rows exist. Keep original audio and synthesized audio timelines distinct.
- [x] Update user documentation with cache location, recovery steps, quota vs rate-limit behavior and limits.
- [x] Run full root Python suite and JS syntax check; review diff. No publish, merge, or live service restart.

## Progress

- Baseline: 85 tests passed (bilibili + TTS) before implementation.
- Email configured in the user's Windows account and read back successfully; not written to repository.
- Branch: `feature/bilibili-translation-cache-resume`, base `3a91a67`.
- Verification: `python -m pytest -q` — 158 passed; Python `compileall`, `node --check tools/bilibili-subtitles/static/app.js`, and `git diff --check` — exit 0.
- Review fix: recheck account quota after provider pacing; normalize MyMemory warning text before quota detection.
- Final review fix: SQLite scheduling failure falls back to process-local pacing/cooldown; partial retries keep an incomplete marker; subtitle-track documentation matches the actual web/CLI behavior.
