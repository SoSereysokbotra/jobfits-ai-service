# Project Deep-Dive — Turn JobFits Into a Production RAG + LLM Platform With Real Evaluation

*A standalone engineering playbook. This expands the roadmap's Project 5 into something you can execute against, tailored to JobFits' actual stack: NestJS/DDD backend, Next.js frontend, **FastAPI AI service**, Postgres (Prisma, 24 models), Cloud Run, and Ollama for dev.*

The goal of this project is not "add AI to JobFits." Your AI service is already ~85% built. The goal is to convert it from a plausible-looking pipeline that has **never been validated against real models** into a system whose match quality is *measured*, *defensible*, and *improvable* — the difference between "I used an LLM" and "I ship a reliable LLM product."

---



## 1. What this project actually is (and why "RAG" is the right frame for job matching)

Job matching looks like a recommender problem, but the production-grade version is a **retrieval + grounded-reasoning** system — exactly the RAG pattern, with the roles renamed:


| Generic RAG                     | JobFits job matching                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Query                           | A candidate profile/CV (or a job posting, for the reverse direction)                                               |
| Corpus                          | All job postings (or all candidate profiles)                                                                       |
| Retrieval                       | Find the best-matching jobs for this candidate                                                                     |
| Reranking                       | Reorder the shortlist by fine-grained fit                                                                          |
| Generation                      | Produce a **structured match**: a score + the specific reasons, grounded in evidence from both documents           |
| "Answer is grounded in context" | "The match reasoning cites real skills/requirements that actually appear in the CV and the JD — not invented ones" |


This reframing matters because it tells you exactly what to measure and where quality can break. A match can fail in two independent places: **retrieval** (the right jobs never made the shortlist) or **generation** (the LLM scored/explained the shortlist wrongly). Your entire evaluation strategy hinges on measuring these *separately* — more on that in §8, because it's the heart of the project.

You run this in **both directions**: candidate → jobs (for job seekers) and job → candidates (for recruiters). Same machinery, swapped query/corpus. Build one direction well first.

---



## 2. The bar — what "done" means

Not "it returns matches." Done means you can state, with evidence:

- **Retrieval quality**, measured on a labeled set: Recall@10 and MRR/nDCG@10, sliced by job category, seniority, and language.
- **Match quality**, measured end-to-end: how well your LLM's match scores agree with human judgment, and a faithfulness score proving the reasoning is grounded (no invented skills).
- **A cost/latency table**: p50/p99 latency per match, and cost per 1,000 matches, on both your dev (Ollama) and production (vLLM) paths.
- **A feedback loop**: user thumbs-up/down on matches flows back into the eval set, and you've shown one iteration that moved a number.

If you can produce that four-part evidence package, you have a portfolio centerpiece and a real product. If you can't, you have a demo.

---



## 3. Required knowledge (first-principles, expanded)

You already have the two hardest prerequisites: you've built a **hybrid BM25 + semantic search** system, and you've built a **ReAct agent with ChromaDB**. So retrieval and LLM orchestration aren't new. What this project adds on top:

- **Embeddings as a design choice, not a default.** Which model, what dimension, dense vs. sparse vs. hybrid, and why — driven by your multilingual (Khmer/English) and budget constraints.
- **Reranking.** Why a bi-encoder retriever + cross-encoder reranker beats either alone, and where the cost lives.
- **Structured generation.** Getting reliable, schema-valid JSON out of an LLM every time — constrained decoding, validation, retries.
- **Prompt engineering as software.** Versioned, tested, diffable prompts — not strings you tweak in a notebook.
- **Evaluation.** The genuinely hard skill: building a labeled set, choosing metrics that separate retrieval from generation, and using LLM-as-judge without fooling yourself.
- **Serving economics.** Continuous batching, caching, and the quadratic-cost trap specific to matching.

---



## 4. System architecture (mapped to your stack)

