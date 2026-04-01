CREATE TABLE orders_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE orders_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES orders_core(id),
    description TEXT,
    metadata    JSONB
);