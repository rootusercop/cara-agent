CREATE TABLE transactions (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    tier      DECIMAL(15,4),
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);