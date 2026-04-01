CREATE TABLE tickets (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    member_id     VARCHAR(255),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);