> **Reality check (verified against the code, 2026-07).** The diagram below is the
> *target*. Today the split is different, and this plan must be read with that in mind:
>
> - **The FastAPI AI service (`jobfits-ai-service`) is stateless model-serving only** —
>   `POST /embed`, `/resume/parse`, `/resume/score`, `/generate/*`, `GET /health`. It has
>   **no database** (no Prisma/pgvector/DB driver in `requirements.txt`) by design
>   (its `BUILD_PLAN.md` golden rule: *"Stateless. No database."*).
> - **The matching pipeline + Postgres live in the NestJS backend (`jobfit-backend`),**
>   which owns the schema via Prisma. Retrieval today = a single **pgvector cosine**
>   nearest-neighbour query in `RecomputeUserMatchesUseCase` over `Job.embedding`, then a
>   deterministic weighted re-rank (skills 40 / exp 25 / loc 15 / salary 10 / other 10) →
>   `recommendations` rows → `GET /recommendations`. The backend calls the AI service's
>   `/embed` (BGE-M3) to build the vectors it stores.
> - **Not yet built** (later phases here): BM25/`tsvector`, RRF fusion, cross-encoder
>   rerank, metadata pre-filter, and the structured LLM match-reasoning layer. The
>   "MATCH" and "EVAL" boxes below therefore run **in the backend**, not the AI service.
>
> So when this doc says "the FastAPI AI service (the focus)", read it as "the *matching
> system*, which is orchestrated by the backend and delegates model calls to the AI
> service." Evaluation (Phase A) is backend work for the same reason.

```
                         ┌─────────────────────────── NestJS backend (existing) ───────────────────────────┐
  Next.js / Chrome ext ──▶  107 endpoints, auth, orchestration  ──▶ calls the FastAPI AI service            │
                         └────────────────────────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
   ┌──────────────────────────────────── FastAPI AI service (the focus) ───────────────────────────────────┐
   │                                                                                                        │
   │  INGEST (offline/async)                    MATCH (online)                                               │
   │  ─────────────────────                     ────────────                                                 │
   │  CV/JD ─▶ parse ─▶ chunk ─▶ embed          query (candidate/job)                                        │
   │         ─▶ pgvector + tsvector (BM25)              │                                                    │
   │                                            1) metadata pre-filter (location, seniority, salary, active) │
   │                                            2) hybrid retrieve (dense pgvector + sparse BM25) → top ~50   │
   │                                            3) rerank (cross-encoder) → top ~10                           │
   │                                            4) LLM match reasoning → validated JSON {score, reasons,      │
   │                                               evidence}  [served via Ollama dev / vLLM prod]             │
   │                                            5) cache (Redis)                                              │
   │                                                   │                                                     │
   │                                            EVAL harness (offline) ◀── labeled pairs + production feedback│
   └────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                     │
                              Postgres (pgvector + full-text) · Redis (cache) · Cloud Run
```

Three deliberate choices for *your* situation:

- **Vector store = pgvector inside your existing Postgres.** You already run Postgres via Prisma and you have a stated habit of not expanding infrastructure unnecessarily. pgvector keeps embeddings, metadata, and full-text (`tsvector` for BM25) in one database you already operate — one backup story, one connection pool, transactional consistency between a job posting and its embedding. Qdrant/Chroma are fine alternatives you already know, but for a single-corpus app at your scale, pgvector is the disciplined pick. Reach for a dedicated vector DB only when scale forces it.
- **Redis for caching.** You already flagged "no Redis in production" as a JobFits blocker. This project is the reason to add it — repeated queries and shared prompt prefixes make caching a real latency/cost win, and adding it here closes an existing operational gap.
- **Ollama for dev, vLLM for prod.** Keep Ollama for local iteration. But your "never validated against real models" blocker gets closed by standing up a real serving path; vLLM gives you continuous batching and an OpenAI-compatible API so the switch is a base-URL change.

---



## 5. Data and schema design (where most of the real work is)

> **Where this schema actually lives (verified 2026-07).** All of it is **Prisma-managed
> in `jobfit-backend`**, not the AI service. Mapping from the sketch below to what exists:
> `job_posting` → the Prisma `jobs` model, `candidate_profile` → `profiles`. Both already
> carry `embedding vector(1024)` (pgvector, added in the Phase 3 matching migration);
> there is **no `tsvector`/`summary` column yet** (those arrive with BM25 in Phase B).
> `match_label` and `match_log` will be **new Prisma models in the backend**, added by a
> hand-written additive migration + `prisma migrate deploy` — the AI service never touches
> the database.

RAG lives or dies on the corpus. Before any modeling:

**Parsing.** CVs and JDs arrive as messy PDFs/HTML/text. Parse into structured fields *and* keep raw text. For a CV: skills, titles, years, education, raw sections. For a JD: required skills, nice-to-haves, seniority, location, salary band, raw text. This structure is what powers metadata filtering (§6), which is often a bigger accuracy lever than the embedding model.

