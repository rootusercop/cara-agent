CREATE TABLE warehouses (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id  VARCHAR(100),
    is_verified  VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);