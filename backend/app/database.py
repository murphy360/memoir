import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./memoir.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_schema_migrations() -> None:
    """Run lightweight SQLite migrations for evolving MVP schema."""
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(memories)")).fetchall()
        }

        if "audio_filename" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN audio_filename VARCHAR(255)"))
        if "audio_content_type" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN audio_content_type VARCHAR(100)"))
        if "audio_size_bytes" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN audio_size_bytes INTEGER"))

        if "recorder_name" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN recorder_name VARCHAR(120)"))
        if "date_precision" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_precision VARCHAR(20)"))
        if "date_year" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_year INTEGER"))
        if "date_month" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_month INTEGER"))
        if "date_day" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_day INTEGER"))
        if "date_decade" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_decade INTEGER"))
        if "people_json" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN people_json TEXT"))
        if "locations_json" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN locations_json TEXT"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
