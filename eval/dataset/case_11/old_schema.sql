-- Old schema: member_benefits table with investment_account_id column
CREATE TABLE member_benefits (
    id                    VARCHAR PRIMARY KEY,
    member_id             VARCHAR NOT NULL,
    benefit_type          VARCHAR NOT NULL,
    sofi_plus_tier        VARCHAR,
    investment_account_id VARCHAR
);
