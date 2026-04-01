CREATE TABLE promotions_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE promotions_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES promotions_core(id),
    description TEXT,
    metadata    JSONB
);