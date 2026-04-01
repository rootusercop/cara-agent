-- Old schema: entitlements table without account_type column
CREATE TABLE entitlements (
    id               VARCHAR PRIMARY KEY,
    user_id          VARCHAR NOT NULL,
    entitlement_type VARCHAR NOT NULL,
    value            TEXT
);
