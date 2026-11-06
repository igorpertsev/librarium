-- Runs once, when the PostgreSQL volume is initialised.
-- A separate database for the automated tests; they never touch the main database.
CREATE DATABASE bookstore_test;
