CREATE TABLE shipments (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    rank      VARCHAR(100) DEFAULT NULL
);