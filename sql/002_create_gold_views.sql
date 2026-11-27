-- Global Restaurant Explorer: Gold Analytical and Serving Views
-- Keep semicolons out of comments and string literals for simple statement splitters

USE global_restaurant_explorer;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW gold_restaurant_search AS
SELECT
    r.restaurant_id,
    r.source_restaurant_id,
    r.source_id,
    sm.source_name,
    sm.license AS source_license,
    r.name,
    co.country_id,
    co.country_name,
    co.iso_code,
    ci.city_id,
    ci.city_name,
    l.location_id,
    l.locality,
    r.address,
    r.latitude,
    r.longitude,
    GROUP_CONCAT(DISTINCT c.cuisine_name ORDER BY c.cuisine_name SEPARATOR ', ') AS cuisines,
    GROUP_CONCAT(DISTINCT c.cuisine_group ORDER BY c.cuisine_group SEPARATOR ', ') AS cuisine_groups,
    r.avg_cost_for_two,
    r.currency_code,
    r.avg_cost_for_two_usd,
    r.fx_rate,
    r.fx_rate_date,
    r.price_range,
    r.rating,
    r.rating_color,
    r.rating_text,
    r.votes,
    r.has_table_booking,
    r.has_online_delivery,
    r.is_delivering_now,
    r.updated_at
FROM restaurants AS r
JOIN source_metadata AS sm ON sm.source_id = r.source_id
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
LEFT JOIN restaurant_cuisines AS rc ON rc.restaurant_id = r.restaurant_id
LEFT JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
GROUP BY
    r.restaurant_id,
    r.source_restaurant_id,
    r.source_id,
    sm.source_name,
    sm.license,
    r.name,
    co.country_id,
    co.country_name,
    co.iso_code,
    ci.city_id,
    ci.city_name,
    l.location_id,
    l.locality,
    r.address,
    r.latitude,
    r.longitude,
    r.avg_cost_for_two,
    r.currency_code,
    r.avg_cost_for_two_usd,
    r.fx_rate,
    r.fx_rate_date,
    r.price_range,
    r.rating,
    r.rating_color,
    r.rating_text,
    r.votes,
    r.has_table_booking,
    r.has_online_delivery,
    r.is_delivering_now,
    r.updated_at;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW gold_city_cuisine_stats AS
SELECT
    co.country_name,
    ci.city_id,
    ci.city_name,
    c.cuisine_id,
    c.cuisine_name,
    c.cuisine_group,
    COUNT(DISTINCT r.restaurant_id) AS restaurant_count,
    ROUND(AVG(r.rating), 2) AS avg_rating,
    ROUND(AVG(r.avg_cost_for_two_usd), 2) AS avg_cost_usd
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
JOIN restaurant_cuisines AS rc ON rc.restaurant_id = r.restaurant_id
JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
GROUP BY
    co.country_name,
    ci.city_id,
    ci.city_name,
    c.cuisine_id,
    c.cuisine_name,
    c.cuisine_group;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW gold_locality_cost AS
SELECT
    co.country_name,
    ci.city_name,
    l.location_id,
    l.locality,
    COUNT(r.restaurant_id) AS restaurant_count,
    ROUND(AVG(r.avg_cost_for_two_usd), 2) AS avg_cost_usd,
    ROUND(MIN(r.avg_cost_for_two_usd), 2) AS min_cost_usd,
    ROUND(MAX(r.avg_cost_for_two_usd), 2) AS max_cost_usd,
    ROUND(AVG(r.rating), 2) AS avg_rating
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
GROUP BY
    co.country_name,
    ci.city_name,
    l.location_id,
    l.locality;

CREATE OR REPLACE SQL SECURITY INVOKER VIEW gold_rating_distribution AS
SELECT
    COALESCE(r.rating_text, 'Unrated') AS rating_label,
    COUNT(r.restaurant_id) AS restaurant_count,
    ROUND(AVG(r.rating), 2) AS avg_rating,
    SUM(r.votes) AS total_votes
FROM restaurants AS r
GROUP BY COALESCE(r.rating_text, 'Unrated');

CREATE OR REPLACE SQL SECURITY INVOKER VIEW gold_geographic_coverage AS
SELECT
    co.country_name,
    ci.city_name,
    COUNT(r.restaurant_id) AS total_restaurants,
    SUM(CASE WHEN r.latitude IS NOT NULL AND r.longitude IS NOT NULL THEN 1 ELSE 0 END) AS geolocated_restaurants,
    SUM(CASE WHEN r.latitude IS NULL OR r.longitude IS NULL THEN 1 ELSE 0 END) AS missing_coordinate_restaurants,
    SUM(CASE WHEN r.rating IS NOT NULL THEN 1 ELSE 0 END) AS rated_restaurants
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
GROUP BY co.country_name, ci.city_name;
