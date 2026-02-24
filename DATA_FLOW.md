# Data Flow in Job Snatcher

How data moves through the system from job discovery to submission.

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          YOU (Human)                                    │
│  - Paste job URLs                                                      │
│  - Approve applications via Slack/dashboard                            │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        AIRFLOW DAG                                      │
│  (Orchestrator - controls task order and data passing)                 │
└─────────────────────────────────────────────────────────────────────────┘
  │
  ├─→ [Ingest Task] ──→ Calls: POST /ingest
  │                      Input: job_urls
  │                      Output: job_ids via xcom
  │
  ├─→ [Cosine Task] ──→ Calls: POST /match
  │                      Input: job_ids
  │                      Output: scores in DB
  │
  ├─→ [Reasoning Task] → Calls: POST /reason
  │                      Input: job_ids
  │                      Output: scores in DB
  │
  ├─→ [Combine Task] ──→ No API call
  │                      Input: job_ids
  │                      Output: combined scores in DB
  │
  ├─→ [Generate Task] → Calls: POST /generate
  │                      Input: job_ids
  │                      Output: cover letters in DB
  │
  └─→ [Curator Task] ──→ Calls: POST /approve-workflow
                         Input: job_ids
                         Output: BLOCKS waiting for you
```

---

## Detailed Data Flow (Step by Step)

### Step 0: You Provide Job URLs

**What happens:**
```
You: "Here are 3 job URLs I want to apply for"
[Manual links in Slack, CSV, or dashboard form]
           ↓
Airflow receives: job_urls = [
  "https://linkedin.com/jobs/123",
  "https://indeed.com/jobs/456",
  "https://example.com/job/789"
]
```

**Data at this point:**
- Just URLs (strings)
- No data in database yet

---

### Step 1: Ingest Task

**What Airflow does:**
```python
job_urls = ["https://linkedin.com/jobs/123", ...]
for url in job_urls:
    response = requests.post('http://localhost:5001/ingest', 
        json={'job_url': url, 'source': 'manual'})
    job_id = response.json()['job_id']
    job_ids.append(job_id)

# Pass to next task
context['task_instance'].xcom_push(key='job_ids', value=job_ids)
```

**What Ingester service does:**
1. Fetch HTML from URL
2. Parse HTML → extract title, company, description, skills, location, salary
3. Insert into `job_applications` table

**Database after Ingest:**
```sql
job_applications table:

id                   | job_title          | company_name  | job_description    | status      | date_found
550e8400-e29b-41d4-a | "Platform Engineer"| "Startup X"   | "We are looking..." | "discovered"| 2026-02-24
660e8400-e29b-41d4-a | "SRE Role"        | "Big Corp"    | "We need an SRE..."| "discovered"| 2026-02-24
...
```

**Data passed to next task:**
```python
job_ids = [
  "550e8400-e29b-41d4-a716-446655440000",
  "660e8400-e29b-41d4-a716-446655440001",
  ...
]
# Via xcom
```

**Metrics emitted:**
```
job_ingester_posts_processed_total{source="manual"} += 3
```

---

### Step 2: Cosine Matcher Task

**What Airflow does:**
```python
job_ids = context['task_instance'].xcom_pull(task_ids='ingest_jobs', key='job_ids')

response = requests.post('http://localhost:5002/match',
    json={'job_ids': job_ids})

# Cosine matcher updated DB directly, just pass job_ids forward
context['task_instance'].xcom_push(key='job_ids', value=job_ids)
```

**What Cosine Matcher service does:**
```
For each job_id:
1. Fetch job description from DB
2. Fetch your professional narrative from DB
3. Generate embeddings for both (using sentence-transformers)
4. Compute cosine similarity (dot product)
5. Score: 0 (completely different) to 1 (identical)
6. UPDATE database: SET cosine_match_score = 0.78
```

**Example calculation:**
```
Your narrative embedding:  [0.2, 0.5, 0.1, 0.3, ...]  (384-dim vector)
Job description embedding: [0.3, 0.4, 0.2, 0.1, ...]  (384-dim vector)

Cosine similarity = dot_product(a, b) / (magnitude(a) * magnitude(b))
                  = 0.78
