# Plan — DeepSeek as an optional generation provider

> Status: **BUILT + VERIFIED LIVE 2026-08-20** (steps 1-4 of §9). Suite 60/60, ruff clean.
> Not yet done: step 5 (`/health`, optional).
>
> **Two defects the mocked tests could not have caught — see §10.**
> Repo: `jobfits-ai-service`. **No changes to `jobfit-backend` or the extension.**
>
> **Changed during implementation:** interview *feedback* was split out as its own task
> (`interview_feedback`) and left OFF the default allowlist — it carries the user's own
> written answer, which the plan's table had lumped in with question generation.

---

## 1. Why

Two problems, one change.

1. **Local generation quality.** `qwen3` is the weakest link in the user-facing text
   (interview questions, extracted requirements). A hosted model is better at these.
2. **Ollama stops on its own.** Recorded in `jobfit-backend/docs/HANDOFF_2026-08-17.md` §4:
   *"The AI service and Ollama both stop on their own. Both died mid-session."* When that
   happens every generation feature silently drops to a template. A hosted API does not
   stop on its own.

DeepSeek is the chosen provider: OpenAI-compatible (small integration), and at our volume
the cost is **cents** — see §7.

---

## 2. Scope — what moves and what does NOT

**Deny by default.** A task uses DeepSeek only if it is on an explicit allowlist.

| Task | Provider | Why |
|---|---|---|
| `/generate/interview` (`kind: questions`) | **DeepSeek → Ollama** | Sends job title + level only. **Zero user data.** |
| `/job/requirements` | **DeepSeek → Ollama** | Sends the employer's public posting. **Zero user data.** |
| `/generate/interview` (`kind: feedback`) | **Ollama only** | Carries the user's own written answer. Task `interview_feedback`, not allowlisted. |
| `/generate/cover-letter` | **Ollama only** (Phase 2) | Sends `resumeSummary` — derived from the user's CV. Needs a privacy notice first. |
| `/resume/parse` | **Ollama only** | Full résumé text: name, email, phone, employers. |
| `/resume/score` | **Ollama only** | Full résumé text. |
| `/embed` | **Ollama only** | DeepSeek has no embeddings API, and the DB column is `vector(1024)` = bge-m3. Changing it invalidates all 377 stored embeddings. |
| `/rerank` | **Ollama only** | Hot matching path over many documents — cost and latency. |
| `/match-reason` | **Ollama only** | Only called from `generation-eval.service.ts`. Not a production path. |

### Non-goals

- **No change to matching or scoring.** Handoff §5 and §6: the eval set cannot currently
  adjudicate a retrieval or scoring change. Nothing here touches those code paths.
- **No new dependency for people without a key.** Empty `DEEPSEEK_API_KEY` must leave
  behaviour byte-identical to today.

---

## 3. Design

### 3.1 Do not put DeepSeek inside `OllamaClient`

`ollama_client.py` says of itself: *"The ONLY module that talks to Ollama."* That
invariant is worth keeping. Instead, introduce a narrow protocol and let the two clients
sit side by side.

```
ChatProvider (Protocol)
    async def chat(messages, json_mode) -> str

├─ OllamaClient      (exists; also does embed + list_models — unchanged)
├─ DeepSeekClient    (NEW; chat only)
└─ FallbackProvider  (NEW; primary → secondary on AiServiceError)
```

`OllamaClient` already matches the protocol. **Its file is not edited at all.**

### 3.2 The allowlist is the PII boundary

```
ChatRouter.for_task("interview")       -> Fallback(DeepSeek, Ollama)   # if allowed + key set
ChatRouter.for_task("cover_letter")    -> OllamaClient                 # not on the list
```

Services that must never leave the machine (`ResumeService`, `EmbedService`,
`RerankService`, `MatchReasonService`) **keep taking `OllamaClient` directly** and are
never handed the router. The privacy rule is then enforced by the type wiring, not by a
comment someone has to remember.

Only `GenerateService` and `JobRequirementsService` change constructor type
(`OllamaClient` -> `ChatProvider`), which is why they are the only two touched.

### 3.3 Fallback semantics

DeepSeek raises `AiServiceError` (402 no balance / timeout / 5xx / network) → log a
warning naming the provider → retry the same call on Ollama. If Ollama also fails, raise
as today; the backend already degrades to its template/static path.

