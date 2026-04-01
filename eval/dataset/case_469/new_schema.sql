CREATE TABLE invoices_core (
    id          VARCHAR(36) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE invoices_extended (
    id          VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES invoices_core(id),
    description TEXT,
    metadata    JSONB
);