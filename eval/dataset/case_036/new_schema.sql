CREATE TABLE transactions (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    is_active  VARCHAR(100),
    member_id  VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);