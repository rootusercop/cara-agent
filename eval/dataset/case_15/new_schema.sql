-- New schema: transactions table with fee renamed to processing_fee (BIGINT)
CREATE TABLE transactions (
    id             VARCHAR PRIMARY KEY,
    sender_id      VARCHAR NOT NULL,
    receiver_id    VARCHAR NOT NULL,
    amount         INT     NOT NULL,
    processing_fee BIGINT
);
