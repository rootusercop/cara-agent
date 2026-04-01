CREATE TABLE policies (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    is_verified      VARCHAR(100) DEFAULT NULL
);