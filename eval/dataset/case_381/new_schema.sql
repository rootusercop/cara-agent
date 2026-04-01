CREATE TABLE analytics (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    tier      VARCHAR(100) DEFAULT NULL
);