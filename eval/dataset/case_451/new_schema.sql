CREATE TABLE incidents (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    total      VARCHAR(100) DEFAULT NULL
);