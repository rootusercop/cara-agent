-- New schema: notifications table with nullable read_at column added
CREATE TABLE notifications (
    id      VARCHAR   PRIMARY KEY,
    user_id VARCHAR   NOT NULL,
    message TEXT      NOT NULL,
    sent_at TIMESTAMP,
    read_at TIMESTAMP
);