**What to embed (chunking).** Don't embed a whole CV as one vector — you lose granularity. Two workable strategies:

- *Field-level embeddings*: embed the skills section, the experience section, etc., separately. Retrieval can then match "Python + FastAPI" in the skills field specifically.
- *Whole-document + summary embedding*: embed a concise LLM-generated summary of the CV/JD alongside the raw. Summaries reduce noise and often retrieve better than raw dumps.

Test both on your eval set. Chunking strategy is a hyperparameter — measure it, don't guess it.

**Metadata for pre-filtering.** Store as first-class columns (not just in the vector): location, seniority level, salary range, employment type, `is_active`. **Filter before you rank.** A perfect semantic match to an expired job in another country is a bug. Metadata filtering is cheap, deterministic, and eliminates whole classes of embarrassing matches that no embedding model will fix.

**Schema sketch (extend, don't bloat — consistent with your JobFits habit):**

```
job_posting(id, ..., seniority, location, salary_min, salary_max, is_active,
            embedding vector(1024), search_tsv tsvector, summary text)
candidate_profile(id, ..., seniority, location_pref, salary_expectation,
            embedding vector(1024), search_tsv tsvector, summary text)
match_label(candidate_id, job_id, label ENUM('great','ok','bad'),
            reason text, source ENUM('human','feedback'), created_at)   -- the eval set
match_log(candidate_id, job_id, score, reasons_json, model_version,
          prompt_version, latency_ms, created_at)                       -- for the flywheel
```

`match_label` is the most important table in this project. It's your source of truth. Build it early.

---



## 6. The retrieval pipeline (concrete model picks for your constraints)

Your constraints: multilingual (Khmer + English), a laptop for dev, a Cloud Run budget for prod. That drives specific choices.

**Embedding model.**

- **Production pick: BGE-M3.** It's the versatile default for a reason — one model gives you dense *and* sparse (lexical) representations, so you get hybrid retrieval without maintaining a separate keyword index, and it's strongly multilingual (matters for Khmer/English CVs). It outputs a manageable dimension and self-hosts cheaply.
- **Alternative worth benchmarking: Qwen3-Embedding.** It's instruction-aware (you can prepend a task instruction like "represent this CV for job retrieval," which measurably helps), strongly multilingual, and supports flexible output dimensions (32–1024) so you can trade storage for accuracy. Bench the 0.6B/4B sizes against BGE-M3 on *your* eval set.
- **Dev/laptop pick: Nomic-embed-text** (runs in Ollama, ~270 MB, CPU-friendly, 8k context) so your local loop is fast. Keep the production embedder pluggable so dev and prod can differ.

Whatever you pick: **re-embed the whole corpus whenever you change the model or dimension.** Mixed-model vectors in one index silently corrupt retrieval.

**Hybrid retrieval.** Dense (pgvector, cosine) catches semantic matches ("built REST APIs" ≈ "backend engineer"); sparse/BM25 (Postgres `tsvector`) catches exact terms that embeddings blur (specific frameworks, certifications, "FastAPI", "Khmer"). Fuse the two ranked lists — **Reciprocal Rank Fusion (RRF)** is the simple, robust default (no score-normalization headaches). You've already built BM25 + semantic once; reuse that instinct here.

**Reranking.** Retrieve ~50 candidates cheaply, then rerank with a cross-encoder that reads (query, document) *together* for fine-grained fit, and keep the top ~10 for the LLM. Picks: **BGE-reranker-v2** (the common production partner to BGE-M3) or **Qwen3-Reranker**. Reranking is usually the single highest-ROI accuracy upgrade in a RAG system — bi-encoders are fast but coarse; the cross-encoder fixes the ordering that actually feeds your LLM. Measure the Recall@10-before vs. nDCG@10-after to prove its worth.

**Retrieval flow (pseudocode):**

```python
def retrieve(query_profile, k=10):
    flt = build_metadata_filter(query_profile)          # location, seniority, salary, is_active
    dense = pgvector_search(query_profile.embedding, filter=flt, limit=50)
    sparse = bm25_search(query_profile.search_tsv, filter=flt, limit=50)
    fused = reciprocal_rank_fusion(dense, sparse)        # ~50 candidates
    reranked = cross_encoder_rerank(query_profile, fused)  # cross-encoder scores
    return reranked[:k]
```

---



## 7. The generation layer — structured match reasoning

The LLM's job is **not** to pick matches (retrieval already did the heavy lifting). Its job is to *score and explain* each shortlisted pair, grounded strictly in the two documents.

**Force structured output.** Never parse free text. Define a schema and validate every response:

```json
{
  "job_id": "…",
  "fit_score": 0.0,                 // 0–1
  "matched_requirements": [ {"requirement": "…", "evidence_from_cv": "…"} ],
  "gaps": [ {"requirement": "…", "note": "…"} ],
  "verdict": "strong | possible | weak"
}
```

Use **constrained decoding / JSON-schema-enforced generation** (vLLM and most serving stacks support grammar/JSON-schema constraints) so the model *cannot* emit malformed JSON. Validate with Pydantic; on the rare failure, retry once, then fall back to a deterministic score. This turns "works 95% of the time" into a service.

**Ground the reasoning.** The prompt must instruct the model to cite evidence *only from the provided CV/JD text*, and your evaluation must check that the cited skills actually appear in the source (this is the faithfulness metric — §8). Invented qualifications are the job-matching equivalent of hallucination and are a legal/trust liability in a hiring product.

**Prompt engineering as software.** Store prompts as versioned files with a `prompt_version` string that's logged with every match (see `match_log`). When you change a prompt, you can A/B the versions against the eval set and *prove* the new one is better. Treat a prompt change like a code change: it gets evaluated before it ships.

**Model size discipline.** You don't need a giant model to score a pre-filtered, pre-ranked pair against a rubric. Start with a small instruct model (a 7B-class open model) served on vLLM; only go bigger if the eval shows the small model can't reason about fit reliably. Cheaper-and-measured beats bigger-and-vibes, and it's what your budget allows anyway.

---



## 8. The evaluation harness — the heart of the entire project

This is the part that makes you an engineer instead of a prompt-tweaker. Build it **before** you optimize anything. Here's the discipline, and a cautionary tale that makes the case.

**The cautionary tale (memorize this failure mode).** A team ships a RAG system, scores 0.91 on faithfulness offline, and celebrates. Weeks later, ~1 in 6 answers is missing a key fact. They check the dashboard: faithfulness is *still* 0.91. The problem was **context recall** at 0.62 — the retriever was silently missing a needed document on harder queries, and the generator was fluently answering from the *partial* context, so the generation metric never dropped. No generation-stage metric could ever have caught it. The lesson is absolute: **measure retrieval and generation separately, or you will ship regressions you can't see.**

**Tier 1 — Retrieval metrics (needs labeled gold matches).**
Build `match_label`: for a set of candidates, have a human (you, initially) label which jobs are `great` / `ok` / `bad` matches. A few hundred labeled pairs is enough to start. Then compute, on held-out queries:

- **Recall@10** — of the truly good jobs, how many made the top 10? (If this is low, no LLM prompt can save you — fix retrieval first.)
- **MRR** — how high did the first good match rank?
- **nDCG@10** — overall ranking quality with graded labels (great > ok > bad).
Slice every metric by job category, seniority, and **language** (your Khmer slice will lag first — that's the signal to invest there).

**Tier 2 — Generation metrics (LLM-as-judge + your labels).**
For the shortlist the LLM scored:

- **Faithfulness / groundedness** — are the "matched requirements" actually present in the CV and JD? Decompose the reasoning into atomic claims and check each against the source. This catches invented skills.
- **Match-score calibration** — does the LLM's `fit_score` correlate with your human labels? Compute rank correlation between LLM scores and human `great/ok/bad`. This is the single number that tells you whether the LLM's judgment is trustworthy.
- **Answer relevance** — does the explanation address *this* candidate–job pair, or is it generic boilerplate?

**Tooling.** Use **Ragas** as the canonical open-source metric library (it pioneered the context-precision / context-recall / faithfulness / answer-relevance pattern and supports LLM-as-judge, mostly reference-free — though context recall needs your labels). If you want pytest-style, component-level eval so each pipeline stage becomes a unit test, **DeepEval** builds on the same metrics. Ragas can also *generate* a synthetic starter eval set from your corpus, which helps you bootstrap before you have enough human labels — but treat synthetic labels as a scaffold, not ground truth.

**LLM-as-judge, honestly.** It's powerful and it's also biased: judges favor longer answers, favor the first option in a pairwise comparison (position bias), and inherit the judge model's blind spots. Mitigate by using a *different, stronger* model as judge than the one being judged, randomizing option order, and periodically spot-checking judge verdicts against your human labels. Never let the judge grade its own homework.

**The flywheel.** Every production match gets logged (`match_log`). Every thumbs-down from a user becomes a candidate `match_label` (source = `feedback`). Every failure becomes a test case. This is what converts a static eval set into a system that gets better from real usage — and it's exactly the "self-improving" loop that separates a product from a demo.

---



## 9. Serving and cost (the part that makes it deployable)

**The quadratic trap.** The naive design calls the LLM on every candidate × every job. With N candidates and M jobs that's N×M LLM calls — ruinous. The whole architecture avoids it: cheap retrieval + reranking narrows M to ~10 per candidate *before* the LLM sees anything. The LLM only ever scores a short, high-quality shortlist. Internalize this: **retrieval is the cost-control mechanism, not just the quality mechanism.**

**Dev → prod path.** Ollama locally; **vLLM** in production for continuous batching, PagedAttention, and an OpenAI-compatible API (so your FastAPI client barely changes). If many of your match prompts share a long system-prompt/rubric prefix — they will — an engine with prefix caching (SGLang's RadixAttention, or vLLM's prefix caching) turns that shared prefix into a large, free speedup. Measure the hit.

**Caching (Redis).** Two layers: an exact-match cache (same candidate+job+model+prompt version → cached result) and optionally a semantic cache for near-duplicate queries. Cache invalidation keys on `model_version` + `prompt_version` so a model/prompt change doesn't serve stale scores.

**The cost table (a required deliverable).** Produce actual numbers: cost per 1,000 matches on Ollama vs. vLLM, p50/p99 latency per stage (retrieve, rerank, generate), and cache hit rate. A model with no cost/latency numbers is uncharacterized. These numbers are also your product's unit economics — directly relevant to your entrepreneurship interest.

---



## 10. Phased build plan (mapped to JobFits' current state)

Your AI service is ~85% built but unvalidated, no Redis, pipeline never run against real models. So the sequence is: *make it real and measurable first, optimize second.*

**Phase A — Ground truth before glory (highest priority).**

1. Build `match_label` and hand-label a few hundred candidate–job pairs across categories/seniorities/languages. This is tedious and it is the most valuable thing you will do on this project.
2. Stand up the eval harness (Ragas/DeepEval) so you can score *anything* you build next.

**Phase B — Validate retrieval.**
3. Wire hybrid retrieval (pgvector dense + `tsvector` BM25 + RRF) with metadata pre-filtering, using BGE-M3.
4. Add the cross-encoder reranker.
5. Measure Recall@10 / MRR / nDCG@10, sliced. Fix retrieval until it clears a bar *before* touching the LLM. (This step alone will teach you more than the LLM step.)

**Phase C — Validate generation (close your "never validated" blocker).**
6. Add the structured, schema-constrained match-reasoning layer. Run it against **real** models, not mocks.
7. Measure faithfulness + score calibration against your labels. Iterate prompts, versioned, proving each change on the eval set.

**Phase D — Productionize the AI path.**
8. Swap Ollama → vLLM; add Redis caching (closes another blocker); produce the cost/latency table.
9. Wire user feedback → `match_label`. Show one feedback-driven iteration that moved a metric.

Each phase ends with numbers, not vibes. If a phase doesn't produce a metric, it isn't finished.

---



## 11. The hard challenges you should expect to fight

- **Building a trustworthy eval set is harder than building the model.** Your labels *are* your ground truth; if they're noisy or biased (you labeling in a rush), every downstream number is a lie. Label carefully, write down your labeling criteria, and have someone else label a sample to check agreement.
- **Retrieval-vs-generation attribution.** When a match is bad, your instrumentation must tell you *which stage* failed. The cautionary tale in §8 is the whole reason this matters. Separate metrics, always.
- **Structured reliability under real load.** LLMs occasionally emit malformed or hallucinated output. Constrained decoding + Pydantic validation + retry + deterministic fallback is what makes it a service instead of a flaky demo.
- **The Khmer/low-resource-language gap.** Your multilingual slice will underperform. This is not a bug to hide; it's the most *interesting and defensible* part of the project (see §13). Embedding models are weaker on Khmer; you may need translation-augmented retrieval or a multilingual embedder tuned on your data.
- **Cold start.** A brand-new candidate or freshly posted job has no interaction history. Content-based retrieval (which is what this whole system is) handles cold start far better than collaborative filtering — a real argument for the RAG framing over a classic recommender.
- **The offline–online gap.** A system that scores well on your static eval set can still disappoint real users (distribution shift, unlabeled query types). The feedback flywheel is what closes this gap; treat offline eval as necessary but not sufficient.
- **LLM-judge self-deception.** Covered in §8 — position bias, length bias, judge blind spots. The danger is that a biased judge makes your numbers *look* great while quality stagnates.

---



## 12. How to evaluate *your* solution (the scorecard)

You've succeeded when you can hand a reviewer this table, filled with real numbers from *your* eval set:


| Stage      | Metric                                  | Your number | Sliced by                           |
| ---------- | --------------------------------------- | ----------- | ----------------------------------- |
| Retrieval  | Recall@10, MRR, nDCG@10                 | ?           | category / seniority / **language** |
| Generation | Faithfulness (groundedness)             | ?           | —                                   |
| Generation | Score↔human-label correlation           | ?           | —                                   |
| Generation | Answer relevance                        | ?           | —                                   |
| Serving    | p50 / p99 latency per match             | ?           | per stage                           |
| Serving    | Cost per 1,000 matches                  | ?           | Ollama vs. vLLM                     |
| Serving    | Cache hit rate                          | ?           | —                                   |
| Loop       | Metric delta after 1 feedback iteration | ?           | —                                   |


Plus: a short write-up explaining *why* each number is what it is, and what you'd fix next. The write-up is as important as the table.

---



## 13. How to push it to research / industry level

- **Industry:** the scorecard + a clean architecture write-up + the cost table *is* a strong applied-AI-engineer portfolio piece — and, given your entrepreneurship interest, JobFits' defensible unit economics and quality story. Deploy it, run it against real (even synthetic-but-realistic) traffic for a few weeks, and produce a reliability report alongside the quality one.
- **Research:** the genuinely novel angle is **multilingual, low-resource-language job matching and its evaluation.** Rigorous RAG evaluation on Khmer/English CV–JD matching is under-served. A study that (a) benchmarks hybrid retrieval + rerank across the two languages, (b) documents where embedding models fail on Khmer, and (c) proposes and measures a mitigation (translation-augmented retrieval, fine-tuned embedder, or cross-lingual reranking) is a legitimate applied paper for a workshop. Your data access and local-language insight are a real advantage here that most researchers don't have.

---



## 14. Your first week (concrete next actions)

1. Create the `match_label` table and hand-label ~100 candidate–job pairs. Write down your labeling rubric first.
2. Stand up Ragas (or DeepEval) against a tiny slice so you can score *something* end-to-end, even a dummy pipeline.
3. Add pgvector + a `tsvector` column to your Postgres; embed your existing job corpus with BGE-M3 (or Nomic-embed-text locally to move fast).
4. Implement hybrid retrieve → RRF → measure Recall@10 on your 100 labels. Get a baseline number. That number is where the real project begins.

Everything after that is: improve a stage, re-measure, prove it moved. One number at a time.

---



## 15. Toolkit for this project (current as of mid-2026)

- **Vector store:** pgvector (in your existing Postgres) + `tsvector` for BM25. Qdrant/Chroma if scale demands.
- **Embeddings:** BGE-M3 (hybrid dense+sparse, multilingual — production); Qwen3-Embedding (instruction-aware, benchmark it); Nomic-embed-text (laptop/Ollama dev).
- **Reranker:** BGE-reranker-v2 or Qwen3-Reranker (cross-encoder).
- **Fusion:** Reciprocal Rank Fusion (RRF).
- **LLM serving:** Ollama (dev) → vLLM (prod, continuous batching, JSON-schema constrained decoding, OpenAI-compatible); SGLang if prefix reuse dominates.
- **Structured output:** JSON-schema / grammar-constrained decoding + Pydantic validation.
- **Evaluation:** Ragas (canonical metrics, LLM-as-judge, synthetic set generation); DeepEval (pytest-style, component-level); your own labeled `match_label` set as ground truth.
- **Caching:** Redis (exact + optional semantic), keyed on model_version + prompt_version.
- **Ops:** your existing Cloud Run; add Cloud Scheduler heartbeat + Redis (closes two of your known JobFits blockers along the way).

---

*The one sentence to keep: **retrieval is your cost and quality lever; evaluation is your credibility; the feedback loop is your moat.** Build the eval harness first, fix retrieval before the LLM, and never ship a match number you can't defend.*