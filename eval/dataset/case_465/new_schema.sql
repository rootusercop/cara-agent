CREATE TABLE warehouses (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    limit      VARCHAR(100) DEFAULT NULL
);