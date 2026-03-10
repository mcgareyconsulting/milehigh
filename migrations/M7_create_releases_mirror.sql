-- Create releases with same schema as jobs + 3 sandbox-only extra columns
CREATE TABLE releases (
    id SERIAL PRIMARY KEY,
    job INTEGER NOT NULL,
    release VARCHAR(16) NOT NULL,
    job_name VARCHAR(128) NOT NULL,
    description VARCHAR(256),
    fab_hrs FLOAT,
    install_hrs FLOAT,
    paint_color VARCHAR(64),
    pm VARCHAR(16),
    "by" VARCHAR(16),
    released DATE,
    fab_order FLOAT,
    cut_start VARCHAR(8),
    fitup_comp VARCHAR(8),
    welded VARCHAR(8),
    paint_comp VARCHAR(8),
    ship VARCHAR(8),
    start_install DATE,
    start_install_formula VARCHAR(256),
    "start_install_formulaTF" BOOLEAN,
    comp_eta DATE,
    job_comp VARCHAR(8),
    invoiced VARCHAR(8),
    notes VARCHAR(256),
    trello_card_id VARCHAR(64) UNIQUE,
    trello_card_name VARCHAR(256),
    trello_list_id VARCHAR(64),
    trello_list_name VARCHAR(128),
    trello_card_description VARCHAR(512),
    trello_card_date DATE,
    viewer_url VARCHAR(512),
    last_updated_at TIMESTAMP,
    source_of_update VARCHAR(16),
    -- Sandbox-only columns (NULL until Trello webhook shadow mode populates them)
    stage VARCHAR(128),
    stage_group VARCHAR(64),
    banana_color VARCHAR(16),
    CONSTRAINT _job_release_uc_releases UNIQUE (job, release)
);

-- One-time seed from jobs
INSERT INTO releases (
    id, job, release, job_name, description, fab_hrs, install_hrs, paint_color, pm, "by",
    released, fab_order, cut_start, fitup_comp, welded, paint_comp, ship, start_install,
    start_install_formula, "start_install_formulaTF", comp_eta, job_comp, invoiced, notes,
    trello_card_id, trello_card_name, trello_list_id, trello_list_name,
    trello_card_description, trello_card_date, viewer_url, last_updated_at, source_of_update
)
SELECT
    id, job, release, job_name, description, fab_hrs, install_hrs, paint_color, pm, "by",
    released, fab_order, cut_start, fitup_comp, welded, paint_comp, ship, start_install,
    start_install_formula, "start_install_formulaTF", comp_eta, job_comp, invoiced, notes,
    trello_card_id, trello_card_name, trello_list_id, trello_list_name,
    trello_card_description, trello_card_date, viewer_url, last_updated_at, source_of_update
FROM jobs;

-- Sync sequence to avoid future ID collisions
SELECT setval('releases_id_seq', (SELECT MAX(id) FROM releases));
