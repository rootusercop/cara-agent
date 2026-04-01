CREATE TABLE coupons (
    id      VARCHAR(36) NOT NULL PRIMARY KEY,
    is_verified  VARCHAR(100),
    customer_id  VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);