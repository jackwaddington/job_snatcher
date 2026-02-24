# Job Matcher - Decision Matrix

## For MVP (Phase 1), make these choices:

**What you're building:**
- Manual job entry (you fill form with title/company/URL/description)
- Link submission (paste URL → system scrapes and parses)
- Match jobs against your professional narrative (cosine + reasoning)
- Generate cover letter + CV variants from your assets
- Single source of truth: submission tracker with full history

**Job sources:**
1. Manual entry (forms/CSV import)
2. Link submission (on-demand, you paste URL)
3. LinkedIn daily scraper (Phase 3)
4. Duunitori daily scraper (Phase 3)

### 1. Job Sources?
| Phase | Source | Method | Effort |
|-------|--------|--------|--------|
| Phase 1 | Manual Entry | You fill form/CSV | Minimal (parsing only) |
| Phase 1 | Link Submission | Paste URL → parse | Minimal (HTML parsing) |
| Phase 2 | (Application Gen) | — | New feature |
| Phase 3 | LinkedIn Auto | Scheduled daily scraper | Medium (rate limits) |
| Phase 3 | Duunitori Auto | Scheduled daily scraper | Medium (check API) |

**Decision:** 
- Phase 1: Manual entry + link submission (on-demand CLI)
- Phase 3: Add LinkedIn daily scraper + Duunitori daily scraper
- Skip Indeed (Finland focus → Duunitori better)

---

### 2. Database for MVP?
| Option | Pros | Cons | Recommendation |
|--------|------|------|-----------------|
| SQLite | Fast setup, no external deps, portable | Concurrent writes weak, not great with Airflow | Phase 1 only |
| PostgreSQL | Proper locking, Airflow-native, scalable | More setup, docker-compose needed | ✅ **Use this** |

**Decision:** PostgreSQL in Docker (docker-compose). Phase 2 = move to Proxmox if needed.

---

### 2b. Service Framework (Python services)?

| Option | Pros | Cons |
|--------|------|------|
| Flask | Familiar, simple | No async, no auto-validation, no auto-docs |
| **FastAPI** | Async-native, auto-validates JSON via Pydantic, free Swagger UI at /docs | Slightly more setup |

**Decision:** FastAPI + uvicorn for all Python services (1–4). Pydantic BaseModel classes serve as the API contract documentation. Each service gets `/docs` for free.

---

### 3. Cover Letter Generation (Phase 2)?
| Option | Pros | Cons | Recommendation |
|--------|------|------|-----------------|
| Claude API | Best quality, you already use it | Costs ~$0.01/letter | ✅ **USE THIS** |
| Local LLM (30B) | Free, private | Slower (30B is reasoning, not generation), overkill | Phase 3+ |
| Template-based | Fast, deterministic | Generic, poor quality | Skip |