```

**Database after Cosine:**
```sql
id                  | cosine_match_score | status
550e8400-e29b-41d4-a| 0.78               | "discovered"
660e8400-e29b-41d4-a| 0.42               | "discovered"
```

**Data passed to next task:**
```python
job_ids = [
  "550e8400-e29b-41d4-a716-446655440000",  # cosine: 0.78
  "660e8400-e29b-41d4-a716-446655440001",  # cosine: 0.42
]
```

**Metrics emitted:**
```
job_matcher_latency_seconds{matcher_type="cosine"} histogram += [2.3, 1.9, ...]
job_matcher_score{matcher_type="cosine"} histogram += [0.78, 0.42, ...]
```

---

### Step 3: Reasoning Matcher Task

**What Airflow does:**
```python
job_ids = context['task_instance'].xcom_pull(task_ids='match_cosine', key='job_ids')

response = requests.post('http://localhost:5003/reason',
    json={'job_ids': job_ids, 'min_cosine_score': 0.6})

# Filter to jobs that were actually processed (had cosine > 0.6)
processed_job_ids = [r['job_id'] for r in response.json()['results']]

context['task_instance'].xcom_push(key='job_ids', value=processed_job_ids)
```

**What Reasoning Matcher service does:**
```
For each job_id where cosine_score > 0.6:
1. Check if gaming PC is reachable (ping)
2. If not: wake via WoL (send magic packet)
3. Wait 30 seconds for boot
4. Format prompt with job description + your professional assets
5. Call Ollama API on gaming PC:
   POST http://gaming-pc:11434/api/generate
   Model: neural-chat
   Prompt: "Does this person fit this job? Why/why not?"
6. Parse response JSON (fit assessment, top 3 reasons, confidence)
7. Extract confidence score (0-100)
8. UPDATE database: SET reasoning_match_score = 0.85, reasoning_explanation = "..."
9. Mark gaming PC to sleep after 5 mins idle
```

**Example LLM call:**
```
Input to Ollama:
"You are a hiring advisor. Evaluate if this person fits this job.

JOB: Platform Engineer at Startup X
- Need 5 years Kubernetes
- AWS, Python, DevOps
- High-paced startup

CANDIDATE: Jack
- 10 years operations background
- 2 years Kubernetes (42 School + homelab)
- Strong infrastructure automation thinking
- Python, Docker, systems programming

Is this a good fit?"

