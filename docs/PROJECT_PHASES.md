# JobFits — Project Phases (simple overview)

A plain-language map of everything. There are **two separate roadmaps**:
1. **AI Features** — building the actual AI features (done).
2. **AI Quality** — proving the matching is *good*, then making it better (in progress).

Status key: ✅ done · 🔜 not started yet · 📍 you are here

---

## Part 1 — AI Features (getting the AI working)

| Phase | What it does | Status |
|-------|--------------|--------|
| **0** | Connect the backend to the AI service (the "phone line" between them) | ✅ done |
| **1** | **Resume parsing** — read a CV and pull out skills, jobs, education | ✅ done |
| **2** | **Resume scoring** — give a resume an ATS score + quality score | ✅ done |
| **3** | **Job matching** — recommend jobs to a person (the % match cards) | ✅ done |
| **4** | **Writing help** — generate cover letters + interview questions | ✅ done (no screen/UI yet) |

**Part 1 is finished.** Every feature also has a backup plan, so nothing breaks if the AI is offline.

---

## Part 2 — AI Quality (proving it's good, then improving it)

This is the RAG plan (`docs/jobfits-rag-plan.md`). The idea: don't just *say* the matching works — **measure** it, then improve it with proof.

| Phase | What it does | Status |
|-------|--------------|--------|
| **A** | **The measuring stick** — hand-label good/bad job matches, then score how well the engine finds the good ones (Recall@10, etc.) | ✅ done |
| **B** | **Better search** — smarter matching (keyword search, a re-ranking step) | 🟡 in progress 📍 |
| **C** | **Smarter explanations** — have the AI score & explain each match, and check it isn't making things up | 🔜 not started |
| **D** | **Make it production-ready** — faster serving, caching, and a loop where user thumbs-up/down improves the system | 🔜 not started |

**The rule for Part 2:** every change in Phase B/C/D must be checked against the Phase A measuring stick — *prove* the number went up, don't guess.

---

## 📍 Where you are right now

**Phase A: done.** The measuring stick works; baseline saved (`eval/reports/BASELINE-2026-07-27.md`).

**Phase B: in progress — banked a real win.** Measured two improvements against the baseline:
- **Hybrid keyword search** — *neutral* on the current 51-job data (the harness honestly showed no gain; kept anyway, helps at scale). Now the default.
- **LLM re-ranker** — **improved ranking: MRR 0.63 → 0.75 (+20%)**. Built + measured + tested, but kept **OFF in production** for now (it adds an AI call per user; shipping it is a later cost decision). Your live app is unchanged.

That's a defensible portfolio result: *"I built a re-ranker and proved it lifted ranking quality 20% on a hand-labeled eval set."*

Still ahead in Phase B (whenever): make the re-ranker reach real users, add metadata filtering, and eventually try a proper cross-encoder model.

---

## Earlier snapshot

**You do NOT need to start Phase B yet.** Before Phase B is worth doing, you need a bit more labeled data so the number is trustworthy (label a few more candidates — optional, whenever you feel like it).

### Your simple loop for labeling more (only if you want)
1. Make the worksheets: `npx ts-node -r tsconfig-paths/register scripts/eval-export-worksheet.ts`
2. Open `eval/worksheets/<id>.jsonl`, change each `"?"` to `great` / `ok` / `bad`, save.
3. Load it: `npx ts-node -r tsconfig-paths/register scripts/eval-load-labels.ts eval/worksheets/<id>.jsonl`
4. Get the score: `npx ts-node -r tsconfig-paths/register scripts/eval-retrieval.ts`

That's it. Take a break — you've earned it. 👍
