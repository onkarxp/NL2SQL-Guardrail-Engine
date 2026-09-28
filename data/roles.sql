CREATE ROLE safequery_reader LOGIN PASSWORD 'reader_dev';
GRANT CONNECT ON DATABASE safequery_db TO safequery_reader;
GRANT USAGE ON SCHEMA public TO safequery_reader;
GRANT SELECT ON regions, customers, products, orders, order_items TO safequery_reader;
ALTER ROLE safequery_reader SET default_transaction_read_only = on;
ALTER ROLE safequery_reader SET statement_timeout = '5s';