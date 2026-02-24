"""
Generator core logic. Framework-agnostic.
"""
import json
import logging
import time
from src.db import SessionLocal, JobApplication, ProfessionalAsset
from src.metrics import generator_latency, generator_errors
from src.generator.prompts import build_cover_letter_prompt, build_cv_variant_prompt
from src.generator.claude_client import generate

logger = logging.getLogger(__name__)


def _get_asset(db, asset_type: str) -> str:
    asset = db.query(ProfessionalAsset).filter_by(asset_type=asset_type, is_active=True).first()
    return asset.content if asset else ''


def _parse_contact_name(contact_json: str) -> str:
    try:
        return json.loads(contact_json).get('name', 'the candidate')
    except Exception:
        return 'the candidate'


def generate_applications(job_ids: list[str]) -> list[dict]:
    """
    Generate cover letter and CV variant for each job.
    Updates cover_letter_draft, cv_variant_generated, and status='drafted' in the database.
    """
    db = SessionLocal()
    results = []
    failed = 0

    try:
        assets = {
            'narrative': _get_asset(db, 'narrative'),
            'employment_history': _get_asset(db, 'employment_history'),
            'projects_summary': _get_asset(db, 'projects_summary'),
            'tech_stack': _get_asset(db, 'tech_stack'),
            'writing_style': _get_asset(db, 'writing_style'),
            'contact_info': _get_asset(db, 'contact_info'),
        }
        contact_name = _parse_contact_name(assets['contact_info'])

        for job_id in job_ids:
            start = time.time()
            try:
                job = db.query(JobApplication).filter_by(id=job_id).first()
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    failed += 1
                    continue

                if not job.job_description:
                    logger.warning(f"Job {job_id} has no description, skipping")
                    failed += 1
                    continue

                # Cover letter
                cover_letter_prompt = build_cover_letter_prompt(
                    job_title=job.job_title,
                    company_name=job.company_name,
                    job_description=job.job_description,
                    reasoning_explanation=job.reasoning_explanation or '',
                    narrative=assets['narrative'],
                    employment_history=assets['employment_history'],
                    projects_summary=assets['projects_summary'],
                    writing_style=assets['writing_style'],
                    contact_name=contact_name,
                )

                try:
                    cover_letter = generate(cover_letter_prompt)
                except Exception as e:
                    generator_errors.labels(error_type='api_error').inc()
                    logger.error(f"Claude API error for {job_id}: {e}")
                    failed += 1
                    continue

                if not cover_letter or len(cover_letter) < 100:
                    generator_errors.labels(error_type='invalid_response').inc()
                    logger.warning(f"Cover letter too short for {job_id}: {len(cover_letter)} chars")
                    failed += 1
                    continue

                # CV variant
                cv_prompt = build_cv_variant_prompt(
                    job_title=job.job_title,
                    job_description=job.job_description,
                    employment_history=assets['employment_history'],
                    projects_summary=assets['projects_summary'],
                    tech_stack=assets['tech_stack'],
                    contact_name=contact_name,
                )

                try:
                    cv_variant = generate(cv_prompt, max_tokens=600)
                except Exception as e:
                    logger.warning(f"CV variant generation failed for {job_id}: {e}")
                    cv_variant = None  # Non-fatal

                job.cover_letter_draft = cover_letter
                job.cv_variant_generated = cv_variant
                job.status = 'drafted'
                db.commit()

                elapsed = time.time() - start
                generator_latency.observe(elapsed)

                results.append({'job_id': job_id, 'status': 'drafted'})
                logger.info(f"Generated application for {job_id} ({elapsed:.1f}s)")

            except Exception as e:
                generator_errors.labels(error_type='error').inc()
                logger.error(f"Unexpected error generating for {job_id}: {e}")
                failed += 1

    finally:
        db.close()

    return results, failed
