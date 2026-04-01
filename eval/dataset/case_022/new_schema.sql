CREATE TABLE reports (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    customer_id  VARCHAR(100),
    is_deleted  VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);