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
        if "document_filename" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN document_filename VARCHAR(255)"))
        if "document_original_filename" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN document_original_filename VARCHAR(255)"))
        if "document_content_type" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN document_content_type VARCHAR(100)"))
        if "document_size_bytes" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN document_size_bytes INTEGER"))

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
        if "response_to_question_id" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN response_to_question_id INTEGER"))
        if "response_to_question_text" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN response_to_question_text TEXT"))
        if "research_summary" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN research_summary TEXT"))
        if "research_sources_json" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN research_sources_json TEXT"))
        if "research_queries_json" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN research_queries_json TEXT"))
        if "research_suggested_metadata_json" not in columns:
            connection.execute(text("ALTER TABLE memories ADD COLUMN research_suggested_metadata_json TEXT"))
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

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS life_periods (
                id INTEGER PRIMARY KEY,
                title VARCHAR(160) NOT NULL,
                slug VARCHAR(180) UNIQUE,
                start_date_text VARCHAR(100),
                end_date_text VARCHAR(100),
                start_sort DATE,
                end_sort DATE,
                summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_life_periods_title ON life_periods (title)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_life_periods_slug ON life_periods (slug)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS life_events (
                id INTEGER PRIMARY KEY,
                period_id INTEGER,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                event_date_text VARCHAR(100),
                event_date_sort DATE,
                date_precision VARCHAR(20),
                date_year INTEGER,
                date_month INTEGER,
                date_day INTEGER,
                date_decade INTEGER,
                legacy_memory_id INTEGER UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (period_id) REFERENCES life_periods(id) ON DELETE SET NULL,
                FOREIGN KEY (legacy_memory_id) REFERENCES memories(id) ON DELETE SET NULL
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_life_events_period_id ON life_events (period_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_life_events_title ON life_events (title)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_life_events_event_date_sort ON life_events (event_date_sort)"))

        event_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(life_events)")).fetchall()
        }
        if "summary" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN summary TEXT"))
        if "research_summary" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN research_summary TEXT"))
        if "research_sources_json" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN research_sources_json TEXT"))
        if "research_queries_json" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN research_queries_json TEXT"))
        if "research_suggested_edit_json" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN research_suggested_edit_json TEXT"))
        if "location" not in event_columns:
            connection.execute(text("ALTER TABLE life_events ADD COLUMN location VARCHAR(255)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY,
                period_id INTEGER,
                kind VARCHAR(20) NOT NULL DEFAULT 'document',
                title VARCHAR(180),
                storage_filename VARCHAR(255) NOT NULL UNIQUE,
                original_filename VARCHAR(255),
                content_type VARCHAR(100),
                size_bytes INTEGER,
                fingerprint_sha256 VARCHAR(64),
                text_excerpt TEXT,
                captured_at DATETIME,
                captured_at_text VARCHAR(100),
                gps_latitude REAL,
                gps_longitude REAL,
                camera_make VARCHAR(80),
                camera_model VARCHAR(120),
                lens_model VARCHAR(120),
                orientation INTEGER,
                image_width INTEGER,
                image_height INTEGER,
                exif_json TEXT,
                notes TEXT,
                legacy_memory_id INTEGER UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (period_id) REFERENCES life_periods(id) ON DELETE SET NULL,
                FOREIGN KEY (legacy_memory_id) REFERENCES memories(id) ON DELETE SET NULL
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_period_id ON assets (period_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_kind ON assets (kind)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_fingerprint_sha256 ON assets (fingerprint_sha256)"))

        asset_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(assets)")).fetchall()
        }
        if "title" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN title VARCHAR(180)"))
        if "captured_at" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN captured_at DATETIME"))
        if "captured_at_text" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN captured_at_text VARCHAR(100)"))
        if "gps_latitude" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN gps_latitude REAL"))
        if "gps_longitude" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN gps_longitude REAL"))
        if "camera_make" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN camera_make VARCHAR(80)"))
        if "camera_model" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN camera_model VARCHAR(120)"))
        if "lens_model" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN lens_model VARCHAR(120)"))
        if "orientation" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN orientation INTEGER"))
        if "image_width" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN image_width INTEGER"))
        if "image_height" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN image_height INTEGER"))
        if "exif_json" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN exif_json TEXT"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_captured_at ON assets (captured_at)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS event_assets (
                id INTEGER PRIMARY KEY,
                event_id INTEGER NOT NULL,
                asset_id INTEGER NOT NULL,
                relation_type VARCHAR(30) DEFAULT 'evidence',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, asset_id),
                FOREIGN KEY (event_id) REFERENCES life_events(id) ON DELETE CASCADE,
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_event_assets_event_id ON event_assets (event_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_event_assets_asset_id ON event_assets (asset_id)"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS asset_faces (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                bbox_x REAL NOT NULL,
                bbox_y REAL NOT NULL,
                bbox_w REAL NOT NULL,
                bbox_h REAL NOT NULL,
                confidence REAL,
                person_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_asset_faces_asset_id ON asset_faces (asset_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_asset_faces_person_id ON asset_faces (person_id)"))

        # Ensure questions table has source_memory_id and answer_memory_id columns
        q_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(questions)")).fetchall()
        }
        if "source_memory_id" not in q_columns:
            connection.execute(text("ALTER TABLE questions ADD COLUMN source_memory_id INTEGER"))
        if "answer_memory_id" not in q_columns:
            connection.execute(text("ALTER TABLE questions ADD COLUMN answer_memory_id INTEGER"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
