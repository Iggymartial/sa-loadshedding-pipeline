-- schema.sql
-- Runs automatically the first time the MySQL container starts, via
-- docker-compose mounting this file into /docker-entrypoint-initdb.d/.
-- (Only runs on a fresh database - if you change this file later, you'll
-- need to drop the docker volume to re-trigger it, or apply changes manually.)

-- ---------------------------------------------------------------------
-- sources: one row per data source (eskom, capetown, etc).
-- Separated from stage_readings because display_name depends only on
-- the source code, not on any individual reading - repeating "Cape Town"
-- on every single row would be redundant and risks inconsistent spelling
-- if it's ever typed differently in different places. Standard 2NF/3NF
-- reasoning: a non-key attribute should depend on the key, the whole
-- key, and nothing but the key.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

-- Seed the two sources we already know about from the /status endpoint.
-- load.py's get_or_create_source() will add any new ones automatically
-- if the API starts returning additional municipalities, but seeding
-- known values keeps the schema self-documenting for a reader.
INSERT INTO sources (code, display_name) VALUES
    ('eskom', 'Eskom'),
    ('capetown', 'Cape Town')
ON DUPLICATE KEY UPDATE display_name = VALUES(display_name);

-- ---------------------------------------------------------------------
-- stage_readings: the actual time-series data - one row per source per
-- extraction run. This is the table that grows over time.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stage_readings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_id INT NOT NULL,
    stage TINYINT NOT NULL,
    stage_updated DATETIME NOT NULL,   -- when the API says the stage last changed
    recorded_at DATETIME NOT NULL,     -- when OUR extractor pulled this data (UTC)
    raw_file VARCHAR(255) NOT NULL,    -- traceability back to the raw JSON in data/raw/
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    -- Speeds up the most common query shape: "give me the latest
    -- readings for source X", which is exactly what a REST API endpoint
    -- serving this data will need to do.
    INDEX idx_source_recorded (source_id, recorded_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- ingestion_runs: audit log of every load attempt. This is what lets
-- us answer "did the pipeline actually run last night, and did it
-- succeed?" without having to dig through logs.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_at DATETIME NOT NULL,
    status ENUM('success', 'failure') NOT NULL,
    records_fetched INT NOT NULL DEFAULT 0,
    raw_file VARCHAR(255),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
