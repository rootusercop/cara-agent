CREATE TABLE webhooks (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    quantity      VARCHAR(100) DEFAULT NULL
);