Full chain, end to end:

```
DeepSeek  →  local Ollama  →  backend template/static fallback
```

**Rationale:** adding DeepSeek must never make a request *more* likely to fail than it is
today. So any DeepSeek error falls through, including a 4xx.

---

## 4. Files

| File | Change |
|---|---|
| `app/config.py` | + 5 settings (§5) |
| `.env.example` | + the same 5, documented, key blank |
| `app/services/chat_provider.py` | **NEW** — `ChatProvider` protocol + `FallbackProvider` |
| `app/services/deepseek_client.py` | **NEW** — OpenAI-format client, `chat()` only |
| `app/services/chat_router.py` | **NEW** — task → provider, reads the allowlist |
| `app/deps.py` | + `get_chat_router()`; existing providers untouched |
| `app/services/generate_service.py` | ctor type only; **interview** routed, cover letter not |
| `app/services/job_requirements_service.py` | ctor type only |
| `app/routers/generate.py`, `job_requirements.py` | inject the router |
| `app/services/ollama_client.py` | **UNCHANGED** |
| `tests/test_deepseek_provider.py` | **NEW** (§6) |

---

## 5. Config

```bash
# ── DeepSeek (optional; blank key = disabled, Ollama only) ──
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TASKS=interview,job_requirements   # allowlist; NEVER add resume tasks
REQUEST_TIMEOUT_DEEPSEEK=30
DEEPSEEK_MAX_TOKENS=4096                    # spend guard (see §10.1: 1024 truncated)
```

Notes:
- `deepseek-v4-flash`, **not** `deepseek-chat` — the old names were retired 2026-07-24.
- Use Flash, not Pro: ~3x cheaper and these are not reasoning tasks.
- `DEEPSEEK_MAX_TOKENS` caps output so a malformed prompt cannot burn credit.
- `.env` is already gitignored (`.gitignore` lines 15-17); only `.env.example` is tracked.

---

## 6. Tests (`respx`, same pattern as `tests/test_generate.py`)

Mock `https://api.deepseek.com/chat/completions` alongside the existing
`http://localhost:11434/api/chat`.

1. Key set + task allowed → **DeepSeek is called**, Ollama is not.
2. DeepSeek 500 → **Ollama is called**, response is still 200.
3. DeepSeek 402 (no balance) → same fallback, 200.
4. Both down → 502, exactly as today.
5. Key blank → DeepSeek route **never touched**.
6. **PII guard:** `/generate/cover-letter` and `/resume/parse` go to Ollama **even with
   DeepSeek enabled**. This is the test that must never be deleted.
7. Response parsing: OpenAI shape `choices[0].message.content`; a malformed shape raises
   `MODEL_ERROR`, not an `IndexError`.

Whole suite must stay green: `./.venv/Scripts/python.exe -m pytest tests/ -q` (**60/60**).

---

## 7. Cost

Priced at DeepSeek's **peak** rate (off-peak is half; peak is only 01:00-04:00 and
06:00-10:00 UTC, so most dev time is cheaper).

| Task | Tokens/call | Cost/call | What $2 buys |
|---|---|---|---|
| Interview prep **(MEASURED)** | **329 in / 963 out** | **~$0.0014** | **~1,400 calls** |
| Job requirements (estimated) | ~800 in / 200 out | ~$0.0006 | ~3,300 calls |

⚠️ **The interview estimate above was 3x optimistic.** The plan guessed ~300 output tokens;
the live call used **963**, because V4-Flash bills its internal reasoning (205 tokens here)
inside the completion budget. $2 is still ~1,400 calls so the conclusion holds — but the
original number was wrong, and this is what it actually costs.

Confirmed working as predicted: **256 of the 329 input tokens were a cache hit** (the fixed
prompt file), billed at ~2% of the miss rate.

Extracting requirements for **all 367 jobs once ≈ $0.23** (still an estimate — not measured).

Billing is **prepaid** — the card is charged once, calls draw down the balance, and an
empty balance returns an error rather than charging again. Prompts are fixed files, so
cache hits (~98% cheaper) should apply on repeat calls.

**Caveat:** the pricing pages I checked disagreed (official docs vs third-party trackers).
The numbers above use the higher set, so real cost should be at or below this.

---

## 8. How we will know it worked — and the honest gap

