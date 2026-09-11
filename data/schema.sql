CREATE EXTENSION IF NOT EXISTS vector; 
-- This need to happen everytime the db is refreshed

CREATE TABLE regions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    region_id INT REFERENCES regions(id),
    signup_date DATE NOT NULL
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    region_id INT REFERENCES regions(id),
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    product_id INT REFERENCES products(id),
    quantity INT NOT NULL,
    amount NUMERIC(10,2) NOT NULL
);

-- Table to store the embeddings for each row in the database
CREATE TABLE schema_embeddings (
    table_name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    embedding vector(384)
);
-- Note on 384: this is the output size of the embedding model we're using (all-MiniLM-L6-v2) — it produces 384-dimensional vectors. 
-- If you ever swap embedding models later, this number needs to match whatever that model outputs.

