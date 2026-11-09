"""SQLite schema for the AlphaForge market data lake.

Units (deliberately normalised, unlike raw Tushare):
  * price  : CNY
  * volume : shares
  * amount : CNY
  * market cap / money flow : CNY
  * fina_indicator : raw Tushare units (%, x)
"""

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS calendar (
    date       TEXT PRIMARY KEY,
    is_open    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS securities (
    code        TEXT PRIMARY KEY,
    ts_code     TEXT,
    name        TEXT,
    industry    TEXT,
    market      TEXT,
    exchange    TEXT,
    board       TEXT,
    list_date   TEXT,
    delist_date TEXT,
    is_st       INTEGER DEFAULT 0,
    list_status TEXT,
    total_mv    REAL,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS daily (
    code      TEXT NOT NULL,
    date      TEXT NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    pre_close REAL,
    volume    REAL,
    amount    REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily(date);

CREATE TABLE IF NOT EXISTS adj_factor (
    code       TEXT NOT NULL,
    date       TEXT NOT NULL,
    adj_factor REAL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS daily_basic (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    turnover_f  REAL,
    volume_ratio REAL,
    pe_ttm      REAL,
    pb          REAL,
    ps_ttm      REAL,
    dv_ttm      REAL,
    total_share REAL,
    float_share REAL,
    free_share  REAL,
    total_mv    REAL,
    circ_mv     REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_basic_date ON daily_basic(date);

CREATE TABLE IF NOT EXISTS moneyflow (
    code     TEXT NOT NULL,
    date     TEXT NOT NULL,
    buy_elg  REAL,
    sell_elg REAL,
    buy_lg   REAL,
    sell_lg  REAL,
    net_mf   REAL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS stk_limit (
    code      TEXT NOT NULL,
    date      TEXT NOT NULL,
    up_limit  REAL,
    down_limit REAL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS fina (
    code          TEXT NOT NULL,
    ann_date      TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    roe           REAL,
    netprofit_yoy REAL,
    or_yoy        REAL,
    debt_to_assets REAL,
    grossprofit_margin REAL,
    eps           REAL,
    bps           REAL,
    ocfps         REAL,
    q_roe         REAL,
    q_profit_yoy  REAL,
    q_sales_yoy   REAL,
    PRIMARY KEY (code, end_date, ann_date)
);
CREATE INDEX IF NOT EXISTS idx_fina_ann ON fina(code, ann_date);

CREATE TABLE IF NOT EXISTS index_member (
    index_code TEXT NOT NULL,
    date       TEXT NOT NULL,
    code       TEXT NOT NULL,
    weight     REAL,
    PRIMARY KEY (index_code, date, code)
);
CREATE INDEX IF NOT EXISTS idx_member_code ON index_member(code, date);

CREATE TABLE IF NOT EXISTS index_daily (
    code      TEXT NOT NULL,
    date      TEXT NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    pre_close REAL,
    pct_chg   REAL,
    volume    REAL,
    amount    REAL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS classify (
    code     TEXT NOT NULL,
    date     TEXT NOT NULL,
    industry TEXT,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS ingest_state (
    dataset   TEXT NOT NULL,
    code      TEXT NOT NULL,
    start_date TEXT,
    end_date   TEXT,
    rows       INTEGER,
    status     TEXT,
    updated_at TEXT,
    PRIMARY KEY (dataset, code)
);
"""

TABLES = [
    "meta", "calendar", "securities", "daily", "adj_factor", "daily_basic",
    "moneyflow", "stk_limit", "fina", "index_member", "index_daily",
    "classify", "ingest_state",
]
