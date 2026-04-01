-- Old schema: orders and products tables with integer price
CREATE TABLE orders (
    id          VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    product_id  VARCHAR NOT NULL,
    quantity    INT
);

CREATE TABLE products (
    id    VARCHAR PRIMARY KEY,
    name  VARCHAR,
    price INT
);
