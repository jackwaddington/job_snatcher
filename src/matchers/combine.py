"""
Score combiner — in-process (no HTTP service needed).

Called directly by the Airflow DAG after cosine and reasoning matchers.

Formula: combined = (0.3 * cosine_score) + (0.7 * reasoning_score)

Jobs without a reasoning score (cosine < threshold, skipped) keep
combined_score = cosine_score so they stay visible but rank low.
"""
import logging
from src.db import SessionLocal, JobApplication

logger = logging.getLogger(__name__)

COSINE_WEIGHT = 0.3
REASONING_WEIGHT = 0.7


def combine_scores(job_ids: list[str]) -> dict:
    """
    Compute combined_match_score for each job_id and persist it.

    Returns:
        {
            'updated': int,
            'skipped': int,   # job not found or no cosine score
            'results': [{'job_id': str, 'combined_score': float}, ...]
        }
    """
    db = SessionLocal()
    updated = 0
    skipped = 0
    results = []

    try:
        for job_id in job_ids:
            job = db.query(JobApplication).filter_by(id=job_id).first()
            if not job:
                logger.warning(f"Job {job_id} not found, skipping")
                skipped += 1
                continue

            cosine = job.cosine_match_score
            if cosine is None:
                logger.warning(f"Job {job_id} has no cosine score, skipping")
                skipped += 1
                continue

            reasoning = job.reasoning_match_score

            if reasoning is not None:
                combined = (COSINE_WEIGHT * cosine) + (REASONING_WEIGHT * reasoning)
            else:
                # Job was below cosine threshold — no reasoning pass ran.
                # Use cosine score directly so it still has a combined score.
                combined = cosine

            combined = round(combined, 4)
            job.combined_match_score = combined
            db.commit()

            results.append({'job_id': job_id, 'combined_score': combined})
            logger.info(
                f"Job {job_id}: cosine={cosine:.3f}, reasoning={reasoning}, combined={combined:.3f}"
            )
            updated += 1

    finally:
        db.close()

    return {'updated': updated, 'skipped': skipped, 'results': results}
