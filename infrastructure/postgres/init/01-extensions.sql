-- Enabled once at cluster initialization; Alembic migrations assume these exist.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
