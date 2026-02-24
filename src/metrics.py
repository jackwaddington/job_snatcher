from prometheus_client import Counter, Histogram, Gauge

# Job Ingester
job_ingester_processed = Counter(
    'job_ingester_posts_processed_total',
    'Total job posts processed',
    ['source']
)

job_ingester_errors = Counter(
    'job_ingester_errors_total',
    'Job ingestion errors',
    ['source', 'error_type']
)

# Matchers
matcher_latency = Histogram(
    'job_matcher_latency_seconds',
    'Job matching latency',
    ['matcher_type'],
    buckets=(1, 2, 5, 10, 30, 60)
)

matcher_scores = Histogram(
    'job_matcher_score',
    'Job match scores',
    ['matcher_type'],
    buckets=(0.1, 0.3, 0.5, 0.7, 0.9)
)

matcher_errors = Counter(
    'job_matcher_errors_total',
    'Matching errors',
    ['matcher_type', 'error_type']
)

# WoL
wol_success = Counter(
    'gaming_pc_wol_success_total',
    'WoL wake-up successful attempts'
)

wol_failure = Counter(
    'gaming_pc_wol_failure_total',
    'WoL wake-up failures'
)

gaming_pc_inference_latency = Histogram(
    'gaming_pc_inference_latency_seconds',
    'LLM inference latency on gaming PC',
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
    ['error_type']  # api_error, invalid_response
)

# Applications
applications_pending = Gauge(
    'job_applications_pending_approval',
    'Applications waiting for curator approval'
)

applications_submitted = Counter(
    'applications_submitted_total',
    'Total applications submitted',
    ['source']
)

applications_rejected = Counter(
    'applications_rejected_total',
    'Applications rejected by curator'
)

# Airflow Pipeline
airflow_task_duration = Histogram(
    'airflow_task_duration_seconds',
    'Airflow task execution time',
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
