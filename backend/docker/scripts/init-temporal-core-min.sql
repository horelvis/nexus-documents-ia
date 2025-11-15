-- Minimal core schema bootstrap for Temporal: only schema_version in temporal schema
CREATE SCHEMA IF NOT EXISTS temporal AUTHORIZATION postgres;
SET search_path TO temporal;

CREATE TABLE IF NOT EXISTS schema_version (
    version_partition INT NOT NULL,
    db_name VARCHAR(255) NOT NULL,
    creation_time TIMESTAMP,
    curr_version VARCHAR(64),
    min_compatible_version VARCHAR(64),
    PRIMARY KEY (version_partition, db_name)
);

INSERT INTO schema_version (version_partition, db_name, creation_time, curr_version, min_compatible_version)
VALUES (0, 'nexus_db', NOW(), '1.0.0', '1.0.0')
ON CONFLICT (version_partition, db_name) DO NOTHING;
