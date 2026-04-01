CREATE TABLE analytics (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    amount      DECIMAL(10,2) NOT NULL,
    updated_at     VARCHAR(50) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);