- **Reliability (measurable):** count `generatedBy: 'template' | 'static'` responses before
  and after. That is the number that justifies paying; it should fall toward zero while
  Ollama is flaky.
- **Cost (measurable):** DeepSeek dashboard balance after a week of normal use, against §7.

⚠️ **Quality is NOT measured.** There is no eval harness for interview questions or
requirement extraction, so the quality claim ships on judgement, not on a number — which
breaks project rule #1. Accepted here because the fallback (a static question list) is
obviously worse, and because these endpoints do not feed matching or scoring. **This
reasoning must not be reused for anything in §2's non-goals.**

One thing that *is* already measured and must be preserved: `job_requirements_service`
scores how grounded each extracted requirement is in the source text. If DeepSeek is
better, that score should hold or rise. **If it drops, that is a regression, not an
upgrade** — the guard exists because a past model copied a prompt's own few-shot example
into its answer.

---

## 9. Order of work

1. Settings + `.env.example` (blank key; suite still green — proves the no-op default).
2. `DeepSeekClient` + `ChatProvider` + `FallbackProvider`, with tests 1-4 and 7.
3. `ChatRouter` + allowlist; wire `GenerateService.interview` and
   `JobRequirementsService`; tests 5 and 6.
4. Manual check with a real key: interview prep on a live posting, watch the balance move.
5. **(Optional, separate)** Fix `/health`. It returns `{"status":"ok","modelsLoaded":[]}`
   with Ollama fully down — handoff open issue #5 — and a second provider makes that
   report more misleading, not less. Suggested: add a `providers` map
   (`{"ollama":"up","deepseek":"disabled"}`). Additive, so the backend `AiHealth` type
   keeps working.

**Rollback:** blank `DEEPSEEK_API_KEY`. No migration, no data change, no backend deploy.

---

## 10. What the live run found (2026-08-20)

Step 4 was run by pointing `OLLAMA_URL` at a dead port, so anything that still answered had
to be DeepSeek. Both findings were invisible to the mocked suite, because both were
**HTTP 200 responses that were nonetheless failures**.

**10.1 — `max_tokens` was corrupting output, not guarding spend.**
The 1024 cap in §5 was a guess. An ordinary interview request spent **963 completion
tokens, 205 of them the model's own reasoning** (V4-Flash bills reasoning inside the
completion budget — the plan did not account for that). So the call sat just under the cap
and sometimes crossed it, returning JSON cut off mid-object. **Now 4096**, ~4x the observed
ceiling; worst case is still well under a cent.

**10.2 — A truncated reply bypassed the fallback entirely.**
Truncation arrives as `finish_reason: "length"` on a **200**, so `DeepSeekClient` returned
the broken text happily, it failed later in `extract_json` — outside `FallbackProvider`'s
reach — and the request **502'd while a healthy Ollama sat unused**. The provider now
raises on `finish_reason == "length"`, putting the failure back inside the fallback
boundary. Pinned by `test_falls_back_when_deepseek_truncates_at_max_tokens`.

The general lesson, worth keeping: *the fallback only covers failures the provider raises.*
Any way the vendor can return 200 with unusable content has to be converted into an
exception inside the client, or the degrade path silently does not apply.

**10.3 — The suite was reading the developer's `.env`.**
Adding a real key turned 12 green tests red: they mock Ollama only, but `job_requirements`
is allowlisted by default, so they tried to reach the real API. `tests/conftest.py` now
forces the provider off for every test; the ones that exercise it opt in via `deepseek_on`.
**The suite must not depend on whether the person running it has bought credit.**

### Verified behaviour, Ollama unreachable

| Call | Result | Meaning |
|---|---|---|
| `/generate/interview` (questions) | **200**, 6 real questions | DeepSeek genuinely carried it |
| `/generate/cover-letter` | **502** | Résumé-derived text stayed local, as designed |

⚠️ **Latency:** that interview call took **13.4s** against a short description.
`REQUEST_TIMEOUT_DEEPSEEK` is 30s, so a long posting could time out — which degrades to
Ollama rather than failing, but is worth watching.

---

## 11. Before merging

- [ ] `DEEPSEEK_TASKS` contains no résumé task.
- [ ] `.env` not staged (`git status` — stage explicit paths, never `-A`).
- [ ] Test 6 (PII guard) present and passing.
- [ ] `PRIVACY.md` updated **if** cover letter is ever added in Phase 2.
