-- Old schema: notifications table without read_at column
CREATE TABLE notifications (
    id      VARCHAR   PRIMARY KEY,
    user_id VARCHAR   NOT NULL,
    message TEXT      NOT NULL,
    sent_at TIMESTAMP
);
