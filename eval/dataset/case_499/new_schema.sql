CREATE TABLE warehouses_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE warehouses_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES warehouses_core(id),
    description TEXT,
    metadata    JSONB
);