CREATE TABLE memberships (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    notes     VARCHAR(255),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);