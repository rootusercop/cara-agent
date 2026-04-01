-- New schema: user_addresses split into billing_addresses and shipping_addresses
CREATE TABLE billing_addresses (
    id      VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    street  VARCHAR,
    city    VARCHAR,
    state   VARCHAR,
    zip     VARCHAR,
    country VARCHAR
);

CREATE TABLE shipping_addresses (
    id      VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    street  VARCHAR,
    city    VARCHAR,
    state   VARCHAR,
    zip     VARCHAR,
    country VARCHAR
);
