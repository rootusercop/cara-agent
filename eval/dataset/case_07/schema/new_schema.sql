-- New schema: profiles table with display_name replacing full_name
CREATE TABLE profiles (
    profile_id   VARCHAR PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL,
    email        VARCHAR(255)
);
