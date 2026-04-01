CREATE TABLE inventory_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE inventory_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES inventory_core(id),
    description TEXT,
    metadata    JSONB
);