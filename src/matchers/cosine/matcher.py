"""
Cosine matcher core logic. Framework-agnostic.
"""
import logging
import time
from src.db import SessionLocal, JobApplication, ProfessionalAsset
from src.metrics import matcher_latency, matcher_scores, matcher_errors
from src.matchers.cosine.embeddings import embed, cosine_similarity

logger = logging.getLogger(__name__)

MATCHER_TYPE = 'cosine'


def match_jobs(job_ids: list[str]) -> list[dict]:
    """
    Score a list of jobs against the professional narrative using cosine similarity.
    Updates cosine_match_score in the database for each job.
    Returns list of results.
    """
    db = SessionLocal()
    results = []
    failed = 0

    try:
        # Fetch narrative once — reuse across all jobs in this batch
        narrative_asset = (
            db.query(ProfessionalAsset)
            .filter_by(asset_type='narrative', is_active=True)
            .first()
        )
        if not narrative_asset:
            raise RuntimeError("No active professional narrative found in database. Run scripts/load_assets.py first.")

        narrative_embedding = embed(narrative_asset.content)

        for job_id in job_ids:
            start = time.time()
            try:
                job = db.query(JobApplication).filter_by(id=job_id).first()
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    matcher_errors.labels(matcher_type=MATCHER_TYPE, error_type='not_found').inc()
                    failed += 1
                    continue

                if not job.job_description:
                    logger.warning(f"Job {job_id} has no description, skipping")
                    matcher_errors.labels(matcher_type=MATCHER_TYPE, error_type='no_description').inc()
                    failed += 1
                    continue

                job_embedding = embed(job.job_description)
                score = cosine_similarity(narrative_embedding, job_embedding)

                job.cosine_match_score = score
                db.commit()

                elapsed = time.time() - start
                matcher_latency.labels(matcher_type=MATCHER_TYPE).observe(elapsed)
                matcher_scores.labels(matcher_type=MATCHER_TYPE).observe(score)

                results.append({
                    'job_id': job_id,
                    'cosine_match_score': round(score, 4),
                })
                logger.info(f"Cosine score for {job_id}: {score:.3f} ({elapsed:.2f}s)")

            except Exception as e:
                matcher_errors.labels(matcher_type=MATCHER_TYPE, error_type='error').inc()
                logger.error(f"Error scoring job {job_id}: {e}")
                failed += 1

    finally:
        db.close()

    return results, failed
