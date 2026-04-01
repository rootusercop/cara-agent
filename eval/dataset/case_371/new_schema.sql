CREATE TABLE profiles (
    id           VARCHAR(36) NOT NULL PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL,
    is_deleted      VARCHAR(100) DEFAULT NULL
);