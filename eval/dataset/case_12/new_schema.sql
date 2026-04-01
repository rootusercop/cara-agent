-- New schema: entitlements table with account_type added (NOT NULL with DEFAULT)
CREATE TABLE entitlements (
    id               VARCHAR NOT NULL PRIMARY KEY,
    user_id          VARCHAR NOT NULL,
    entitlement_type VARCHAR NOT NULL,
    value            TEXT,
    account_type     VARCHAR NOT NULL DEFAULT 'STANDARD'
);
