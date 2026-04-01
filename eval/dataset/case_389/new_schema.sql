CREATE TABLE promotions (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    expires_at      VARCHAR(100) DEFAULT NULL
);