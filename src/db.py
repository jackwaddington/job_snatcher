from sqlalchemy import (
    create_engine, Column, String, Text, DateTime,
    Float, Boolean, Integer, Index
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid
from src.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Job reference
    job_title = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    job_url = Column(Text, unique=True, nullable=False)
    job_posting_html = Column(Text)

    # Extracted from posting
    job_description = Column(Text)
    required_skills = Column(ARRAY(String))
    seniority_level = Column(String(50))
    employment_type = Column(String(50))
    location = Column(String(255))
    salary_range = Column(String(100))

    # Timeline
    date_found = Column(DateTime, default=datetime.utcnow)
    date_applied = Column(DateTime)
    date_rejection_received = Column(DateTime)
    date_offer_received = Column(DateTime)

    # Workflow status: discovered → matched → drafted → submitted → rejected/offered
    status = Column(String(50), nullable=False, default='discovered')

    # Matching scores
    cosine_match_score = Column(Float)
    reasoning_match_score = Column(Float)
    combined_match_score = Column(Float)
    reasoning_explanation = Column(Text)

    # Application materials
    cover_letter_draft = Column(Text)
    cover_letter_final = Column(Text)
    cv_variant_generated = Column(Text)

    # Metadata
    source = Column(String(50))  # manual, linkedin, indeed, api
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProfessionalAsset(Base):
    __tablename__ = "professional_assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # narrative, employment_history, projects_summary, tech_stack,
    # contact_info, career_goals, writing_style
    asset_type = Column(String(50), nullable=False)

    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Indices
Index('idx_status', JobApplication.status)
Index('idx_date_found', JobApplication.date_found)
Index('idx_combined_score', JobApplication.combined_match_score)
Index('idx_company', JobApplication.company_name)
Index('idx_asset_type_active', ProfessionalAsset.asset_type, ProfessionalAsset.is_active)
