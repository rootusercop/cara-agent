-- New schema: invoices table with DECIMAL monetary columns (widening type change)
CREATE TABLE invoices (
    id         VARCHAR        PRIMARY KEY,
    amount     DECIMAL(10, 2) NOT NULL,
    tax_amount DECIMAL(10, 2) NOT NULL
);
