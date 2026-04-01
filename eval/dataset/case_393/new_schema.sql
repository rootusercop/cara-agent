CREATE TABLE accounts (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    user_id      VARCHAR(100) DEFAULT NULL
);