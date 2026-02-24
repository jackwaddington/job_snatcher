"""
Initialize the database schema.
Run once after `docker-compose up`:
    python -m scripts.init_db
"""
from src.db import engine, Base


def main():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")


if __name__ == "__main__":
    main()
