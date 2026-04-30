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
        if "date_recorded" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN date_recorded DATE"))
        if "recorder_person_id" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN recorder_person_id INTEGER"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_people_name ON people (name)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_places_name ON places (name)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS memory_people (
                id INTEGER PRIMARY KEY,
                memory_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                role VARCHAR(20) DEFAULT 'mentioned',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(memory_id, person_id)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_people_memory_id ON memory_people (memory_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_people_person_id ON memory_people (person_id)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS memory_places (
                id INTEGER PRIMARY KEY,
                memory_id INTEGER NOT NULL,
                place_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(memory_id, place_id)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_places_memory_id ON memory_places (memory_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_places_place_id ON memory_places (place_id)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS person_aliases (
                id INTEGER PRIMARY KEY,
                person_id INTEGER NOT NULL,
                alias VARCHAR(120) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_person_aliases_person_id ON person_aliases (person_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_person_aliases_alias ON person_aliases (alias)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
