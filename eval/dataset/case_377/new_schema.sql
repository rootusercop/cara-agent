CREATE TABLE transactions (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    customer_id      VARCHAR(100) DEFAULT NULL
);