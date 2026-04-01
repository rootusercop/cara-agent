-- Old schema: transactions table with fee column (INT)
CREATE TABLE transactions (
    id          VARCHAR PRIMARY KEY,
    sender_id   VARCHAR NOT NULL,
    receiver_id VARCHAR NOT NULL,
    amount      INT     NOT NULL,
    fee         INT
);
