"""
Load professional assets from assets/ directory into the database.
Run after init_db.py:
    python -m scripts.load_assets

Upserts each asset — safe to re-run when you update your files.
"""
import os
from pathlib import Path
from src.db import SessionLocal, ProfessionalAsset

BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets"

ASSET_FILES = {
    "professional_narrative.md": "narrative",
    "employment_history.json": "employment_history",
    "projects_summary.json": "projects_summary",
    "tech_stack.yaml": "tech_stack",
    "contact_info.json": "contact_info",
    "career_goals.md": "career_goals",
    "writing_style.md": "writing_style",
}


def load_assets():
    db = SessionLocal()
    try:
        for filename, asset_type in ASSET_FILES.items():
            filepath = ASSETS_DIR / filename
            if not filepath.exists():
                print(f"  SKIP {filename} (not found)")
                continue

            content = filepath.read_text(encoding="utf-8")

            # Deactivate existing active versions
            existing = (
                db.query(ProfessionalAsset)
                .filter_by(asset_type=asset_type, is_active=True)
                .first()
            )

            if existing:
                if existing.content == content:
                    print(f"  OK   {filename} (unchanged)")
                    continue
                existing.is_active = False
                new_version = existing.version + 1
            else:
                new_version = 1

            asset = ProfessionalAsset(
                asset_type=asset_type,
                content=content,
                version=new_version,
                is_active=True,
            )
            db.add(asset)
            print(f"  LOAD {filename} → {asset_type} (v{new_version})")

        db.commit()
        print("Assets loaded.")
    finally:
        db.close()


if __name__ == "__main__":
    load_assets()
