-- Global Restaurant Explorer: MySQL 8.0 Operational, Silver, and Gold Spatial Schema
-- Engine: InnoDB | Charset: utf8mb4 | Collation: utf8mb4_0900_ai_ci

CREATE DATABASE IF NOT EXISTS global_restaurant_explorer
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE global_restaurant_explorer;

CREATE TABLE IF NOT EXISTS source_metadata (
    source_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_name VARCHAR(64) NOT NULL,
    license VARCHAR(64) NOT NULL,
    url VARCHAR(255) NULL,
    PRIMARY KEY (source_id),
    UNIQUE KEY uq_source_metadata_name (source_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(36) NOT NULL,
    dag_id VARCHAR(100) NOT NULL,
    source_id INT UNSIGNED NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME NULL,
    status VARCHAR(32) NOT NULL,
    rows_read INT UNSIGNED NOT NULL DEFAULT 0,
    rows_inserted INT UNSIGNED NOT NULL DEFAULT 0,
    rows_updated INT UNSIGNED NOT NULL DEFAULT 0,
    rows_unchanged INT UNSIGNED NOT NULL DEFAULT 0,
    rows_quarantined INT UNSIGNED NOT NULL DEFAULT 0,
    rows_warned INT UNSIGNED NOT NULL DEFAULT 0,
    quarantine_rate DECIMAL(6, 4) NOT NULL DEFAULT 0.0000,
    PRIMARY KEY (run_id),
    KEY idx_pipeline_runs_source_started (source_id, started_at),
    CONSTRAINT fk_pipeline_runs_source_id
        FOREIGN KEY (source_id) REFERENCES source_metadata (source_id),
    CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('running', 'success', 'skipped_unchanged', 'quality_gate_failed', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id VARCHAR(36) NOT NULL,
    source_id INT UNSIGNED NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    source_version VARCHAR(100) NULL,
    source_updated_at DATETIME NULL,
    file_checksum CHAR(64) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    row_count INT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    ingested_at DATETIME NOT NULL,
    PRIMARY KEY (batch_id),
    KEY idx_ingestion_batches_source_checksum (source_id, file_checksum),
    KEY idx_ingestion_batches_run_id (run_id),
    CONSTRAINT fk_ingestion_batches_source_id
        FOREIGN KEY (source_id) REFERENCES source_metadata (source_id),
    CONSTRAINT fk_ingestion_batches_run_id
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(36) NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    source_record_id VARCHAR(64) NULL,
    rule_name VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    raw_payload JSON NOT NULL,
    detected_at DATETIME NOT NULL,
    PRIMARY KEY (issue_id),
    KEY idx_data_quality_issues_run_rule (run_id, rule_name),
    KEY idx_data_quality_issues_batch_severity (batch_id, severity),
    CONSTRAINT fk_data_quality_issues_batch_id
        FOREIGN KEY (batch_id) REFERENCES ingestion_batches (batch_id),
    CONSTRAINT fk_data_quality_issues_run_id
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id),
    CONSTRAINT chk_data_quality_issues_severity
        CHECK (severity IN ('reject', 'warning'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS countries (
    country_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_country_code INT UNSIGNED NOT NULL,
    country_name VARCHAR(100) NOT NULL,
    iso_code CHAR(2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    PRIMARY KEY (country_id),
    UNIQUE KEY uq_countries_source_code (source_country_code),
    UNIQUE KEY uq_countries_name (country_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS cities (
    city_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    country_id INT UNSIGNED NOT NULL,
    city_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (city_id),
    UNIQUE KEY uq_cities_country_city (country_id, city_name),
    KEY idx_cities_name (city_name),
    CONSTRAINT fk_cities_country_id
        FOREIGN KEY (country_id) REFERENCES countries (country_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS locations (
    location_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    city_id INT UNSIGNED NOT NULL,
    locality VARCHAR(150) NOT NULL,
    PRIMARY KEY (location_id),
    UNIQUE KEY uq_locations_city_locality (city_id, locality),
    CONSTRAINT fk_locations_city_id
        FOREIGN KEY (city_id) REFERENCES cities (city_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS cuisines (
    cuisine_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    cuisine_name VARCHAR(100) NOT NULL,
    cuisine_group VARCHAR(100) NOT NULL,
    PRIMARY KEY (cuisine_id),
    UNIQUE KEY uq_cuisines_name (cuisine_name),
    KEY idx_cuisines_group (cuisine_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_restaurant_id VARCHAR(64) NOT NULL,
    source_id INT UNSIGNED NOT NULL,
    batch_id VARCHAR(36) NOT NULL,
    last_seen_batch_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    location_id INT UNSIGNED NOT NULL,
    address VARCHAR(500) NULL,
    latitude DECIMAL(9, 6) NULL,
    longitude DECIMAL(9, 6) NULL,
    avg_cost_for_two DECIMAL(14, 2) NULL,
    currency_code CHAR(3) NOT NULL,
    avg_cost_for_two_usd DECIMAL(14, 2) NULL,
    fx_rate DECIMAL(14, 6) NULL,
    fx_rate_date DATE NULL,
    price_range TINYINT UNSIGNED NOT NULL,
    rating DECIMAL(3, 1) NULL,
    rating_color VARCHAR(32) NULL,
    rating_text VARCHAR(32) NULL,
    votes INT UNSIGNED NOT NULL DEFAULT 0,
    has_table_booking BOOLEAN NOT NULL DEFAULT FALSE,
    has_online_delivery BOOLEAN NOT NULL DEFAULT FALSE,
    is_delivering_now BOOLEAN NOT NULL DEFAULT FALSE,
    switch_to_order_menu BOOLEAN NOT NULL DEFAULT FALSE,
    match_group_id INT UNSIGNED NULL,
    record_hash CHAR(64) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (restaurant_id),
    UNIQUE KEY uq_restaurants_source_record (source_id, source_restaurant_id),
    KEY idx_restaurants_location_price_rating (location_id, price_range, rating),
    KEY idx_restaurants_rating_votes (rating, votes),
    KEY idx_restaurants_cost_usd (avg_cost_for_two_usd),
    KEY idx_restaurants_batch_id (batch_id),
    FULLTEXT KEY idx_restaurants_name_ft (name),
    CONSTRAINT fk_restaurants_source_id
        FOREIGN KEY (source_id) REFERENCES source_metadata (source_id),
    CONSTRAINT fk_restaurants_location_id
        FOREIGN KEY (location_id) REFERENCES locations (location_id),
    CONSTRAINT fk_restaurants_batch_id
        FOREIGN KEY (batch_id) REFERENCES ingestion_batches (batch_id),
    CONSTRAINT chk_restaurants_price_range
        CHECK (price_range BETWEEN 1 AND 4),
    CONSTRAINT chk_restaurants_rating_range
        CHECK (rating IS NULL OR (rating BETWEEN 0.0 AND 5.0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS restaurant_cuisines (
    restaurant_id INT UNSIGNED NOT NULL,
    cuisine_id INT UNSIGNED NOT NULL,
    PRIMARY KEY (restaurant_id, cuisine_id),
    KEY idx_restaurant_cuisines_cuisine_id (cuisine_id),
    CONSTRAINT fk_restaurant_cuisines_restaurant_id
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (restaurant_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_restaurant_cuisines_cuisine_id
        FOREIGN KEY (cuisine_id) REFERENCES cuisines (cuisine_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gold_map_points (
    restaurant_id INT UNSIGNED NOT NULL,
    source_id INT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    country_name VARCHAR(100) NOT NULL,
    city_name VARCHAR(100) NOT NULL,
    locality VARCHAR(150) NOT NULL,
    cuisines VARCHAR(500) NULL,
    price_range TINYINT UNSIGNED NOT NULL,
    rating DECIMAL(3, 1) NULL,
    votes INT UNSIGNED NOT NULL DEFAULT 0,
    avg_cost_for_two DECIMAL(14, 2) NULL,
    currency_code CHAR(3) NOT NULL,
    avg_cost_for_two_usd DECIMAL(14, 2) NULL,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    location POINT SRID 4326 NOT NULL,
    PRIMARY KEY (restaurant_id),
    KEY idx_gold_map_points_country_city (country_name, city_name),
    SPATIAL INDEX idx_gold_map_points_location (location),
    CONSTRAINT fk_gold_map_points_restaurant_id
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (restaurant_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO source_metadata (source_id, source_name, license, url)
VALUES
    (1, 'zomato', 'CC0 1.0', 'https://www.kaggle.com/datasets/shrutimehta/zomato-restaurants-data');

INSERT IGNORE INTO countries (source_country_code, country_name, iso_code, currency_code)
VALUES
    (1, 'India', 'IN', 'INR'),
    (14, 'Australia', 'AU', 'AUD'),
    (30, 'Brazil', 'BR', 'BRL'),
    (37, 'Canada', 'CA', 'CAD'),
    (94, 'Indonesia', 'ID', 'IDR'),
    (148, 'New Zealand', 'NZ', 'NZD'),
    (162, 'Philippines', 'PH', 'PHP'),
    (166, 'Qatar', 'QA', 'QAR'),
    (184, 'Singapore', 'SG', 'SGD'),
    (189, 'South Africa', 'ZA', 'ZAR'),
    (191, 'Sri Lanka', 'LK', 'LKR'),
    (208, 'Turkey', 'TR', 'TRY'),
    (214, 'UAE', 'AE', 'AED'),
    (215, 'United Kingdom', 'GB', 'GBP'),
    (216, 'United States', 'US', 'USD');
