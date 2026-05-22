-- Base métier MS-05 (séparée de la métadonnée Airflow)
CREATE USER app WITH PASSWORD 'app';
CREATE DATABASE belgian_companies OWNER app;
GRANT ALL PRIVILEGES ON DATABASE belgian_companies TO app;
