# Job Snatcher - Technical Architecture & Implementation Guide

**Status:** Ready to build  
**Created:** Feb 24, 2026  
**For:** Claude in VS Code (implementation reference)

---

## Overview

Job Snatcher is a job discovery, matching, and application automation system. You maintain your professional assets once (work history, projects, narrative). The system mixes them with job postings to score fit, draft cover letters, and track everything.

**Core flow:**
```
Job URL → Ingest → Parse → Cosine Match → Reasoning Match → Generate Cover Letter → Curator Approval → Submit
```

**Why this matters:**
- Removes administrative toil (copy-paste, reformatting, rewriting same stories)
- Gives you feedback (match scores tell you what patterns actually work for you)
- Teaches you real infrastructure (Airflow, microservices, observability, LLM placement)
- Solves your actual problem (job hunting right now)

---

## Data Model

### job_applications table (PostgreSQL)

Single source of truth for all applications.

```sql
CREATE TABLE job_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Job reference
    job_title VARCHAR(255) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    job_url TEXT NOT NULL UNIQUE,
    job_posting_html LONGTEXT,        -- full HTML for re-parsing if needed
    
    -- Extracted from posting
    job_description TEXT,
    required_skills TEXT[],            -- array: ['Python', 'Kubernetes', 'SQL']
    seniority_level VARCHAR(50),       -- Junior, Mid, Senior, Lead
    employment_type VARCHAR(50),       -- Full-time, Contract, etc
    location VARCHAR(255),
    salary_range VARCHAR(100),
    
    -- Timeline
    date_found TIMESTAMP DEFAULT NOW(),
    date_applied TIMESTAMP,
    date_rejection_received TIMESTAMP,
    date_offer_received TIMESTAMP,
    
    -- Application workflow status
    status VARCHAR(50) NOT NULL DEFAULT 'discovered',
    -- Values: discovered → matched → drafted → submitted → rejected/offered
    
    -- Matching scores
    cosine_match_score FLOAT,          -- 0-1, embedding similarity
    reasoning_match_score FLOAT,       -- 0-1, LLM assessment
    combined_match_score FLOAT,        -- (0.3 * cosine) + (0.7 * reasoning)
    reasoning_explanation TEXT,        -- why LLM thinks it's a fit
    
    -- Application materials
    cover_letter_draft TEXT,           -- auto-generated, raw
    cover_letter_final TEXT,           -- what you actually sent (post-review)
    cv_variant_generated TEXT,         -- reordered by relevance
    
    -- Metadata
    source VARCHAR(50),                -- 'manual', 'linkedin', 'indeed', 'api'
    notes TEXT,                        -- your manual observations
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indices for common queries
CREATE INDEX idx_status ON job_applications(status);
CREATE INDEX idx_date_found ON job_applications(date_found DESC);
CREATE INDEX idx_combined_score ON job_applications(combined_match_score DESC);
CREATE INDEX idx_company ON job_applications(company_name);
```

### professional_assets table (PostgreSQL)

Your reference data, versioned.

```sql
CREATE TABLE professional_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    asset_type VARCHAR(50) NOT NULL,
    -- Values: 'narrative', 'employment_history', 'projects', 'tech_stack', 'contact_info', 'career_goals'
    
    content LONGTEXT NOT NULL,         -- YAML/JSON/Markdown depending on type
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_asset_type_active ON professional_assets(asset_type, is_active);
```

---

## Component Specifications

### 1. Job Ingester

**Purpose:** Take job URL, fetch & parse HTML, insert into database.

**Container:** `src/ingester/`

**Input:** 
- URL (string)
- Source type (string: 'manual', 'linkedin', 'indeed')

**Output:** 
- Row inserted in `job_applications` table with status='discovered'
- Metrics emitted: `job_ingester_posts_processed_total`, `job_ingester_errors_total`

**Process:**
```
1. Accept job URL
2. Fetch HTML (requests for static, Selenium for JavaScript-heavy)
3. Parse HTML:
   - Extract: title, company, description, requirements
   - Check: required_skills array, seniority_level, employment_type, location
4. Check if URL already in DB (SELECT by job_url)
5. If exists: skip (idempotent)
6. If new: INSERT into job_applications with status='discovered'
7. Emit Prometheus metrics
8. Return job_id or error
```

**Error handling:**
- URL unreachable → log error, emit `job_ingester_errors_total{source,error_type='network'}`, skip
- Parse failure (malformed HTML) → store raw HTML, flag for manual review, emit error
- Duplicate URL → idempotent, return existing job_id
- Database error → retry with backoff, emit error

