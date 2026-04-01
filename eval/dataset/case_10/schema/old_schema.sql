-- Old schema: invoices table with integer monetary columns
CREATE TABLE invoices (
    id         VARCHAR PRIMARY KEY,
    amount     INT     NOT NULL,
    tax_amount INT     NOT NULL
);
