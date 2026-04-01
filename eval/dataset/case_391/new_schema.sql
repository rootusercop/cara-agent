CREATE TABLE dashboards (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    is_active      VARCHAR(100) DEFAULT NULL
);