**Performance target:** Process 50-100 jobs/day without blocking Airflow

**Code location:** `src/ingester/main.py`

---

### 2. Cosine Matcher

**Purpose:** Fast semantic matching using embeddings.

**Container:** `src/matchers/cosine/`

**Input:**
- job_id (UUID)
- job_description (text, from DB)
- your_narrative (text, from DB professional_assets)

**Output:**
- cosine_match_score: 0-1 (float)
- top_keywords: list of matched skills/concepts
- Updates job_applications.cosine_match_score

**Process:**
```
1. Fetch job description from job_applications table
2. Fetch your professional narrative from professional_assets (where asset_type='narrative', is_active=true)
3. Embed both using sentence-transformers (local model, on Mac Mini)
4. Compute cosine similarity
5. Extract top 5 keywords via TF-IDF
6. UPDATE job_applications SET cosine_match_score, extract keywords
7. Emit Prometheus metrics: job_matcher_latency_seconds{matcher_type='cosine'}, job_matcher_score{matcher_type='cosine'}
8. Return score
```

**Implementation details:**
- Use `sentence-transformers/all-MiniLM-L6-v2` (lightweight, 22MB)
- Embeddings cached in memory during DAG run
- No external API calls
- Stateless (can run in parallel)

**Performance target:** <2 seconds per job on Mac Mini M4

**Error handling:**
- Model not loaded → load on startup, emit error
- Empty job description → skip, emit error
- Database error → retry with backoff

**Code location:** `src/matchers/cosine/matcher.py`

---

### 3. Reasoning Matcher (LLM)

**Purpose:** Deep reasoning about job fit using 30B model on gaming PC.

**Container:** `src/matchers/reasoning/`

**Input:**
- job_id (UUID)
- job_description (text)
- employment_history (JSON)
- projects_summary (JSON)
- tech_stack (YAML)
- career_goals (text)

