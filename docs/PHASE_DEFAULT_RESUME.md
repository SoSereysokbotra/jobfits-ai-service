# Phase: "Which CV does the AI use?" — make the default résumé actually count

**Date opened:** 2026-08-17
**Status:** ✅ implemented 2026-08-17 — steps 1–4 done, **step 5 (re-run the eval) outstanding**
**Where the work happens:** `jobfit-backend` (this is a backend change; the AI service is stateless and needs **no** change)

> Implementation notes are at the bottom, under [What was actually built](#what-was-actually-built).

---

## The question

> A user can upload many résumés. If the database has many CVs, which one does the AI use?

## The answer (short)

**The AI never picks.** The AI service is stateless — every endpoint takes raw text in the
request body (`/resume/parse`, `/resume/score`, `/match-reason`, `/generate/*`). Whoever
calls it decides which CV's text to send. That caller is always `jobfit-backend`.

So the real question is: *what does the backend pick?* Today the answer is
**"the most recently updated one"** — not the one the user chose.

---

## What is already built (verified, not assumed)

The entire "default résumé" feature **already exists end to end**:

| Layer | What exists | Where |
|-------|-------------|-------|
| Database | `Resume.isDefault Boolean @default(false)`, indexed | `prisma/schema.prisma:613`, `:630` |
| Domain | `setAsDefault()` / `unsetDefault()` | `src/modules/resume/domain/entities/resume.entity.ts:83-91` |
| Repository | `findDefaultByUserId()` | `src/modules/resume/infrastructure/repositories/resume.repository.ts:65-70` |
| Service | `setDefaultResume()` — unsets the old default first, so only one can be default | `src/modules/resume/application/services/resume.service.ts:119-133` |
| API | `PATCH /resumes/:id/set-default` | `src/modules/resume/presentation/controllers/resume.controller.ts:114-124` |
| Frontend | "Default" badge + a set-default button | `src/features/resume/components/resume-card.tsx:38`, `:67-70` |

**No migration is needed. No new column. No new endpoint. No new UI.**

---

## The actual bug

The flag exists and the user can set it — **but almost nothing in the AI pipeline reads it.**

### The one place that gets it right

`src/modules/match-report/application/match-report.service.ts:141-147`

```ts
private async pickResume(userId: string): Promise<Resume | null> {
  const preferred = await this.resumes.findDefaultByUserId(userId);
  if (preferred?.parsingStatus === 'SUCCESS') return preferred;

  const all = await this.resumes.findByUserId(userId); // newest first
  return all.find((r) => r.parsingStatus === 'SUCCESS') ?? preferred ?? null;
}
```

Default first, fall back to newest-that-parsed. **This is the behaviour we want everywhere.**

### The eight places that ignore it

All run some variant of `orderBy: { updatedAt: 'desc' }` and never look at `isDefault`:

| # | File | Line | What it feeds |
|---|------|------|---------------|
| 1 | `matching/application/services/matching-embedding.service.ts` | 196 | **the candidate embedding** — the single most important one |
| 2 | `matching/application/services/job-match.service.ts` | 156 | years-of-experience in match scoring |
| 3 | `matching/application/use-cases/match-external-job.use-case.ts` | 271 | external-job matching |
| 4 | `matching/application/use-cases/recompute-user-matches.use-case.ts` | 364 | skills + experience for recompute |
| 5 | `matching/application/use-cases/recompute-user-matches.use-case.ts` | 407 | years of experience |
| 6 | `generation/generation.service.ts` | 202 | cover letters / interview Qs |
| 7 | `matching/evaluation/generation-eval.service.ts` | 301 | **the eval harness** |
| 8 | `matching/application/services/skill-gap.service.ts` | 174 | skill-gap analysis (uses `createdAt`) |

Site #1 is the one that matters most: it builds `profiles.embedding`, which drives every
recommendation. Its own header comment already says *"latest parsed résumé"* — so this is a
known, documented choice, not an accident. It's just the wrong choice now that users can
pick a default.

### Second bug found along the way: soft-deleted CVs still count

`Resume` has `deletedAt` and delete is a **soft** delete
(`resume.service.ts:110-117` → `repository.delete()`).

Of the 8 sites above, **only #8 (`skill-gap.service.ts:175`) filters `deletedAt: null`.**
The other 7 do not. So a résumé the user deleted can still be the one driving their
matching, their embedding, and their cover letters.

### Third gap: a user's first CV is never the default

`resume.service.ts:74-85` builds the `Resume` without `isDefault`, and the entity defaults
it to `false` (`resume.entity.ts:64`). Nothing else ever calls `setAsDefault()` except the
explicit endpoint.

So a user who uploads one CV and never clicks the button has **no default at all** — which
is exactly why the "latest" fallback has been silently carrying the whole system.

---

## The plan

### Step 1 — one shared helper (do this first)

Right now the same "pick a résumé" query is copy-pasted 8 times with 3 different rules
(`updatedAt` vs `createdAt`, with/without `deletedAt`). Fixing them one by one guarantees
they drift again.

Add **one** method — mirroring the logic already proven in `match-report.service.ts` — and
have all 8 sites call it:

```
default (isDefault: true, parsed, not deleted)
  → else newest parsed, not deleted
  → else null
```

Suggested home: the resume module's repository, so the matching module doesn't own résumé
selection rules.

### Step 2 — auto-default the first upload

In `resume.service.ts` upload: if the user has no existing default, mark this one default.
Makes the common case (one CV) correct with zero user action.

### Step 3 — re-embed when the default changes

`setDefaultResume()` currently only flips flags. Since the embedding is built from the
chosen résumé, changing the default must trigger `embedCandidate(userId)` — otherwise the
user picks a different CV and their recommendations don't move.

`MatchingEmbeddingService.embedCandidateByResume(resumeId)` already exists
(`matching-embedding.service.ts:62-68`) and degrades gracefully when the AI is down.

### Step 4 — backfill

Existing users have `isDefault = false` on every row. One-off script: for each user with no
default, set their newest successfully-parsed résumé as default. Then re-run
`embedAllCandidates()` (`matching-embedding.service.ts:103`).

### Step 5 — re-run the eval harness

Site #7 is the eval harness itself, so this change moves the measuring stick. Re-run Phase A
against `eval/reports/BASELINE-2026-07-27.md` and confirm the number didn't drop.

---

## What we are deliberately NOT doing

**Per-résumé embeddings** (move `embedding` off `profiles` onto `resumes`, match every CV,
take the best). It's genuinely better for someone with a "Developer CV" and a "Designer CV".
But it costs N× embeddings, needs job-level dedupe, and would force `MatchLabel` /
`MatchScore` / `Recommendation` to key on `resumeId` instead of the user — which invalidates
the hand-labeled eval set from Phase A.

Not worth it until users actually ask for it. Revisit after Phase B.

**Merging all CVs into one profile.** Rejected: averaging unrelated careers makes the vector
mean nothing, and `/match-reason` would cite skills from a CV the user didn't intend to
apply with.

---

## Open question for the user

When a user has a default CV but it **failed to parse**, `match-report` silently falls back
to the newest one that did parse. Should the rest of the system do the same (silent
fallback), or tell the user "your default CV couldn't be read, we're using X instead"?

**Shipped as silent fallback**, matching existing behaviour. Still worth revisiting — the
user currently gets no signal that their chosen CV is unreadable.

---

## What was actually built

Implemented 2026-08-17. All paths verified against the real code, not assumed.

### New files

| File | Purpose |
|------|---------|
| `src/modules/resume/application/services/active-resume.service.ts` | The single definition of "which résumé counts" |
| `src/modules/resume/application/services/active-resume.service.spec.ts` | 6 tests pinning the rule (default beats newer; unparsed default skipped; soft-deleted never returned) |
| `src/modules/resume/resume-selection.module.ts` | Exports `ActiveResumeService` on its own, so matching/generation don't inherit ResumeModule's BullMQ queue, storage client and controllers |
| `src/modules/resume/domain/events/resume-default-changed.event.ts` | Carries the **user** id; triggers the re-embed |
| `scripts/backfill-default-resumes.ts` | Step 4, with `--dry-run` |

### The rule (one place now)

```
1. the default résumé — if it parsed and is not soft-deleted
2. else the most recently updated résumé that parsed and is not soft-deleted
3. else null
```

### All 8 call sites now use it

Each was `prisma.resume.findFirst({ orderBy: { updatedAt: 'desc' } })`; each is now
`activeResume.findActiveResumeId(userId)` followed by a `parsedResumeData.findUnique` for
whichever columns that site needs. That is one extra query per site — accepted, because it
is the only way the three inconsistent variants collapse into one rule. It also fixes the
soft-delete hole at 7 of the 8 sites in the same move.

`MatchReportService.pickResume` was **left alone deliberately** — it already applied this
order, and it needs the `Resume` entity plus the ability to surface an unparsed default
rather than dropping it. Its comment now points at the shared service.

### Steps 2 and 3

- **Auto-default on first upload** — `ResumeService.uploadResume` checks
  `findDefaultByUserId` and claims the flag only when the user has none. Later uploads
  never touch an existing choice.
- **Re-embed on change** — `setDefaultResume` publishes `ResumeDefaultChangedEvent`, picked
  up by the existing `UserProfileUpdatedListener` alongside the profile events. It also now
  early-returns when the résumé is already the default, so a no-op click costs nothing.

### Verification

- `npx tsc --noEmit` — clean
- `npx jest --runInBand` — **538/538 pass, 51/51 suites**
- `npx eslint` on every changed file — clean
- Nest DI smoke test — all five affected providers resolve against the real `AppModule`

> ⚠️ Running jest **in parallel** (the default) fails 1–8 tests in `ai.client.spec`,
> `http-cache.interceptor` and `refresh-token.handler` — they bind real ports / a real DB
> and collide. Verified this is **pre-existing**: a clean tree with the changes stashed
> fails the same way (different tests each run). Use `--runInBand` for a trustworthy result.

### Still to do

**Step 5 — re-run the Phase A eval.** `generation-eval.service.ts` was one of the 8 sites,
so the measuring stick itself moved. Compare against `eval/reports/BASELINE-2026-07-27.md`
and confirm the number did not drop.

**Step 4 — run the backfill** against real data (nothing was run; the script is written):

```
npx ts-node -r tsconfig-paths/register scripts/backfill-default-resumes.ts --dry-run
npx ts-node -r tsconfig-paths/register scripts/backfill-default-resumes.ts
```

Needs the AI service up for the re-embed pass; without it those users are left un-embedded
and `backfill-embeddings.ts` can finish later.

---

## ⚠️ Review note — 2026-08-18: three things this phase did not close

Added by an external review (`jobfit-backend/docs/MENTOR_REVIEW_2026-08-18.md`, findings
#5 and #6). All three were verified against the code, not inferred from this document.

### 1. Step 3 does not actually move the user's recommendations

Step 3's stated purpose: *"otherwise the user picks a different CV and their recommendations
don't move."* The re-embed now fires correctly — but **nothing invalidates
`recommendations`.** `RecommendationsQueryService.getForUser` recomputes only when the user
has **zero** rows (`recommendations-query.service.ts:26-31`), and there is no scheduler
anywhere (`grep -rn "@Cron\|ScheduleModule" src/` → nothing).

So after changing the default CV: `profiles.embedding` changes, the cached
`Recommendation` rows do not, and the user sees the same list as before — the exact symptom
Step 3 was written to prevent.

**Fix:** have `UserProfileUpdatedListener` delete the user's `recommendation` rows after a
successful re-embed; the existing lazy path rebuilds on the next read. Ideally also stamp
`computedAt` + the `resumeId` the score came from, so the UI can say *when* the match was
computed instead of implying it is live.

### 2. The application path asks a different question, and still answers it wrong

`Application.resumeId` exists and the submit DTO accepts it
(`application.service.ts:81`) — the system records *which CV the candidate applied with*.

`ApplicationScreeningService.screen()` selects
`{ id, userId, jobId, status, screenedAt }` (`application-screening.service.ts:68`) and
**never reads `resumeId`**. It resolves the user's *current* active résumé instead. So an
employer's screening summary can describe a CV the candidate never submitted — while
`EmployerApplicationResponseDto` calls that summary *"A SNAPSHOT of that moment, never
recomputed"*.

This is not the same question this phase answered. Matching asks *"which CV represents you
right now?"*; an application asks *"which CV did you send, then?"* — and the answer to the
second is already stored in a column.

**Fix:** resolve `resumeId` at write time (`dto.resumeId` if owned by the caller, else
`activeResume.findActiveResumeId(userId)`), make it non-null from then on, and have
`screen()` score against **that** résumé.

### 3. `dto.resumeId` is not checked for ownership

`Application.create({ resumeId: dto.resumeId })` accepts any UUID the client sends. Harmless
today because nothing reads the column — it stops being harmless the moment fix #2 lands.

