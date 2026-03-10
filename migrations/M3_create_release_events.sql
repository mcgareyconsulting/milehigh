-- M3: Create release_events table
-- Run AFTER M2.

CREATE TABLE IF NOT EXISTS release_events (
    id SERIAL PRIMARY KEY,
    job INTEGER NOT NULL,
    release VARCHAR(50),
    action VARCHAR(50) NOT NULL,
    payload JSON NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    source VARCHAR(50) NOT NULL,
    internal_user_id INTEGER REFERENCES users(id),
    external_user_id VARCHAR(255),
    is_system_echo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMP,
    CONSTRAINT uq_release_events_hash UNIQUE (payload_hash)
);
