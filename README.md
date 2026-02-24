# Job Snatcher

Automated job discovery, matching, and application pipeline.

## The Problem

Job applications are a repetitive admin task. Find job, add to spreadsheet, research company, write cover letter, send — a lot of time for uncertain ROI and exposing ourselves to an emotional rollercoaster of hopes and dashed dreams.

The thing is: we are not our cover letter. Professional experience lives in STAR stories and employment history. Passions can be expressed on GitHub. A good cover letter just holds these up to a mirror of the job posting.

I've been doing this manually. This project automates it.

## How It Works

Five microservices, orchestrated by Airflow:

```text
Job URL → Ingest → Cosine Match → LLM Reasoning → Combine Scores → Generate → Human Review
```

1. **Ingester** — fetches and parses job postings (Duunitori, LinkedIn, Indeed, generic)
2. **Cosine Matcher** — semantic similarity between job description and your professional narrative (sentence-transformers)
3. **Reasoning Matcher** — local LLM on gaming PC reasons about fit, explains why/why not
4. **Generator** — Claude writes a tailored CV and cover letter, reflecting STAR stories and GitHub
5. **Curator** — you review drafts, approve or edit before anything gets sent

Only high-scoring jobs reach the generator. Only approved drafts go anywhere.

## Stack

| Layer            | Tech                                      |
| ---------------- | ----------------------------------------- |
| Services 1–4     | Python, FastAPI                           |
| Service 5        | TypeScript, Fastify (Curator)             |
| Orchestration    | Apache Airflow                            |
| Database         | PostgreSQL + SQLAlchemy                   |
| Embeddings       | sentence-transformers (all-MiniLM-L6-v2)  |
| LLM (reasoning)  | Ollama on gaming PC (Wake-on-LAN)         |
| LLM (generation) | Claude API (prod) / local Ollama (dev)    |
| Observability    | Prometheus + Grafana                      |
| Infrastructure   | Docker Compose → k3s later                |

## Setup

```bash
# 1. Copy and fill in environment
cp .env.example .env

# 2. Start Postgres
docker-compose up postgres -d

# 3. Initialise DB and load your professional assets
python3 -m scripts.init_db
python3 -m scripts.fetch_github_projects   # auto-generates projects_summary.json
python3 -m scripts.load_assets

# 4. Start services
uvicorn src.ingester.main:app --port 5001 --reload
uvicorn src.matchers.cosine.main:app --port 5002 --reload
# ... etc
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical design and [decisions.md](decisions.md) for key choices made during development.

## Professional Assets

Your data lives in `assets/` (gitignored — contains PII). Copy from `assets.example/` as a template:

- `professional_narrative.md` — career story and STAR achievements
- `employment_history.json` — roles and accomplishments
- `writing_style.md` — how you write, your voice
- `tech_stack.yaml` — languages, tools, certifications
- `contact_info.json` — name, GitHub URL (used to auto-generate project summaries)

## LLM Backends

Controlled by `GENERATOR_LLM` in `.env`:

| Value           | When to use                                     |
| --------------- | ----------------------------------------------- |
| `ollama_local`  | Development — Mistral/Llama on your Mac         |
| `ollama_gaming` | Mid-tier — Ollama on gaming PC (woken via WoL)  |
| `claude`        | Production — best quality cover letters         |

## Status

- [x] Ingester (Duunitori, LinkedIn, Indeed, generic parser)
- [x] Cosine matcher
- [x] Reasoning matcher (Ollama + Wake-on-LAN)
- [x] Score combiner
- [x] Application generator
- [x] Curator approval service (TypeScript/Fastify)
- [x] Airflow DAG
- [ ] Tests
- [ ] k3s deployment
