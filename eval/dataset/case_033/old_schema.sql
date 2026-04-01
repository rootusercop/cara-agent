CREATE TABLE subscriptions (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    notes     VARCHAR(100),
    email       VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);