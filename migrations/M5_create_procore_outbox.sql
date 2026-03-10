-- M5: Create procore_outbox table
-- Run AFTER M4.

CREATE TABLE IF NOT EXISTS procore_outbox (
    id SERIAL PRIMARY KEY,
    submittal_id VARCHAR(255) NOT NULL,
    project_id INTEGER NOT NULL,
    action VARCHAR(50) NOT NULL,
    request_payload JSON,
    source_application_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    next_retry_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_procore_outbox_submittal ON procore_outbox(submittal_id);
CREATE INDEX IF NOT EXISTS ix_procore_outbox_project ON procore_outbox(project_id);
