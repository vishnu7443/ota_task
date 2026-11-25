-- Automatically executed once on fresh PostgreSQL volume initialization
-- Creates the separate test database required for automated pytest isolation.
SELECT 'CREATE DATABASE ota_test OWNER ' || current_user
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ota_test')\gexec
