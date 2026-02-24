"""
Reasoning matcher core logic. Framework-agnostic.
"""
import logging
import time
from src.db import SessionLocal, JobApplication, ProfessionalAsset
from src.metrics import matcher_latency, matcher_scores, matcher_errors
from src.matchers.reasoning.prompt import build_prompt
from src.matchers.reasoning.ollama_client import generate, parse_reasoning_response
from src.matchers.reasoning.wol import wake_and_wait
from src import config

logger = logging.getLogger(__name__)

MATCHER_TYPE = 'reasoning'
MIN_COSINE_SCORE = 0.6  # Only run reasoning on jobs that passed cosine threshold


def _get_asset(db, asset_type: str) -> str:
    asset = db.query(ProfessionalAsset).filter_by(asset_type=asset_type, is_active=True).first()
    return asset.content if asset else ''


def match_jobs(job_ids: list[str]) -> list[dict]:
    """
    Run LLM reasoning on jobs that cleared the cosine threshold.
    Wakes the gaming PC via WoL if needed.
    Updates reasoning_match_score and reasoning_explanation in the database.
    Returns list of results (only jobs that were actually processed).
    """
    db = SessionLocal()
    results = []
    failed = 0

    try:
        # Wake the gaming PC once before processing the batch
        if config.GAMING_PC_MAC_ADDRESS:
            from urllib.parse import urlparse
            parsed = urlparse(config.OLLAMA_BASE_URL)
            ollama_host = parsed.hostname
            ollama_port = parsed.port or 11434
            online = wake_and_wait(config.GAMING_PC_MAC_ADDRESS, ollama_host, ollama_port)
            if not online:
                raise RuntimeError("Gaming PC is not reachable — cannot run reasoning matcher.")
        else:
            logger.warning("GAMING_PC_MAC_ADDRESS not set — skipping WoL, assuming Ollama is already running.")

        # Load professional assets once for the batch
        assets = {
            'contact_info': _get_asset(db, 'contact_info'),
            'career_goals': _get_asset(db, 'career_goals'),
            'employment_history': _get_asset(db, 'employment_history'),
            'projects_summary': _get_asset(db, 'projects_summary'),
            'tech_stack': _get_asset(db, 'tech_stack'),
        }

        for job_id in job_ids:
            start = time.time()
            try:
                job = db.query(JobApplication).filter_by(id=job_id).first()
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    failed += 1
                    continue

                # Filter: only run on jobs that passed cosine
                if (job.cosine_match_score or 0) < MIN_COSINE_SCORE:
                    logger.info(f"Skipping {job_id}: cosine {job.cosine_match_score} < {MIN_COSINE_SCORE}")
                    continue

                if not job.job_description:
                    logger.warning(f"Job {job_id} has no description, skipping")
                    failed += 1
                    continue

                prompt = build_prompt(
                    job_description=job.job_description,
                    contact_info=assets['contact_info'],
                    career_goals=assets['career_goals'],
                    employment_history=assets['employment_history'],
                    projects_summary=assets['projects_summary'],
                    tech_stack=assets['tech_stack'],
                )

                raw_response = generate(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL, prompt)
                parsed = parse_reasoning_response(raw_response)

                score = parsed['confidence']
                explanation = (
                    f"{parsed['fit_assessment']}\n\n"
                    f"Reasons:\n" + '\n'.join(f"- {r}" for r in parsed['top_3_reasons']) +
                    (f"\n\nConcerns: {parsed['concerns']}" if parsed['concerns'] else '')
                )

                job.reasoning_match_score = score
                job.reasoning_explanation = explanation
                db.commit()

                elapsed = time.time() - start
                matcher_latency.labels(matcher_type=MATCHER_TYPE).observe(elapsed)
                matcher_scores.labels(matcher_type=MATCHER_TYPE).observe(score)

                results.append({
                    'job_id': job_id,
                    'reasoning_match_score': round(score, 4),
                    'reasoning_explanation': explanation,
                })
                logger.info(f"Reasoning score for {job_id}: {score:.3f} ({elapsed:.1f}s)")

            except Exception as e:
                matcher_errors.labels(matcher_type=MATCHER_TYPE, error_type='error').inc()
                logger.error(f"Error reasoning about job {job_id}: {e}")
                failed += 1

    finally:
        db.close()

    return results, failed
