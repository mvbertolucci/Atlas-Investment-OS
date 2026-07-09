-- Atlas Investment OS initial schema.
-- SQLite will be used as the source of truth in the next sprint.

CREATE TABLE IF NOT EXISTS companies (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    exchange TEXT,
    country TEXT,
    currency TEXT,
    sector TEXT,
    industry TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,
    investment_score REAL,
    business_score REAL,
    valuation_score REAL,
    financial_score REAL,
    timing_score REAL,
    confidence_score REAL,
    recommendation TEXT
);
