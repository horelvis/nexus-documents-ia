-- Initialize TemporalIO schema for PostgreSQL
-- This script creates the basic schema structure needed by TemporalIO

-- Create schema_version table
CREATE TABLE IF NOT EXISTS schema_version (
    version_partition INT NOT NULL,
    db_name VARCHAR(255) NOT NULL,
    creation_time TIMESTAMP,
    curr_version VARCHAR(64),
    min_compatible_version VARCHAR(64),
    PRIMARY KEY (version_partition, db_name)
);

-- Insert initial schema version
INSERT INTO schema_version (version_partition, db_name, creation_time, curr_version, min_compatible_version)
VALUES (0, 'nexus_db', NOW(), '1.0.0', '1.0.0')
ON CONFLICT (version_partition, db_name) DO NOTHING;

-- Create schema_update_history table
CREATE TABLE IF NOT EXISTS schema_update_history (
    version_partition INT NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    update_time TIMESTAMP NOT NULL,
    description VARCHAR(255),
    manifest_md5 VARCHAR(64),
    new_version VARCHAR(64),
    old_version VARCHAR(64),
    PRIMARY KEY (version_partition, year, month, update_time)
);

-- Create namespaces table
CREATE TABLE IF NOT EXISTS namespaces (
    partition_id INT NOT NULL,
    id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    notification_version BIGINT NOT NULL,
    data BYTEA,
    data_encoding VARCHAR(16),
    is_global BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (partition_id, id)
);

-- Create namespace_metadata table
CREATE TABLE IF NOT EXISTS namespace_metadata (
    partition_id INT NOT NULL,
    notification_version BIGINT NOT NULL,
    PRIMARY KEY (partition_id)
);

-- Create shards table
CREATE TABLE IF NOT EXISTS shards (
    shard_id INT NOT NULL,
    range_id BIGINT NOT NULL,
    data BYTEA,
    data_encoding VARCHAR(16),
    PRIMARY KEY (shard_id)
);

-- Create executions table
CREATE TABLE IF NOT EXISTS executions (
    namespace_id VARCHAR(255) NOT NULL,
    workflow_id VARCHAR(255) NOT NULL,
    run_id VARCHAR(255) NOT NULL,
    start_time TIMESTAMP,
    execution_time TIMESTAMP,
    workflow_type_name VARCHAR(255),
    workflow_status INT,
    close_time TIMESTAMP,
    history_length BIGINT,
    memo BYTEA,
    encoding VARCHAR(64),
    task_queue VARCHAR(255),
    search_attributes BYTEA,
    parent_namespace_id VARCHAR(255),
    parent_workflow_id VARCHAR(255),
    parent_run_id VARCHAR(255),
    completion_event_batch_id BIGINT,
    PRIMARY KEY (namespace_id, workflow_id, run_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS executions_start_time ON executions (namespace_id, start_time);
CREATE INDEX IF NOT EXISTS executions_workflow_id ON executions (namespace_id, workflow_id);
CREATE INDEX IF NOT EXISTS executions_status ON executions (namespace_id, workflow_status);

-- Create history tables
CREATE TABLE IF NOT EXISTS history_node (
    shard_id INT NOT NULL,
    tree_id VARCHAR(255) NOT NULL,
    branch_id VARCHAR(255) NOT NULL,
    node_id BIGINT NOT NULL,
    txn_id BIGINT NOT NULL,
    data BYTEA,
    data_encoding VARCHAR(16),
    PRIMARY KEY (shard_id, tree_id, branch_id, node_id, txn_id)
);

CREATE TABLE IF NOT EXISTS history_tree (
    shard_id INT NOT NULL,
    tree_id VARCHAR(255) NOT NULL,
    branch_id VARCHAR(255) NOT NULL,
    data BYTEA,
    data_encoding VARCHAR(16),
    PRIMARY KEY (shard_id, tree_id, branch_id)
);

-- Create task tables
CREATE TABLE IF NOT EXISTS tasks (
    namespace_id VARCHAR(255) NOT NULL,
    task_queue_name VARCHAR(255) NOT NULL,
    task_queue_type INT NOT NULL,
    type INT NOT NULL,
    task_id BIGINT NOT NULL,
    data BYTEA,
    data_encoding VARCHAR(16),
    PRIMARY KEY (namespace_id, task_queue_name, task_queue_type, type, task_id)
);

-- Create queue tables
CREATE TABLE IF NOT EXISTS queue (
    queue_type INT NOT NULL,
    message_id BIGINT NOT NULL,
    message_payload BYTEA,
    message_encoding VARCHAR(16),
    PRIMARY KEY (queue_type, message_id)
);

-- Create cluster_metadata table
CREATE TABLE IF NOT EXISTS cluster_metadata (
    metadata_partition INT NOT NULL,
    cluster_name VARCHAR(255) NOT NULL,
    data BYTEA,
    data_encoding VARCHAR(16),
    version BIGINT NOT NULL,
    PRIMARY KEY (metadata_partition, cluster_name)
);

-- Insert default cluster metadata
INSERT INTO cluster_metadata (metadata_partition, cluster_name, data, data_encoding, version)
VALUES (0, 'active', '\x', 'json', 1)
ON CONFLICT (metadata_partition, cluster_name) DO NOTHING;

-- Create default namespace
INSERT INTO namespaces (partition_id, id, name, notification_version, data, data_encoding, is_global)
VALUES (0, '32049b68-7872-4094-8973-6c5cd3a3b764', 'default', 1, '\x', 'json', false)
ON CONFLICT (partition_id, id) DO NOTHING;

-- Update namespace metadata
INSERT INTO namespace_metadata (partition_id, notification_version)
VALUES (0, 1)
ON CONFLICT (partition_id) DO UPDATE SET notification_version = 1;
