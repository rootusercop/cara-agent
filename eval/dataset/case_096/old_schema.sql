CREATE TABLE accounts (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    deleted_at     VARCHAR(100),
    email       VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);