**Output:**
- reasoning_match_score: 0-1 (float)
- reasoning_explanation: text (why this matches or doesn't)
- Updates job_applications.reasoning_match_score, reasoning_explanation

**Process:**
```
1. Query jobs where cosine_match_score > 0.6 (filter to top candidates, save GPU)
2. For each job:
   a. Check if gaming PC is reachable (ping)
   b. If not reachable: Wake via WoL (magic packet to MAC address)
   c. Wait 30 seconds for boot
   d. Fetch professional assets from DB
   e. Format prompt (see below)
   f. Call Ollama API: POST http://gaming-pc-ip:11434/api/generate
   g. Parse response for reasoning + confidence score
   h. UPDATE job_applications with scores + explanation
   i. Emit Prometheus metrics
3. After last job: Let gaming PC idle for 5 mins
4. If idle > 5 mins: SSH into gaming PC, run sleep command
5. Return scores
```

**Prompt template:**
```
You are a hiring advisor evaluating job fit for a candidate.

JOB POSTING:
[job_description]

CANDIDATE PROFILE:
Name: [name from contact_info]
Career Goals: [career_goals]
Employment History:
[employment_history formatted as readable list]

Projects & Technical Work:
[projects_summary with tech stack]

Technical Skills:
[tech_stack]

YOUR TASK:
Evaluate if this is a good fit for the candidate. Respond with ONLY valid JSON:
{
  "fit_assessment": "[one sentence: is this a good fit?]",
  "top_3_reasons": [
    "[reason 1 with specific reference to candidate or job]",
    "[reason 2]",
    "[reason 3]"
  ],
  "confidence": 0.75,
  "concerns": "[any red flags or mismatches]"
}

Be honest. A mediocre fit gets 0.4-0.6. A great fit gets 0.8+.
```

**Implementation details:**
- Use Ollama library: `pip install ollama`
- Model: `neural-chat` or `neural-chat:7b` (7B on gaming PC is faster than 30B)
- Timeout: 5 minutes per job
- WoL: use `wakeonlan` library, MAC address from config
- SSH: paramiko for power cycling if stuck

**Performance target:** 30-60 seconds per job (includes WoL overhead)

**Error handling:**
- Gaming PC doesn't wake → retry WoL 3x, emit `gaming_pc_wol_failure_total`, skip job
- Ollama unreachable → retry 3x, timeout after 5 mins, emit error
- Malformed response → parse gracefully, set score=0, flag for manual review
- Database error → retry with backoff

**Code location:** `src/matchers/reasoning/matcher.py`

---

### 4. Application Generator

**Purpose:** Auto-draft cover letters using Claude API.

**Container:** `src/generator/`

**Input:**
- job_id (UUID)
- job_description (text)
- job_title, company_name (strings)
- reasoning_explanation (text, from reasoning matcher)
- your_narrative (text)
- employment_history (JSON)
- projects_summary (JSON)

**Output:**
- cover_letter_draft: text (3-4 paragraphs, Markdown)
- cv_variant_generated: text (reordered by relevance to job)
- Updates job_applications.cover_letter_draft, cv_variant_generated, status='drafted'

**Process:**
```
1. Fetch job + reasoning explanation from DB
2. Fetch professional assets from DB
3. Generate cover letter:
   a. Format prompt (see below)
   b. Call Claude API: Anthropic client, model='claude-opus-4-5-20251101'
   c. Extract 3-paragraph text from response
   d. Validate: 3+ paragraphs, mentions candidate name, references job
   e. Store in job_applications.cover_letter_draft
4. Generate CV variant:
   a. Parse projects_summary JSON
   b. Extract top 3 projects matching job description keywords
   c. Reorder employment_history to put most relevant at top
   d. Create Markdown-formatted CV with top projects highlighted
   e. Store in job_applications.cv_variant_generated
5. UPDATE status='drafted'
6. Emit Prometheus metrics: job_generator_latency_seconds, applications_drafted_total
7. Return success
```

**Cover letter prompt:**
```
You are an expert cover letter writer. Write a compelling, authentic cover letter.

CANDIDATE INFORMATION:
Name: [name]
Role: [job_title]
Company: [company_name]

JOB DESCRIPTION:
[job_description]

CANDIDATE PROFILE:
[professional_narrative - STAR stories, problems solved]

EMPLOYMENT HISTORY:
[formatted employment_history]

PROJECTS:
[relevant projects from projects_summary]

WHY THIS FIT:
[reasoning_explanation from LLM matcher]

YOUR TASK:
Write a 3-paragraph cover letter:
1. Opening: Why you're genuinely interested in this role (2-3 sentences)
2. Body: How your specific experience matches their needs. Use ONE concrete STAR example from your history that aligns with their job description (3-4 sentences)
3. Closing: Call to action - express enthusiasm, mention next steps (2 sentences)

REQUIREMENTS:
- Write in [candidate]'s authentic voice (professional but genuine)
- Be specific - reference actual skills/projects from their profile
- Mention the company/role by name (shows you read the posting)
- Avoid clichés ("I'm a team player", "I'm passionate about technology")
- Keep it concise - 250-300 words total
- Output ONLY the cover letter text, no preamble or formatting

OUTPUT FORMAT:
Just the cover letter, ready to copy-paste into an email.
```

**Implementation details:**
- Use Anthropic client: `from anthropic import Anthropic`
- API key from environment: `os.getenv('CLAUDE_API_KEY')`
- Temperature: 0.7 (creative but consistent)
- Max tokens: 800
- Retry on rate limit: exponential backoff

**Performance target:** <10 seconds per cover letter

**Error handling:**
- API error → retry 3x, emit error, mark job status='draft_failed'
- Invalid response (no paragraphs) → log, flag for manual review
- Database error → retry with backoff

**Code location:** `src/generator/main.py`

---

### 5. Curator (Approval Gate)

**Purpose:** Human review before submission. You decide what actually gets applied for.

**Container:** `src/curator/`

**Input:**
- jobs with status='drafted' and combined_match_score > threshold (default 0.65)

**Output:**
- Slack notification to you
- Waits for your approval (approve/reject/skip)
- Updates job_applications.status → 'submitted' or 'rejected'
- Updates date_applied (if approved)

**Process:**
```
1. Query: SELECT * FROM job_applications WHERE status='drafted' AND combined_match_score > 0.65 ORDER BY combined_match_score DESC
2. For each job:
   a. Format summary: job title, company, match scores, preview of cover letter
   b. Send Slack notification via webhook:
      - Job: [title] @ [company] (Score: 0.82)
      - Why it matches: [first 2 sentences of reasoning_explanation]
      - Cover letter preview: [first 100 chars of cover_letter_draft]
      - Buttons: [Approve] [Reject] [Save for Later]
   c. Wait for human response (timeout: 24 hours)
   d. If approved:
      - UPDATE status='submitted', date_applied=NOW()
      - Emit metric: applications_submitted_total
   e. If rejected:
      - UPDATE status='rejected'
      - Emit metric: applications_rejected_total
   f. If timeout:
      - Leave status='drafted' (action required)
      - Send reminder notification
3. Return summary of decisions made
```

**Slack integration:**
- Use webhook URL from config: `os.getenv('SLACK_WEBHOOK_URL')`
- Block Kit formatted message for buttons
- Blocks: header, context (scores), divider, cover letter preview

**Implementation details:**
- Slack webhook POST (simple HTTP)
- Or: Slack interactive buttons with callback URL (more complex)
- Start simple: webhook only, you visit dashboard to decide

**Code location:** `src/curator/notifier.py`

---

### 6. Airflow DAG

**File:** `src/airflow_dags/job_snatcher_pipeline.py`

**DAG definition:**
```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'job_snatcher',
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'job_snatcher_pipeline',
    default_args=default_args,
    description='Ingest, match, generate, and track job applications',
    schedule_interval=None,  # Manual trigger for Phase 1, schedule in Phase 3
    start_date=datetime(2026, 2, 24),
    catchup=False,
)

# Tasks
ingest_task = PythonOperator(
    task_id='ingest_jobs',
    python_callable=ingest_jobs,
    op_kwargs={'job_urls': '{{ dag_run.conf.get("job_urls", []) }}'},
    dag=dag,
)

cosine_task = PythonOperator(
    task_id='match_cosine',
    python_callable=match_cosine,
    op_kwargs={'job_ids': '{{ task_instance.xcom_pull(task_ids="ingest_jobs") }}'},
    dag=dag,
)

reasoning_task = PythonOperator(
    task_id='match_reasoning',
    python_callable=match_reasoning,
    op_kwargs={'job_ids': '{{ task_instance.xcom_pull(task_ids="match_cosine") }}'},
    pool='gpu_pool',  # Limit concurrent GPU tasks
    dag=dag,
)

generate_task = PythonOperator(
    task_id='generate_applications',
    python_callable=generate_applications,
    op_kwargs={'job_ids': '{{ task_instance.xcom_pull(task_ids="match_reasoning") }}'},
    dag=dag,
)

curator_task = PythonOperator(
    task_id='curator_approval',
    python_callable=curator_approval,
    op_kwargs={'job_ids': '{{ task_instance.xcom_pull(task_ids="generate_applications") }}'},
    dag=dag,
)

# Dependencies
ingest_task >> cosine_task >> reasoning_task >> generate_task >> curator_task
```

**Task flow:**
```
[Ingest] → [Cosine Match] → [Reasoning Match] → [Generate] → [Curator]
```

**Execution model:**
- Trigger: Manual (you paste job URLs and run the DAG)
- Parallelism: cosine & reasoning can run in parallel if using CeleryExecutor (Phase 2)
- For Phase 1: LocalExecutor, sequential execution
- Logging: All tasks log to Airflow logs (viewable in web UI)

**Scheduling (Phase 3):**
```python
schedule_interval='0 6 * * *',  # Daily 6 AM (discover new jobs)
```

**Code location:** `src/airflow_dags/job_snatcher_pipeline.py`

---

## Professional Assets (Your Data)

These live as files in your Git repo and get loaded into the database:

### assets/professional_narrative.md
STAR stories, problem-solving examples, why you want SRE/Platform Eng. ~500-1000 words.

Example:
```markdown
# Professional Narrative

## Who I Am
10 years in restaurant operations, now transitioning to SRE/Platform Engineering.

## Why SRE/Platform Eng
I'm drawn to systems thinking, infrastructure automation, building tools that remove toil.

## Problem 1: POS System Deployment at Scale
**Situation:** Fafa's expanding to 5 countries, each with different POS systems.
**Task:** Standardize deployment, automate configuration.
**Action:** Built deployment automation, reduced setup time 80%.
**Result:** Faster expansion, fewer manual errors, better visibility.

[more STAR stories...]
```

### assets/employment_history.json
Chronological work history with key accomplishments.

```json
{
  "current": "42 School Student",
  "roles": [
    {
      "title": "Operations Manager",
      "company": "Fafa's",
      "dates": "2020-2023",
      "location": "Helsinki",
      "accomplishments": [
        "Managed POS system deployment across 5 countries",
        "Automated reporting dashboards (SQL + visualization)"
      ]
    },
    ...
  ]
}
```

### assets/projects.json
Personal/school projects with tech stack and descriptions.

```json
{
  "school": [
    {
      "name": "Transcendence",
      "description": "Web-based Pong game with tournament system",
      "technologies": ["TypeScript", "Fastify", "SQLite", "React"],
      "github": "link-to-repo"
    }
  ],
  "homelab": [
    {
      "name": "k3s Kubernetes Cluster",
      "description": "3-node Pi cluster with monitoring",
      "technologies": ["k3s", "Kubernetes", "Prometheus", "Grafana"]
    }
  ]
}
```

### assets/tech_stack.yaml
Organized by category, with proficiency levels.

```yaml
languages:
  - C
  - Python
  - TypeScript
  - Bash

infrastructure:
  - Docker
  - Kubernetes (k3s)
  - Prometheus
  - Grafana
  - Apache Airflow

systems:
  - Systems programming
  - Network programming
  - Socket programming
  - Linux administration
```

### assets/contact_info.json
```json
{
  "name": "Jack Waddington",
  "email": "your@email.com",
  "phone": "+358...",
  "github": "https://github.com/jackwaddington",
  "linkedin": "https://linkedin.com/in/...",
  "portfolio": "https://your-site.com"
}
```

### assets/career_goals.md
Why SRE/Platform Eng matters to you. ~200 words.

---

## Observability & Metrics

### Prometheus Metrics (emit from each component)

```python
# src/metrics.py - all metric definitions

from prometheus_client import Counter, Histogram, Gauge

# Ingester
job_ingester_processed = Counter(
    'job_ingester_posts_processed_total',
    'Total job posts processed',
    ['source']  # labels: 'manual', 'linkedin', 'indeed'
)

job_ingester_errors = Counter(
    'job_ingester_errors_total',
    'Ingestion errors',
    ['source', 'error_type']  # error_type: 'network', 'parse', 'db'
)

# Matchers
matcher_latency = Histogram(
    'job_matcher_latency_seconds',
    'Matching latency',
    ['matcher_type'],  # 'cosine', 'reasoning'
    buckets=(1, 2, 5, 10, 30, 60)
)

matcher_score = Histogram(
    'job_matcher_score',
    'Match scores',
    ['matcher_type'],
    buckets=(0.1, 0.3, 0.5, 0.7, 0.9)
)

matcher_errors = Counter(
    'job_matcher_errors_total',
    'Matching errors',
    ['matcher_type', 'error_type']
)

# WoL
gaming_pc_wol_success = Counter(
    'gaming_pc_wol_success_total',
    'WoL wake-up successes'
)

gaming_pc_wol_failure = Counter(
    'gaming_pc_wol_failure_total',
    'WoL wake-up failures'
)

gaming_pc_inference_latency = Histogram(
    'gaming_pc_inference_latency_seconds',
    'LLM inference latency',
    buckets=(10, 30, 60, 120)
)

# Generator
generator_latency = Histogram(
    'job_generator_latency_seconds',
    'Cover letter generation latency',
    buckets=(1, 5, 10, 20)
)

generator_errors = Counter(
    'job_generator_errors_total',
    'Generation errors',
    ['error_type']  # 'api_error', 'invalid_response'
)

# Curator
applications_pending_approval = Gauge(
    'job_applications_pending_approval',
    'Applications waiting for human approval'
)

applications_submitted = Counter(
    'applications_submitted_total',
    'Applications submitted',
    ['source']  # which job source
)

applications_rejected = Counter(
    'applications_rejected_total',
    'Applications rejected by curator'
)

# Pipeline
airflow_task_duration = Histogram(
    'airflow_task_duration_seconds',
    'Task execution time',
    ['task_id'],
    buckets=(1, 5, 10, 30, 60, 300)
)

airflow_dag_success = Counter(
    'airflow_dag_runs_success_total',
    'Successful DAG runs'
)

airflow_dag_failure = Counter(
    'airflow_dag_runs_failure_total',
    'Failed DAG runs'
)
```

### Grafana Dashboards

**Dashboard 1: Job Hunt Overview**
- Total applications submitted (counter widget)
- Offers received (counter widget)
- Pipeline status (pie chart: discovered/matched/drafted/submitted)
- Match score distribution (histogram)
- Applications over time (line chart)

**Dashboard 2: Pipeline Performance**
- Task execution times (bar chart, by task_id)
- Task failure rates (line chart)
- Cosine matcher latency (p50, p95, p99)
- Reasoning matcher latency (p50, p95, p99)
- Generator latency (p50, p95)

**Dashboard 3: System Health**
- Airflow scheduler uptime (gauge)
- Database connection pool (gauge)
- Gaming PC WoL success rate (%)
- Ollama API availability
- Last 5 DAG run statuses (table)
- Error logs (recent errors)

---

## Testing Strategy

### Unit Tests

Fast, isolated, no database. Test individual functions.

**File:** `tests/unit/`

Examples:
```python
# test_ingester.py
def test_parse_indeed_html():
    html = read_fixture('indeed_sample.html')
    result = parse_indeed_posting(html)
    assert result['title'] == 'Platform Engineer'
    assert result['company'] == 'Startup X'

# test_matchers.py
def test_cosine_high_match():
    job_desc = "Python, Kubernetes, DevOps..."
    narrative = "[your ops background + k3s experience]"
    score = cosine_match(job_desc, narrative)
    assert score > 0.7

def test_cosine_low_match():
    job_desc = "Sales, cold calling, no tech"
    narrative = "[your tech background]"
    score = cosine_match(job_desc, narrative)
    assert score < 0.3
```

### Integration Tests

With real database. Test components talking to each other.

**File:** `tests/integration/`

Examples:
```python
# test_ingester_db.py
def test_ingest_job_inserts_to_db(test_db):
    url = "https://linkedin.com/jobs/..."
    ingest_job(url, source='linkedin')
    
    row = test_db.query(JobApplication).filter_by(job_url=url).first()
    assert row is not None
    assert row.status == 'discovered'

# test_pipeline_e2e.py
def test_full_pipeline(test_db):
    # 1. Ingest
    job_id = ingest_job(url, source='manual')
    # 2. Match
    cosine_score = match_cosine(job_id)
    # 3. Generate
    cover_letter = generate_cover_letter(job_id)
    # 4. Verify all fields updated
    row = test_db.query(JobApplication).filter_by(id=job_id).first()
    assert row.cosine_match_score == cosine_score
    assert row.cover_letter_draft is not None
```

### End-to-End Tests

Full DAG execution with test data.

**File:** `tests/e2e/`

```python
def test_airflow_dag_full_run():
    # Load test job fixtures
    test_jobs = load_fixtures('test_jobs.json')
    
    # Trigger DAG manually
    dag_run = dag.execute(conf={'job_urls': test_jobs})
    
    # Verify pipeline completed
    assert dag_run.state == 'success'
    
    # Check results
    jobs = db.query(JobApplication).filter_by(source='test').all()
    assert len(jobs) == len(test_jobs)
    assert all(job.cosine_match_score is not None for job in jobs)
    assert all(job.cover_letter_draft is not None for job in jobs)
```

### Test Data Fixtures

**File:** `test_data/`

```
test_data/
├── jobs/
│   ├── indeed_sample.html        # real Indeed job HTML
│   ├── linkedin_sample.html
│   └── test_jobs.json
├── narratives/
│   ├── professional_narrative.md
│   ├── employment_history.json
│   └── projects.json
└── expected_outputs/
    ├── parsed_job_expected.json
    ├── cover_letter_expected.md
```

---

## Dashboard UI

**File:** `infra/dashboard.html`

Simple single-page dashboard showing:
- Job discovery pipeline status
- Recent jobs (table: title, company, scores, status)
- Curator pending approvals (clickable buttons: approve/reject)
- Performance graphs (matching latency, submission velocity)
- System health (Prometheus up? Ollama reachable?)

**Tech:** Vanilla HTML + JavaScript + Chart.js (fetch from Prometheus API)

**No heavy framework.** Load Prometheus data directly via API calls.

**Features:**
```html
<h1>Job Snatcher Dashboard</h1>

<!-- Status cards -->
<div class="stats">
  <div class="card">
    <h2>Jobs Discovered</h2>
    <p id="stat-discovered">0</p>
  </div>
  <div class="card">
    <h2>Pending Approval</h2>
    <p id="stat-pending">0</p>
  </div>
  <div class="card">
    <h2>Submitted</h2>
    <p id="stat-submitted">0</p>
  </div>
</div>

<!-- Recent jobs table -->
<h2>Recent Jobs</h2>
<table>
  <thead>
    <tr>
      <th>Title</th>
      <th>Company</th>
      <th>Cosine Score</th>
      <th>Reasoning Score</th>
      <th>Status</th>
      <th>Action</th>
    </tr>
  </thead>
  <tbody id="jobs-table">
    <!-- Populate via API -->
  </tbody>
</table>

<!-- Performance graph -->
<h2>Matching Latency</h2>
<canvas id="latency-chart"></canvas>

<!-- System health -->
<h2>System Health</h2>
<div id="health">
  <p>Prometheus: <span id="health-prometheus">✓</span></p>
  <p>Database: <span id="health-db">✓</span></p>
  <p>Ollama: <span id="health-ollama">✓</span></p>
</div>
```

**JavaScript:**
```javascript
// Fetch job stats from Prometheus
async function loadStats() {
  const discovered = await queryPrometheus('count(job_applications_status{status="discovered"})');
  const pending = await queryPrometheus('job_applications_pending_approval');
  document.getElementById('stat-discovered').textContent = discovered;
  document.getElementById('stat-pending').textContent = pending;
}

// Fetch recent jobs from API
async function loadJobs() {
  const response = await fetch('/api/jobs/recent?limit=10');
  const jobs = await response.json();
  // Render table...
}

// Poll every 30 seconds
setInterval(() => {
  loadStats();
  loadJobs();
}, 30000);
```

---

## Directory Structure

```
job-snatcher/
├── README.md                          # This project: what & why
├── ARCHITECTURE.md                    # Technical spec (this file)
├── DECISIONS.md                       # Design decisions & tradeoffs
│
├── docker-compose.yml                 # Local development: Postgres, Airflow, Prometheus, Grafana
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment variables template
├── .gitignore                         # Standard Python gitignore
│
├── src/
│   ├── __init__.py
│   ├── config.py                      # Configuration from environment
│   ├── metrics.py                     # Prometheus metric definitions
│   ├── db.py                          # SQLAlchemy models & session management
│   │
│   ├── ingester/
│   │   ├── __init__.py
│   │   ├── main.py                    # Entry point: ingest_job(url, source)
│   │   ├── parsers.py                 # parse_indeed(), parse_linkedin(), parse_generic()
│   │   └── fetcher.py                 # Fetch HTML (requests + Selenium)
│   │
│   ├── matchers/
│   │   ├── cosine/
│   │   │   ├── __init__.py
│   │   │   ├── matcher.py             # match_cosine(job_id) → score
│   │   │   └── embeddings.py          # sentence-transformers wrapper
│   │   └── reasoning/
│   │       ├── __init__.py
│   │       ├── matcher.py             # match_reasoning(job_id) → score + explanation
│   │       ├── wol.py                 # Wake-on-LAN logic
│   │       ├── ollama_client.py       # Ollama API wrapper
│   │       └── prompt.py              # Prompt templates
│   │
│   ├── generator/
│   │   ├── __init__.py
│   │   ├── main.py                    # generate_cover_letter(job_id), generate_cv_variant()
│   │   ├── prompts.py                 # Claude API prompt templates
│   │   └── claude_client.py           # Anthropic API wrapper
│   │
│   ├── curator/
│   │   ├── __init__.py
│   │   ├── notifier.py                # curator_approval(job_ids) → send Slack
│   │   └── slack_client.py            # Webhook wrapper
│   │
│   └── airflow_dags/
│       └── job_snatcher_pipeline.py   # Airflow DAG definition
│
├── tests/
│   ├── conftest.py                    # Pytest fixtures
│   ├── unit/
│   │   ├── test_ingester.py
│   │   ├── test_matchers.py
│   │   ├── test_generator.py
│   │   └── test_curator.py
│   ├── integration/
│   │   ├── test_ingester_db.py
│   │   ├── test_pipeline_e2e.py
│   │   └── test_metrics.py
│   └── e2e/
│       └── test_full_pipeline.py
│
├── test_data/
│   ├── jobs/
│   │   ├── indeed_sample.html
│   │   ├── linkedin_sample.html
│   │   └── test_jobs.json
│   ├── narratives/
│   │   ├── professional_narrative.md
│   │   ├── employment_history.json
│   │   ├── projects.json
│   │   ├── tech_stack.yaml
│   │   └── contact_info.json
│   └── expected_outputs/
│       ├── parsed_job_expected.json
│       └── cover_letter_expected.md
│
├── assets/
│   ├── professional_narrative.md      # YOUR STORY (YAML/Markdown)
│   ├── employment_history.json        # YOUR WORK HISTORY (JSON)
│   ├── projects.json                  # YOUR PROJECTS (JSON)
│   ├── tech_stack.yaml                # YOUR SKILLS (YAML)
│   ├── contact_info.json              # YOUR CONTACT INFO (JSON)
│   └── career_goals.md                # WHY SRE/PLATFORM ENG (Markdown)
│
├── infra/
│   ├── docker/
│   │   ├── airflow.Dockerfile         # Airflow container with dependencies
│   │   ├── ingester.Dockerfile        # Ingester container (Phase 2)
│   │   └── matcher.Dockerfile         # Matcher container (Phase 2)
│   ├── kubernetes/
│   │   ├── deployment.yaml            # k3s deployment (Phase 4)
│   │   └── service.yaml               # k3s service (Phase 4)
│   ├── prometheus/
│   │   └── prometheus.yml             # Prometheus scrape config
│   └── grafana/
│       └── dashboards.json            # Grafana dashboard definitions (optional)
│
├── docs/
│   ├── SETUP.md                       # How to get running locally
│   ├── DEPLOYMENT.md                  # How to deploy to k3s (Phase 4)
│   ├── API.md                         # API endpoints (curator, dashboard)
│   └── TROUBLESHOOTING.md             # Common issues & fixes
│
└── scripts/
    ├── init_db.py                     # Initialize database schema
    ├── load_assets.py                 # Load professional assets from files → DB
    └── test_wol.py                    # Test WoL connectivity to gaming PC
```

---

## Task Breakdown (Implementation Order)

### Phase 1: MVP (Job Matching)

**Week 1:**
1. Set up Git repo, directory structure
2. Create docker-compose.yml (Postgres, Prometheus, Grafana, Airflow)
3. Create SQLAlchemy models (job_applications, professional_assets)
4. Create test data fixtures (3-5 real job postings as HTML)
5. Write Job Ingester (parse HTML, insert to DB)
6. Unit tests for ingester (parse correctly, handle errors)
7. Write Cosine Matcher (embeddings, similarity)
8. Unit tests for matchers
9. Create Airflow DAG (ingest → cosine)
10. Test DAG locally

**Week 2:**
11. Add Prometheus metrics to each component
12. Create Grafana dashboards (pipeline status, latency)
13. Write integration tests (ingester + DB + matcher)
14. Write end-to-end test (full DAG run)
15. Create dashboard.html (simple stats + recent jobs)
16. Documentation: SETUP.md, README.md
17. Deploy locally, test with 5-10 real job URLs

**Output:** You can paste job URLs, system scores them, Grafana shows pipeline health.

---

### Phase 2: Application Generation

18. Write Reasoning Matcher (WoL, Ollama integration)
19. Integration tests for reasoning matcher
20. Write Application Generator (Claude API, cover letter prompt)
21. Integration tests for generator
22. Write Curator (Slack notifications, approval)
23. Update Airflow DAG (add generator → curator)
24. Update Grafana dashboards (add submission metrics)
25. Update dashboard.html (show pending approvals, approve/reject buttons)
26. Documentation: Curator workflow, gaming PC setup

**Output:** System auto-generates cover letters, you review + approve via Slack/dashboard, submits.

---

### Phase 3: Automated Job Discovery

27. Write LinkedIn scraper (or use LinkedIn job URLs as feed)
28. Write Indeed scraper
29. Update Airflow DAG (schedule daily)
30. Add email notifications (daily digest of matches)
31. Tracking dashboard (applications per day, offer rate)
32. Documentation: Duunitori/LinkedIn scraper setup

**Output:** System discovers jobs daily, notifies you of top matches, you approve.

---

### Phase 4: Scale to k3s (Optional)

33. Containerize ingester, matchers, generator
34. Create k3s deployments
35. Move PostgreSQL to Proxmox (with backups)
36. Update Prometheus/Grafana to k3s
37. Celery executor for Airflow (distributed tasks)

**Output:** Workers scale across k3s cluster, Airflow orchestrates.

---

## Running Locally (Quick Start)

```bash
# 1. Clone & setup
git clone <repo>
cd job-snatcher
cp .env.example .env

# 2. Start services
docker-compose up -d

# 3. Wait for Postgres to be ready
sleep 5

# 4. Initialize DB
python -m scripts.init_db

# 5. Load your professional assets
python -m scripts.load_assets

# 6. Access services
# Airflow: http://localhost:8080
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
# Dashboard: http://localhost:8000 (after running API server)

# 7. Trigger DAG manually
# Via Airflow UI, or:
# curl -X POST http://localhost:8080/api/v1/dags/job_snatcher_pipeline/dagRuns \
#   -H "Content-Type: application/json" \
#   -d '{"conf": {"job_urls": ["https://example.com/job1"]}}'
```

---

## Success Criteria

**Job Hunting:**
- 15-20 applications per week (vs ~5 manual)
- High-quality matches (better offer rate)
- 10 mins per application (vs 60 mins)

**Technical:**
- Pipeline uptime > 95%
- Cosine latency P95 < 10 seconds
- Reasoning latency P95 < 60 seconds
- Test coverage > 80% on critical paths
- Grafana shows real-time metrics

**Learning:**
- Deep understanding of Airflow DAGs, task orchestration
- Hands-on experience with multi-model LLM placement
- Real prompt engineering with consequences
- Infrastructure thinking (observability, reliability, cost)

---

**This is your spec. Use it to build with Claude in VS Code.**