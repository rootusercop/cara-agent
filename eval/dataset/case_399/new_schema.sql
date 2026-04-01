CREATE TABLE subscriptions (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    name      VARCHAR(100) DEFAULT NULL
);