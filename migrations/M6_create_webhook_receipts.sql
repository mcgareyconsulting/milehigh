-- M6: Create webhook_receipts table
-- Run AFTER M5.

CREATE TABLE IF NOT EXISTS webhook_receipts (
    id SERIAL PRIMARY KEY,
    receipt_hash VARCHAR(64) UNIQUE NOT NULL,
    provider VARCHAR(32) NOT NULL DEFAULT 'procore',
    resource_id VARCHAR(64),
    received_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_webhook_receipts_received_at ON webhook_receipts(received_at);
