-- Old schema: profiles table with full_name column
CREATE TABLE profiles (
    profile_id VARCHAR PRIMARY KEY,
    full_name  VARCHAR(255) NOT NULL,
    email      VARCHAR(255)
);
