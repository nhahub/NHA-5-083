-- Global Restaurant Explorer: development reset script
-- Drops Gold views, Gold spatial tables, Silver tables, and operational tables

USE global_restaurant_explorer;

DROP VIEW IF EXISTS gold_geographic_coverage;
DROP VIEW IF EXISTS gold_rating_distribution;
DROP VIEW IF EXISTS gold_locality_cost;
DROP VIEW IF EXISTS gold_city_cuisine_stats;
DROP VIEW IF EXISTS gold_restaurant_search;

DROP TABLE IF EXISTS gold_map_points;
DROP TABLE IF EXISTS restaurant_cuisines;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS cuisines;
DROP TABLE IF EXISTS locations;
DROP TABLE IF EXISTS cities;
DROP TABLE IF EXISTS countries;
DROP TABLE IF EXISTS data_quality_issues;
DROP TABLE IF EXISTS ingestion_batches;
DROP TABLE IF EXISTS pipeline_runs;
DROP TABLE IF EXISTS source_metadata;