Output from Ollama:
{
  "fit_assessment": "Good fit, but experience gap on seniority",
  "top_3_reasons": [
    "Strong infrastructure automation experience aligns with role",
    "Kubernetes knowledge is recent and hands-on (k3s cluster)",
    "Concern: only 2 years K8s vs 5 years required"
  ],
  "confidence": 0.85
}
```

**Database after Reasoning:**
```sql
id                  | cosine | reasoning | reasoning_explanation              | status
550e8400-e29b-41d4-a| 0.78   | 0.85      | "Good fit, experience gap..."     | "discovered"
660e8400-e29b-41d4-a| 0.42   | null      | null (filtered out, cosine<0.6)   | "discovered"
```

**Data passed to next task:**
```python
job_ids = [
  "550e8400-e29b-41d4-a716-446655440000",  # reasoning: 0.85
]
# Note: job 2 filtered out because cosine score was 0.42
```

**Metrics emitted:**
```
gaming_pc_wol_success_total += 1 (or wol_failure if didn't wake)
job_matcher_latency_seconds{matcher_type="reasoning"} += 35.2
gaming_pc_inference_latency_seconds += 32.1
```

---

### Step 4: Combine Scores Task

**What Airflow does:**
```python
job_ids = context['task_instance'].xcom_pull(task_ids='match_reasoning', key='job_ids')

# Call internal function (no HTTP, in-process)
from src.matchers.combine import combine_scores
combine_scores(job_ids)

context['task_instance'].xcom_push(key='job_ids', value=job_ids)
```

**What Combine does:**
```python
def combine_scores(job_ids):
    for job_id in job_ids:
        job = db.query(JobApplication).filter_by(id=job_id).first()
        
        cosine = job.cosine_match_score or 0.0
        reasoning = job.reasoning_match_score or 0.0
        
        # Weight: 30% cosine (fast semantic), 70% reasoning (deep thinking)
        combined = (0.3 * cosine) + (0.7 * reasoning)
        
        job.combined_match_score = combined
        db.commit()
```

**Calculation example:**
```
Job 1:
  cosine_score: 0.78
  reasoning_score: 0.85
  combined: (0.3 * 0.78) + (0.7 * 0.85) = 0.234 + 0.595 = 0.829

Job 2:
  cosine_score: 0.42
  reasoning_score: null (filtered out)
  combined: (0.3 * 0.42) + (0.7 * 0) = 0.126
```

**Database after Combine:**
```sql
id                  | cosine | reasoning | combined | status
550e8400-e29b-41d4-a| 0.78   | 0.85      | 0.829    | "discovered"
```

**Data passed to next task:**
```python
job_ids = ["550e8400-e29b-41d4-a716-446655440000"]
```

---

### Step 5: Generate Applications Task

**What Airflow does:**
```python
job_ids = context['task_instance'].xcom_pull(task_ids='combine_scores', key='job_ids')

response = requests.post('http://localhost:5004/generate',
    json={'job_ids': job_ids})

context['task_instance'].xcom_push(key='job_ids', value=job_ids)
```

**What Generator service does:**
```
For each job_id:
1. Fetch from DB:
   - job description
   - reasoning explanation (why LLM thinks it matches)
   - your professional narrative
   - your employment history
   - your projects

2. Call Claude API:
   POST https://api.anthropic.com/v1/messages
   Model: claude-opus-4-5-20251101
   Prompt: "Write a 3-paragraph cover letter based on..."

3. Parse response → extract 3-paragraph cover letter text

4. Generate CV variant:
   - Take your projects, reorder by relevance to this job
   - Highlight skills that match job requirements
   - Create Markdown version

5. UPDATE database:
   - SET cover_letter_draft = "Dear Hiring Team..."
   - SET cv_variant_generated = "# CV for Platform Engineer..."
   - SET status = 'drafted'
```

**Example Claude call:**
```
Input:
"Write a 3-paragraph cover letter.

JOB: Platform Engineer at Startup X
- They need: Kubernetes, AWS, Python

CANDIDATE: Jack
- Experience: 10 years ops, 2 years K8s (42 School)
- Projects: k3s cluster, Prometheus monitoring, Discord analytics

WHY IT MATCHES:
Your infrastructure thinking aligns with their needs.
Concern: only 2 years K8s vs 5 required.

Write in Jack's voice. Be specific. Avoid clichés."

Output:
"Dear Startup X Team,

I'm excited about the Platform Engineer role because of your infrastructure-first approach. With 10 years in operations and 2 years hands-on with Kubernetes (building a k3s cluster with Prometheus monitoring), I've developed the systems thinking your team needs.

My recent work includes [specific example]. While my Kubernetes experience is recent compared to your 5-year requirement, my infrastructure automation background provides the foundation to grow quickly in this role.

I'd love to discuss how my systems thinking can help your team scale reliably. You can reach me at jack@email.com.

Regards,
Jack"
```

**Database after Generate:**
```sql
id                  | status    | cover_letter_draft                    | cv_variant_generated
550e8400-e29b-41d4-a| "drafted" | "Dear Startup X Team, I'm excited..." | "# CV\n\n## Projects\n- k3s cluster..."
```

**Data passed to next task:**
```python
job_ids = ["550e8400-e29b-41d4-a716-446655440000"]
```

**Metrics emitted:**
```
job_generator_latency_seconds += 7.2
applications_drafted_total += 1
```

---

### Step 6: Curator (Approval) Task

**What Airflow does:**
```python
job_ids = context['task_instance'].xcom_pull(task_ids='generate_applications', key='job_ids')

response = requests.post('http://localhost:5005/approve-workflow',
    json={'job_ids': job_ids, 'min_score': 0.65})

# This BLOCKS. Airflow waits here.
# Curator sends Slack notification, task pauses.
# You approve/reject via Slack button or dashboard.
# Once you decide, curator API updates DB and task resumes.
```

**What Curator service does:**
```
For each job_id:
1. Format Slack notification:
   - Job title: Platform Engineer @ Startup X
   - Scores: 0.78 cosine, 0.85 reasoning, 0.829 combined
   - Why it matches: [first 2 lines of reasoning_explanation]
   - Cover letter preview: [first 100 chars]
   - Buttons: [Approve] [Reject] [Save for Later]

2. Send via Slack webhook

3. Wait for your response (timeout: 24 hours)
   - Poll database for your decision

4. If you approve:
   UPDATE job_applications SET status='submitted', date_applied=NOW()
   Return success

5. If you reject:
   UPDATE job_applications SET status='rejected'
   Return success

6. If timeout (no response):
   Send reminder Slack message
```

**You interact like this:**
```
Slack message arrives:

Job Snatcher Bot:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Platform Engineer @ Startup X

Match Score: 0.829 (Very Good)
- Cosine: 0.78 | Reasoning: 0.85

Why It Matches:
Your infrastructure automation experience aligns...

Cover Letter Preview:
"Dear Startup X Team, I'm excited about..."

[APPROVE] [REJECT] [SAVE FOR LATER]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You click: [APPROVE]
```

**Database after Curator (Approve):**
```sql
id                  | status      | date_applied           | cover_letter_final
550e8400-e29b-41d4-a| "submitted" | "2026-02-24T11:15:00Z" | "Dear Startup X Team, I'm excited..."
```

**Data returned:**
```python
# Airflow task completes
return {
  "approved": 1,
  "rejected": 0,
  "skipped": 0,
  "message": "1 application submitted"
}
```

**Metrics emitted:**
```
applications_submitted_total += 1
job_applications_pending_approval -= 1
```

---

## Summary: Data at Each Stage

| Stage | Data in DB | Status | What's filled |
|-------|-----------|--------|----------------|
| After Ingest | job_url, title, company, description | discovered | Basic info only |
| After Cosine | ↑ + cosine_match_score | discovered | Semantic similarity |
| After Reasoning | ↑ + reasoning_match_score, explanation | discovered | LLM assessment |
| After Combine | ↑ + combined_match_score | discovered | Final score |
| After Generate | ↑ + cover_letter_draft, cv_variant | drafted | Application materials |
| After Curator | ↑ + status, date_applied | submitted | Ready to send |

---

## How JSON Flows Through System

Each service receives JSON, processes, updates DB, returns JSON:

```
Airflow (Python)
    │
    ├─→ requests.post(..., json={...})
    │                            ↓
    │                    [Network]
    │                            ↓
    ┌─────────────────────────────────────────┐
    │ Service (Flask)                         │
    │ @app.route('/endpoint', methods=POST)  │
    │ def handle():                           │
    │   data = request.json  # Parse JSON    │
    │   # Process data                        │
    │   db.update(...)  # Side effect         │
    │   return jsonify({...})  # Return JSON │
    └─────────────────────────────────────────┘
    │                            ↑
    │                    [Network]
    │                            ↓
    └─→ response.json()  # Parse JSON back
        
        Pass result to next task via xcom
```

**JSON flexibility in action:**

If Cosine matcher wants to add a new field later:
```python
# Old response
{"results": [{"job_id": "...", "cosine_match_score": 0.78}]}

# New response (added new field)
{"results": [{"job_id": "...", "cosine_match_score": 0.78, "top_keywords": ["Python", ...]}]}

# Airflow still works - just doesn't use top_keywords
score = result['cosine_match_score']  # Still exists!
```

But if a required field changes:
```python
# Old: {"cosine_match_score": 0.78}
# New: {"score": 0.78}  # Renamed!

# Airflow breaks: KeyError: 'cosine_match_score'
```

**That's why we document the API contract** - to avoid surprises.

---

## Key Insights

1. **Database is the source of truth** - Services only read/write DB
2. **Airflow doesn't know the details** - Just calls HTTP, passes job_ids
3. **Each service is independent** - Can be rewritten, redeployed separately
4. **JSON is the interface language** - Services can be Python, Go, Rust, etc.
5. **xcom passes job_ids, not full records** - Keeps Airflow fast
6. **Curator blocks until you decide** - Async approval workflow
7. **Metrics flow throughout** - Every step is observable
