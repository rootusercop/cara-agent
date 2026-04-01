-- New schema: products.price changes to DECIMAL, orders gains total_price DECIMAL column
CREATE TABLE orders (
    id          VARCHAR        PRIMARY KEY,
    customer_id VARCHAR        NOT NULL,
    product_id  VARCHAR        NOT NULL,
    quantity    INT,
    total_price DECIMAL(10, 2)
);

CREATE TABLE products (
    id    VARCHAR        PRIMARY KEY,
    name  VARCHAR,
    price DECIMAL(10, 2)
);
