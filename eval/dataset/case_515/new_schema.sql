CREATE TABLE tokens_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE tokens_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES tokens_core(id),
    description TEXT,
    metadata    JSONB
);