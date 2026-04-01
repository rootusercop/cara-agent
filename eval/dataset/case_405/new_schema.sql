CREATE TABLE warehouses (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    deleted_at      VARCHAR(100) DEFAULT NULL
);