"""
Core ingestion logic. Framework-agnostic — called by main.py.
"""
import logging
from src.db import SessionLocal, JobApplication
from src.metrics import job_ingester_processed, job_ingester_errors
from src.ingester.fetcher import fetch_html, detect_job_source
from src.ingester.validators import url_is_valid
from src.ingester.parsers.generic import parse_generic_posting
from src.ingester.parsers.indeed import parse_indeed_posting
from src.ingester.parsers.linkedin import parse_linkedin_posting

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


class DuplicateJobError(Exception):
    def __init__(self, job_id: str, date_found: str):
        self.job_id = job_id
        self.date_found = date_found


def ingest_job(job_url: str, source: str = 'manual') -> dict:
    """
    Ingest a job posting from a URL.

    Returns a dict with job metadata on success.
    Raises:
        ValueError: Invalid URL
        DuplicateJobError: Job already ingested
        requests.HTTPError: URL unreachable
        ParseError: HTML could not be parsed
    """
    if not url_is_valid(job_url):
        raise ValueError(f"Invalid URL: {job_url}")

    db = SessionLocal()
    try:
        # Idempotency check
        existing = db.query(JobApplication).filter_by(job_url=job_url).first()
        if existing:
            raise DuplicateJobError(
                job_id=str(existing.id),
                date_found=existing.date_found.isoformat(),
            )

        # Fetch HTML
        try:
            html = fetch_html(job_url)
        except Exception as e:
            job_ingester_errors.labels(source=source, error_type='network').inc()
            logger.error(f"Failed to fetch {job_url}: {e}")
            raise

        # Parse
        detected_source = detect_job_source(job_url)
        try:
            if detected_source == 'linkedin':
                parsed = parse_linkedin_posting(html)
            elif detected_source == 'indeed':
                parsed = parse_indeed_posting(html)
            else:
                parsed = parse_generic_posting(html)
        except Exception as e:
            job_ingester_errors.labels(source=source, error_type='parse').inc()
            logger.warning(f"Parse failed for {job_url}, storing raw HTML: {e}")
            # Store raw HTML anyway so it can be manually reviewed later
            job = JobApplication(
                job_url=job_url,
                job_title='[parse failed]',
                company_name='[parse failed]',
                job_posting_html=html,
                source=source,
                status='discovered',
            )
            db.add(job)
            db.commit()
            raise ParseError(f"Could not parse {job_url}: {e}")

        if not parsed.get('title') or not parsed.get('company'):
            job_ingester_errors.labels(source=source, error_type='parse').inc()
            raise ParseError(f"Missing title or company for {job_url}")

        # Insert
        job = JobApplication(
            job_url=job_url,
            job_title=parsed['title'],
            company_name=parsed['company'],
            job_description=parsed.get('description'),
            required_skills=parsed.get('skills') or [],
            seniority_level=parsed.get('seniority'),
            employment_type=parsed.get('employment_type'),
            location=parsed.get('location'),
            salary_range=parsed.get('salary'),
            job_posting_html=html,
            source=source,
            status='discovered',
        )

        try:
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as e:
            job_ingester_errors.labels(source=source, error_type='db').inc()
            db.rollback()
            logger.error(f"DB error inserting {job_url}: {e}")
            raise

        job_ingester_processed.labels(source=source).inc()
        logger.info(f"Ingested: {job.job_title} @ {job.company_name} ({job.id})")

        return {
            'job_id': str(job.id),
            'job_title': job.job_title,
            'company_name': job.company_name,
            'job_url': job.job_url,
            'job_description': job.job_description,
            'required_skills': job.required_skills or [],
            'seniority_level': job.seniority_level,
            'location': job.location,
            'salary_range': job.salary_range,
            'status': job.status,
            'source': job.source,
            'date_found': job.date_found.isoformat(),
            'created_at': job.created_at.isoformat(),
        }
    finally:
        db.close()
