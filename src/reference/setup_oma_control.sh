#!/bin/bash

# Create config directory if it doesn't exist
mkdir -p ./config

# Create database and insert data
sqlite3 ./config/oma_control.db <<EOF
CREATE TABLE IF NOT EXISTS properties (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR REPLACE INTO properties (key, value) VALUES 
    ('JAVA_SOURCE_FOLDER', '/Users/changik/workspace/src-orcl/src'),
    ('SOURCE_DBMS_TYPE', 'orcl'),
    ('TARGET_DBMS_TYPE', 'postgres');
EOF

echo "Database created successfully at ./config/oma_control.db"
