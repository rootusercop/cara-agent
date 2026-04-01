CREATE TABLE dashboards_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE dashboards_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES dashboards_core(id),
    description TEXT,
    metadata    JSONB
);