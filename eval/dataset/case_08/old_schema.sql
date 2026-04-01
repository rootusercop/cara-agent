-- Old schema: single unified user_addresses table
CREATE TABLE user_addresses (
    id           VARCHAR PRIMARY KEY,
    user_id      VARCHAR NOT NULL,
    street       VARCHAR,
    city         VARCHAR,
    state        VARCHAR,
    zip          VARCHAR,
    country      VARCHAR,
    address_type VARCHAR
);