**Decision:** Use Claude API for cover letters. Save your 30B model for matching reasoning (which it's better at).

---

### 4. Airflow Executor?
| Option | Pros | Cons | Recommendation |
|--------|------|------|-----------------|
| LocalExecutor | Simple, no extra deps, great for Mac Mini | Single-threaded, no parallelism | ✅ **START HERE** |
| CeleryExecutor | Parallel tasks, scales to k3s | Complex setup, needs Redis/RabbitMQ | Phase 2 |
| KubernetesExecutor | Native to k3s | Overkill for Phase 1 | Phase 4 |

**Decision:** LocalExecutor on Mac Mini for Phase 1. Switch to Celery when moving to k3s.

---

### 5. Notification Channel?
| Option | Pros | Cons | Recommendation |
|--------|------|------|-----------------|
| Slack only | Fast, real-time | Requires Slack workspace | ✅ **START HERE** |
| Email | Formal, record-keeping | Slower, easy to miss | Add Phase 2 |
| Web dashboard | Centralized, pretty | Extra work to build | Phase 3 |
| All three | Most useful | Most complex | Phase 3 |

**Decision:** Phase 1 = Slack webhook. Phase 2 = add email + dashboard.

---

### 6. Match Score Threshold (when to notify)?
| Threshold | Likely Matches | False Positives | Recommendation |
|-----------|----------------|-----------------|-----------------|
| 0.5 (cosine + reasoning combined) | Highest | Most | Too noisy |
| 0.65 | Many | Some | ✅ **START HERE** |
| 0.75 | Fewer | Least | Too restrictive |

**Decision:** Start at 0.65. Adjust after 1 week based on how many you actually like.

---

### 7. Gaming PC Sleep Timeout?
| Timeout | Pros | Cons | Recommendation |
|---------|------|------|-----------------|
| Immediate (after each job) | Minimal power use | Slow (WoL overhead), thrashing | Skip |
| 5 minutes | Good balance, cheap | Minimal extra power | ✅ **USE THIS** |
| 30 minutes | Faster for batch jobs | More power use | Maybe later |

**Decision:** 5-minute idle timeout via script on gaming PC.

---

## Quick Checklist for Tuesday (before Wednesday interview)

- [ ] Read through architecture doc (30 mins)
- [ ] Answer the 7 questions above (5 mins) — fill in your choices
- [ ] Create empty Git repo with directory structure (15 mins)
- [ ] Spin up docker-compose.yml with PostgreSQL, Airflow, Prometheus, Grafana (20 mins)
- [ ] Write one test job fixture in `test_data/jobs/test_job.json` (5 mins)
- [ ] Sketch first Airflow DAG (ingest → cosine → notify) on paper (10 mins)

**Total: ~1.5 hours to be "ready" to code on Thursday**

---

## Interview Talking Points (Wednesday)

When they ask "Tell us about a project you've built":

"I'm building a job application automation system that solves a real problem I have: job hunting is repetitive. It's a microservices pipeline:

1. **Ingester** — Takes job URLs, parses HTML, normalizes data
2. **Matchers** — Two parallel strategies:
   - Cosine: Fast semantic similarity (embeddings)
   - Reasoning: Deep fit analysis (30B LLM on local gaming PC, wakes via WoL)
3. **Generator** — Auto-drafts cover letters (Claude API) and CV variants
4. **Curator** — Human approval gate before submission

The whole thing is orchestrated by Apache Airflow, runs in Docker containers, and has full observability: Prometheus metrics flowing to Grafana dashboards. MVP is just job matching + notification. Phase 2 adds generation. Phase 3 automates job discovery.

Why this project?
- **Real problem** — I'm actively job hunting, so it's useful immediately
- **Technical depth** — Microservices, orchestration, LLM integration, infrastructure
- **Learning** — This is how I'm learning Airflow for SRE/Platform Eng work
- **Portfolio** — I can show this as a real system that automates part of my life

The key insight: Instead of 'find job → customize app' (reactive), it's 'here's who I am → show me matching jobs' (proactive). Like Tinder for jobs, but the system does the filtering."

**They'll ask:**
- "Why dual matching strategies?" → Fast + accurate, learns from LLM
- "Why wake the gaming PC?" → Cost + power efficiency, keeps expensive hardware asleep
- "How do you measure success?" → Job submission velocity, match accuracy, offer rate
- "What's hard about this?" → Prompt engineering for reasoning, handling false positives, infrastructure coordination

You've got this. 🎯

---

## After Wednesday Interview

Thursday: Start building. Begin with Task 1 (Git repo + structure) and go from there.

This doc is your north star. Keep it open in VS Code while you code.

---

### 8. Language per Service?

Each service is independent — use the right tool for the job.

| Service | Language | Why |
|---------|----------|-----|
| Ingester | Python | BeautifulSoup, Selenium, requests — all Python-first for scraping |
| Cosine Matcher | Python | `sentence-transformers` is Python only |
| Reasoning Matcher | Python | Ollama client, `wakeonlan` lib — Python wins |
| Generator | Python | Anthropic SDK is best in Python |
| Curator | **TypeScript** | Just HTTP + webhooks, no ML. Jack knows TS. Demonstrates polyglot thinking. |

**Decision:** Python for services 1–4. TypeScript (Fastify) for Curator (service 5).

Curator lives in `services/curator/` (not `src/` which is Python).
