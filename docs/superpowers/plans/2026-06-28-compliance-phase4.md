# Compliance Phase 4 Implementation Plan — AI Assistant + Agent Writes

**Goal:** Add the AI Compliance Assistant (deterministic NL-intent layer that answers compliance questions and links to real event/pack IDs, plus templated explanation drafting) and expand the agent CLI/MCP write surface. No server-side LLM, no autonomous compliance decisions.

**Builds on:** Phases 1-3. Design: `docs/superpowers/specs/2026-06-28-compliance-center-design.md` ("AI Compliance Assistant" + Non-Goals). Existing AI pattern: `app/services/ai_service.py` (heuristic keyword intent routing, en/tr) + `app/api/ai.py` — there is NO server-side LLM; the external agent is the LLM. Mirror that.

## Guardrails (from design Non-Goals)
- The engine stays deterministic and auditable; the assistant NEVER makes a compliance decision.
- The assistant is READ + DRAFT only. It surfaces deterministic data and links event/pack IDs. It does NOT create/approve packs or change event status on its own — those require an explicit user action (UI button / explicit CLI write command), gated by permission. "Create the May report pack" returns a *proposed action* (permit + period), not an executed write.
- Every answer references deterministic IDs (event ids, pack ids, permit id).

---

## Task A: Backend AI Compliance Assistant
**Files:** `app/services/compliance_assistant.py`; endpoint in `app/api/compliance.py` (`POST /compliance/assistant`); tests `tests/test_compliance_assistant.py`.

`answer_compliance_question(db, question, *, permit_id=None, period_start=None, period_end=None) -> dict` — heuristic en/tr intent classifier (mirror `parse_natural_language_query` style) producing `{intent, answer, links:[{type:"event|pack|permit", id}], data, proposed_action?}`. Intents:
- **readiness** ("ready for reporting", "rapora hazır mı", "bu ay hazır") → overview + open required `needs_explanation` count + existing pack status for the period; links permit + any pack ids; answer states ready/not-ready and why.
- **breaches** ("which limits were exceeded", "hangi limitler aşıldı") → `limit_exceeded` events for permit/period; links event ids.
- **missing_explanations** ("what explanations are missing", "hangi açıklamalar eksik") → open `needs_explanation` events; links event ids.
- **draft_explanation** ("draft an operator explanation for event N", "N için açıklama taslağı") → deterministic templated draft text built from the event's evidence_json (observed vs limit, period, parameter). Returns the draft in `data.draft` + links the event id. Does NOT save it.
- **create_pack** ("create the May report pack", "mayıs paketini oluştur") → resolves permit + period and returns `proposed_action = {action:"create_report_pack", permit_id, period_start, period_end}`; does NOT create. Answer instructs the user to confirm.
- **fallback** → short help listing supported questions.

Endpoint `POST /compliance/assistant` (any authenticated user; READ — no writes) body `{question, permit_id?, start?, end?}` → the dict above. No audit row (read-only).

Tests: each intent returns the right `intent` + populated `links`/`data`; draft_explanation produces non-empty text referencing the event; create_pack returns proposed_action WITHOUT creating a pack (assert pack count unchanged); unknown question → fallback.

Commit `feat(compliance): AI compliance assistant`.

## Task B: Agent CLI + MCP Writes + Assistant
**Files:** `scada-core` endpoints/client/catalog; `agent-harness` compliance command group; `mcp-scada` server; their tests.

Add to the agent surface:
- READ: `compliance_assistant` (capability tier "read"; CLI `scada compliance ask "<question>" [--permit-id N] [--start ISO] [--end ISO] --json-output`; MCP `compliance_ask`).
- WRITE (tier "write", write-gated by existing `SCADA_MCP_ALLOW_WRITES`): `compliance_add_note` (event note), `compliance_set_status` (event status; waive needs reason), `compliance_create_report_pack`, `compliance_approve_report_pack`. CLI: `scada compliance note add <event_id> "<text>"`, `scada compliance status set <event_id> <status> [--reason ...]`, `scada compliance report-pack create --permit-id N --start ISO --end ISO`, `scada compliance report-pack approve <pack_id>`.
- Endpoint constants + typed client methods for each. Document new CLI leaves in `agent-harness/skills/SKILL.md` (the MCP contract test enforces this).

Tests: catalog capability tiers (assistant read; the 4 writes write); CLI smoke (`scada compliance ask` mocked → JSON; write commands call client); MCP gating (assistant + reads default; the 4 writes only with `SCADA_MCP_ALLOW_WRITES=1`).

Verify `just cli-check` + `just mcp-check` green. Commit `feat(compliance): agent assistant + write surface`.

## Task C: Frontend AI Assistant
**Files:** `src/pages/compliance/AssistantTab.tsx` (+ wire into `ComplianceCenter.tsx`); `src/api/client.ts` (`askComplianceAssistant`); i18n `compliance.json` ×5; tests.

A panel/tab: question input (with the design's example prompts as quick-buttons), sends to `/compliance/assistant`, renders the answer + clickable links (event id → Events tab/detail; pack id → Report Packs tab; permit id → Permits). For `draft_explanation`, show the draft with a "Save as note" button that calls the existing add-note mutation (explicit user action; operator+admin only). For `create_pack` proposed_action, show a "Create pack" button that calls the existing create-pack mutation (explicit user action). Non-act users see answers but not the act buttons.

Tests: a mocked assistant response renders answer + links; draft response shows Save-as-note (hidden for viewer); create_pack shows Create button (hidden for viewer); i18n parity holds.

Verify `pnpm tsc --noEmit` + `pnpm test` (compliance + parity green; known pre-existing Grafana/Dashboard failures allowed). Commit `feat(compliance): AI assistant frontend`.

## Task D: Docs + Final Verification
- README + AGENTS.md: note `scada compliance ask` + the write commands; note the AI Assistant tab.
- Run targeted backend + frontend + cli + mcp; record only pre-existing unrelated failures.
- Commit `docs(compliance): note Phase 4 AI assistant`.

## Acceptance
- Assistant answers readiness/breaches/missing-explanations/draft/create-pack with deterministic ID links.
- Assistant never writes: create_pack/approve are proposals; writes happen only via explicit user/agent action.
- CLI/MCP expose the assistant (read) + write commands (write-gated).
- Frontend Assistant tab drives questions → linked answers → explicit save-as-note / create-pack actions, gated by role.
- Backend + frontend compliance tests green; i18n parity holds; cli/mcp checks green.
