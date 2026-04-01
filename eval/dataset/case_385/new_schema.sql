CREATE TABLE users (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    email      VARCHAR(100) DEFAULT NULL
);