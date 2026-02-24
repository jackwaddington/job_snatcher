"""
Airflow DAG: job_snatcher_pipeline

Orchestrates the full pipeline:
  ingest → cosine_match → reasoning_match → combine_scores → generate → curator_notify

Service endpoints (set via Airflow Variables or environment):
  INGESTER_URL      default http://localhost:5001
  COSINE_URL        default http://localhost:5002
  REASONING_URL     default http://localhost:5003
  GENERATOR_URL     default http://localhost:5004
  CURATOR_URL       default http://localhost:5005

Trigger: scheduled daily, or manually via Airflow UI / API.

Manual trigger with config:
    {"job_urls": ["https://...", "https://..."]}

job_ids flow via XCom between tasks.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from prometheus_client import Counter

from src.matchers.combine import combine_scores
from src.metrics import (
    airflow_dag_success,
    airflow_dag_failure,
    airflow_task_duration,
)

logger = logging.getLogger(__name__)

# ── Service base URLs ────────────────────────────────────────────────────────

def _url(service: str, default: str) -> str:
    return Variable.get(f'{service}_URL', default_var=os.getenv(f'{service}_URL', default))


INGESTER_URL = _url('INGESTER', 'http://localhost:5001')
COSINE_URL = _url('COSINE', 'http://localhost:5002')
REASONING_URL = _url('REASONING', 'http://localhost:5003')
GENERATOR_URL = _url('GENERATOR', 'http://localhost:5004')
CURATOR_URL = _url('CURATOR', 'http://localhost:5005')

# ── Helpers ──────────────────────────────────────────────────────────────────

def _post(url: str, payload: dict, timeout: int = 60) -> dict:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── Task functions ───────────────────────────────────────────────────────────

def ingest_task(**context) -> list[str]:
    """
    Read job_urls from DAG run config, call ingester for each.
    Pushes job_ids XCom → downstream tasks.
    """
    import time
    start = time.time()

    conf = context['dag_run'].conf or {}
    job_urls = conf.get('job_urls', [])

    if not job_urls:
        logger.warning('No job_urls in DAG config — nothing to ingest')
        return []

    job_ids = []
    for url in job_urls:
        try:
            result = _post(f'{INGESTER_URL}/ingest', {'job_url': url, 'source': 'airflow'})
            job_ids.append(result['job_id'])
            logger.info(f"Ingested {url} → {result['job_id']}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                logger.info(f"Duplicate (already ingested): {url}")
            else:
                logger.error(f"Ingest failed for {url}: {e}")
        except Exception as e:
            logger.error(f"Ingest error for {url}: {e}")

    elapsed = time.time() - start
    airflow_task_duration.labels(task_id='ingest').observe(elapsed)

    context['ti'].xcom_push(key='job_ids', value=job_ids)
    logger.info(f"Ingest complete: {len(job_ids)} jobs ingested from {len(job_urls)} URLs")
    return job_ids


def cosine_match_task(**context) -> list[str]:
    """Call cosine matcher. Passes same job_ids downstream."""
    import time
    start = time.time()

    job_ids = context['ti'].xcom_pull(task_ids='ingest', key='job_ids') or []
    if not job_ids:
        logger.warning('No job_ids to match')
        return []

    result = _post(f'{COSINE_URL}/match', {'job_ids': job_ids}, timeout=120)
    logger.info(f"Cosine match: {result['processed']} processed, {result['failed']} failed")

    elapsed = time.time() - start
    airflow_task_duration.labels(task_id='cosine_match').observe(elapsed)

    context['ti'].xcom_push(key='job_ids', value=job_ids)
    return job_ids


def reasoning_match_task(**context) -> list[str]:
    """
    Call reasoning matcher (Ollama on gaming PC).
    Only jobs with cosine_score >= 0.6 are actually processed by the service.
    Returns same job_ids so combine can score all of them.
    """
    import time
    start = time.time()

    job_ids = context['ti'].xcom_pull(task_ids='cosine_match', key='job_ids') or []
    if not job_ids:
        logger.warning('No job_ids for reasoning')
        return []

    try:
        result = _post(f'{REASONING_URL}/reason', {'job_ids': job_ids}, timeout=600)
        logger.info(f"Reasoning: {result['processed']} processed, {result['failed']} failed")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 503:
            logger.warning('Gaming PC unreachable — reasoning skipped for this batch')
        else:
            raise

    elapsed = time.time() - start
    airflow_task_duration.labels(task_id='reasoning_match').observe(elapsed)

    context['ti'].xcom_push(key='job_ids', value=job_ids)
    return job_ids


def combine_scores_task(**context) -> list[str]:
    """In-process score combination — no HTTP call."""
    import time
    start = time.time()

    job_ids = context['ti'].xcom_pull(task_ids='reasoning_match', key='job_ids') or []
    if not job_ids:
        logger.warning('No job_ids to combine')
        return []

    result = combine_scores(job_ids)
    logger.info(f"Combine scores: {result['updated']} updated, {result['skipped']} skipped")

    elapsed = time.time() - start
    airflow_task_duration.labels(task_id='combine_scores').observe(elapsed)

    # Only pass jobs that actually got a combined score
    scored_ids = [r['job_id'] for r in result['results']]
    context['ti'].xcom_push(key='job_ids', value=scored_ids)
    return scored_ids


def generate_task(**context) -> list[str]:
    """
    Call generator for jobs above combined score threshold.
    Threshold: 0.5 (adjust via Airflow Variable GENERATE_THRESHOLD).
    """
    import time
    from src.db import SessionLocal, JobApplication

    start = time.time()
    threshold = float(Variable.get('GENERATE_THRESHOLD', default_var='0.5'))

    job_ids = context['ti'].xcom_pull(task_ids='combine_scores', key='job_ids') or []
    if not job_ids:
        logger.warning('No job_ids to generate')
        return []

    # Filter to jobs above threshold
    db = SessionLocal()
    try:
        qualifying = []
        for job_id in job_ids:
            job = db.query(JobApplication).filter_by(id=job_id).first()
            if job and job.combined_match_score is not None and job.combined_match_score >= threshold:
                qualifying.append(job_id)
            else:
                score = job.combined_match_score if job else None
                logger.info(f"Job {job_id} below threshold ({score} < {threshold}), skipping generation")
    finally:
        db.close()

    if not qualifying:
        logger.info('No jobs above threshold — generation skipped')
        context['ti'].xcom_push(key='job_ids', value=[])
        return []

    result = _post(f'{GENERATOR_URL}/generate', {'job_ids': qualifying}, timeout=300)
    logger.info(f"Generate: {result['processed']} processed, {result['failed']} failed")

    elapsed = time.time() - start
    airflow_task_duration.labels(task_id='generate').observe(elapsed)

    drafted_ids = [r['job_id'] for r in result['results'] if r['status'] == 'drafted']
    context['ti'].xcom_push(key='job_ids', value=drafted_ids)
    return drafted_ids


def curator_notify_task(**context):
    """
    Notify Curator service that drafted jobs are ready for review.
    Curator presents them via Slack/web UI — pipeline completes here.
    Human approval happens asynchronously through Curator.
    """
    import time
    start = time.time()

    job_ids = context['ti'].xcom_pull(task_ids='generate', key='job_ids') or []
    if not job_ids:
        logger.info('No drafted jobs to send to curator')
        return

    try:
        result = _post(f'{CURATOR_URL}/notify', {'job_ids': job_ids}, timeout=30)
        logger.info(f"Curator notified: {result}")
    except Exception as e:
        # Non-fatal — drafts are in DB, curator can be checked manually
        logger.warning(f"Curator notification failed (non-fatal): {e}")

    elapsed = time.time() - start
    airflow_task_duration.labels(task_id='curator_notify').observe(elapsed)


def on_success_callback(context):
    airflow_dag_success.labels(dag_id='job_snatcher_pipeline').inc()


def on_failure_callback(context):
    airflow_dag_failure.labels(dag_id='job_snatcher_pipeline').inc()


# ── DAG definition ───────────────────────────────────────────────────────────

default_args = {
    'owner': 'jack',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='job_snatcher_pipeline',
    description='End-to-end job ingestion, scoring, generation, and curator notification',
    default_args=default_args,
    start_date=datetime(2026, 2, 24),
    schedule_interval='0 8 * * *',  # 08:00 daily
    catchup=False,
    tags=['job_snatcher'],
    on_success_callback=on_success_callback,
    on_failure_callback=on_failure_callback,
) as dag:

    t_ingest = PythonOperator(
        task_id='ingest',
        python_callable=ingest_task,
    )

    t_cosine = PythonOperator(
        task_id='cosine_match',
        python_callable=cosine_match_task,
    )

    t_reasoning = PythonOperator(
        task_id='reasoning_match',
        python_callable=reasoning_match_task,
    )

    t_combine = PythonOperator(
        task_id='combine_scores',
        python_callable=combine_scores_task,
    )

    t_generate = PythonOperator(
        task_id='generate',
        python_callable=generate_task,
    )

    t_curator = PythonOperator(
        task_id='curator_notify',
        python_callable=curator_notify_task,
    )

    t_ingest >> t_cosine >> t_reasoning >> t_combine >> t_generate >> t_curator
