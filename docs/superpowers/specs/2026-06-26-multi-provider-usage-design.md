# Multi-provider usage integration — design spec

**Date:** 2026-06-26
**Status:** Approved design (pending user spec-review + implementation plan next session)
**Goal:** Light up the three stubbed provider pages (Codex/ChatGPT, xAI, OpenCode) with real
usage data, alongside the live Claude page.

## Summary

The display already renders **provider pages** by **metric shape** (`quota`/`capped`/`spend`/
`balance`) — adding a provider was designed to be "a registry entry + a data collector, not
renderer changes." This spec covers the **data collectors** for three providers, using a
**unified client-push** architecture: the Pi stays a pure renderer with **no new secrets**, and
the user's machine gathers every provider's usage and POSTs one combined payload to the Pi
receiver (the same pattern already used for Claude's `/usage`).

User decisions (2026-06-26):
- **Unified client-push** for all three (Pi holds no credentials).
- **Codex:** just the two percentages (5-hour + weekly). No credits tile.
- **OpenCode:** single-machine use, so local session files are a complete record.

## Per-provider data sources (verified this session)

### Codex (ChatGPT) → `quota` (two tiles)
- **Shows:** "5 hour usage limit — 99% remaining" (+reset time) and "Weekly usage limit — 100%
  remaining" — structurally identical to Claude's session% / week%.
- **Endpoint:** `GET https://chatgpt.com/backend-api/wham/usage`
- **Auth:** ChatGPT **web-session Bearer token** (cookie-only GET returns `{"detail":"Unauthorized"}`).
  Not readable with any API key.
- **Client token source (resolve in plan):** prefer the Codex CLI auth file `~/.codex/auth.json`
  if present; else extract the ChatGPT session cookie from the local browser and exchange via
  `chatgpt.com/api/auth/session` for an `accessToken`. Handle expiry by skipping (show stale),
  never crash the push.
- **Maps to:** the existing `openai` provider stub, repurposed as Codex — `TilesPage` with two
  `quota` metrics (`codex.session_5h_pct` +reset, `codex.weekly_pct` +reset).

### xAI → `spend` (hero, 7-day)
- **Shows (console):** "Credits usage $1.39" over a selectable window (24h/**7d**/30d/90d), plus
  "Credits remaining $4.22".
- **Endpoint:** `POST https://management-api.x.ai/v1/billing/teams/{team_id}/usage`
- **Auth:** an xAI **management key** (xAI Console → Settings → Management Keys) — **separate from
  the inference API key**. Held in *client* config (not on the Pi).
- **Request:** body has `analyticsRequest.timeRange` (`startTime`/`endTime`/`timezone`, format
  `YYYY-MM-DD HH:MM:SS`), `timeUnit` (e.g. `TIME_UNIT_DAY`), and `values` with `{"name":"usd",
  "aggregation":"AGGREGATION_SUM"}`. Set the range to the last 7 days; sum the returned `usd`
  data points → `xai.spend_7d`.
- **Maps to:** the `xai` provider stub, changed from `balance` to a `spend` metric.

### OpenCode → `spend` (hero, 7-day)
- **Shows (console):** per-call cost history (DATE / MODEL / INPUT / OUTPUT / COST). The Zen **API
  key is inference-only** — no billing/usage REST endpoint (web console uses an opaque
  `POST /_server` RPC).
- **Local source (chosen):** the `opencode` CLI writes per-session message/cost JSON under
  **`~/.local/share/opencode`** (`OPENCODE_DATA_DIR`). Sum cost over the last 7 days →
  `opencode.spend_7d`. (Same model as Claude Code; community tools like ccusage/opencode-usage
  parse exactly these files. Exact JSON field for cost/tokens to confirm in the plan.)
- **Maps to:** the `opencode` provider stub, changed from `balance` to a `spend` metric.

## Pi-side changes (data-only)

- **`src/receiver.py`:** accept the new provider sections in the pushed payload and merge into
  `state["codex" | "xai" | "opencode"]`. Keep each provider independent (a missing/failed
  provider leaves its last-known state; never error the whole push).
- **`src/registry.py`:** enable the three stubbed providers with correct shapes/keys:
  - `codex` (was `openai`): `TilesPage([quota 5h, quota weekly])`.
  - `xai`: `spend` metric (hero page), key `xai.spend_7d`.
  - `opencode`: `spend` metric (hero page), key `opencode.spend_7d`.
- Net: **four provider pages cycle** (Claude, Codex, xAI, OpenCode); the per-provider accent
  stripe now distinguishes them.
- No new Pi secrets, no new Pi collector threads (unified client-push). The existing Anthropic
  `collector.py` (Admin API, currently 401) is untouched/out of scope.

## Client-side structure

- Extend `client/` with a **per-provider fetcher** each returning a small dict, plus an
  orchestrator that gathers all providers and POSTs one combined payload to the Pi receiver on
  the existing schedule (cron/timer). Each fetcher is isolated and independently testable.
- Client config gains: xAI management key + `team_id`, Codex token source, OpenCode data dir, and
  the existing Pi host/token.

## Data flow

1. Client (on the user's machine) runs on a timer: fetch Claude `/usage` (existing) + Codex
   `wham/usage` + xAI management API + OpenCode local files.
2. Client POSTs one combined JSON to the Pi receiver.
3. Receiver merges into `state`; `Dashboard` cycles the four provider pages and renders.

## Error handling

- Each fetcher is independent: a failure (expired Codex token, network error, missing file)
  pushes nothing for that provider; others still update; the tile shows last-known/placeholder.
- Codex token expiry is the main operational risk → log + skip, show stale, never crash.

## Testing

- Unit-test each fetcher's parse against mocked API responses / sample local files.
- Receiver test for the combined payload → state merge.
- Registry tests for the three enabled providers + their shapes.
- No hardware needed; all rendering already covered by the existing `dashboard` tests.

## Build order (independently shippable increments)

1. **Codex** — highest value (referenced daily), confirmed data, maps to existing `quota` tiles.
2. **xAI** — clean management-API call.
3. **OpenCode** — local-file parse.

Each increment = fetcher + receiver handling + registry enable + unit tests.

## Open items to resolve in the implementation plan

- Codex token acquisition (`~/.codex/auth.json` vs browser-cookie extraction) and expiry handling.
- Exact OpenCode local-file JSON schema (cost vs token fields; how sessions/messages are dated).
- Exact xAI response JSON shape (the `timeSeries`/`dataPoints` field to sum for `usd`).
- Receiver payload contract (one combined object vs per-provider keys) and config key names.
