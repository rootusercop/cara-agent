CREATE TABLE payments (
    payment_id VARCHAR(36) NOT NULL PRIMARY KEY,
    amount BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    user_id VARCHAR(36) NOT NULL
);
