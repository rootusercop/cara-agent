CREATE TABLE audit_logs (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    description      VARCHAR(100) DEFAULT NULL
);