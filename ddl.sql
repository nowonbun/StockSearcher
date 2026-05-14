-- Schema definition for StockSearcher datasets (KR & JP).
-- Separate tables are provided for Korean and Japanese universes
-- to reflect the distinct dataset loaders in dataset_kr.py and dataset_jp.py.

-- -----------------------------
-- KRX stock master & price tables
-- -----------------------------
CREATE TABLE IF NOT EXISTS STOCK_LIST_KR (
    code        VARCHAR(12)  NOT NULL,
    name        VARCHAR(200) NOT NULL,
    market      VARCHAR(50)  NOT NULL,
    order_no    INT          DEFAULT NULL,
    create_date DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_date DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code),
    KEY idx_stock_list_kr_order (order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS STOCK_DATA_KR (
    code          VARCHAR(12)  NOT NULL,
    date          DATE         NOT NULL,
    Open          BIGINT       DEFAULT NULL,
    High          BIGINT       DEFAULT NULL,
    Low           BIGINT       DEFAULT NULL,
    Close         BIGINT       DEFAULT NULL,
    Volume        BIGINT       DEFAULT NULL,
    TransAmnt     BIGINT       DEFAULT NULL,
    5MvAvg        BIGINT       DEFAULT NULL,
    20MvAvg       BIGINT       DEFAULT NULL,
    50MvAvg       BIGINT       DEFAULT NULL,
    60MvAvg       BIGINT       DEFAULT NULL,
    120MvAvg      BIGINT       DEFAULT NULL,
    240MvAvg      BIGINT       DEFAULT NULL,
    UpperBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_3 BIGINT       DEFAULT NULL,
    DI_plus       BIGINT       DEFAULT NULL,
    DI_minus      BIGINT       DEFAULT NULL,
    ADX           BIGINT       DEFAULT NULL,
    create_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, date),
    KEY idx_stock_data_kr_date (date),
    CONSTRAINT fk_stock_data_kr_list FOREIGN KEY (code) REFERENCES STOCK_LIST_KR (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS STOCK_DATA_WEEK_KR (
    code          VARCHAR(12)  NOT NULL,
    date          DATE         NOT NULL,
    Open          BIGINT       DEFAULT NULL,
    High          BIGINT       DEFAULT NULL,
    Low           BIGINT       DEFAULT NULL,
    Close         BIGINT       DEFAULT NULL,
    Volume        BIGINT       DEFAULT NULL,
    TransAmnt     BIGINT       DEFAULT NULL,
    5MvAvg        BIGINT       DEFAULT NULL,
    20MvAvg       BIGINT       DEFAULT NULL,
    50MvAvg       BIGINT       DEFAULT NULL,
    60MvAvg       BIGINT       DEFAULT NULL,
    UpperBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_3 BIGINT       DEFAULT NULL,
    DI_plus       BIGINT       DEFAULT NULL,
    DI_minus      BIGINT       DEFAULT NULL,
    ADX           BIGINT       DEFAULT NULL,
    create_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, date),
    KEY idx_stock_data_week_kr_date (date),
    CONSTRAINT fk_stock_data_week_kr_list FOREIGN KEY (code) REFERENCES STOCK_LIST_KR (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS STOCK_PREDICT_KR;
CREATE TABLE IF NOT EXISTS STOCK_PREDICT_KR (
    data_cutoff   DATE         NOT NULL,
    code          VARCHAR(12)  NOT NULL,
    probability   DECIMAL(10,6) NOT NULL,
    run_name      VARCHAR(200) NOT NULL,
    seq_len       INT          NOT NULL,
    horizon_days  INT          NOT NULL,
    rise_threshold DECIMAL(6,4) NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (data_cutoff, code),
    CONSTRAINT fk_stock_predict_kr_list FOREIGN KEY (code) REFERENCES STOCK_LIST_KR (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS STOCK_PREDICT_WEEK_KR (
    data_cutoff   DATE         NOT NULL,
    code          VARCHAR(12)  NOT NULL,
    probability   DECIMAL(10,6) NOT NULL,
    run_name      VARCHAR(200) NOT NULL,
    seq_len       INT          NOT NULL,
    horizon_days  INT          NOT NULL,
    rise_threshold DECIMAL(6,4) NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (data_cutoff, code),
    CONSTRAINT fk_stock_predict_week_kr_list FOREIGN KEY (code) REFERENCES STOCK_LIST_KR (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- -----------------------------
-- JPX stock master & price tables
-- -----------------------------
CREATE TABLE IF NOT EXISTS STOCK_LIST_JP (
    code            VARCHAR(12)  NOT NULL,
    name            VARCHAR(200) NOT NULL,
    stocktype       VARCHAR(200) DEFAULT NULL,
    industry33code  VARCHAR(50)  DEFAULT NULL,
    industry33type  VARCHAR(200) DEFAULT NULL,
    industry17code  VARCHAR(50)  DEFAULT NULL,
    industry17type  VARCHAR(200) DEFAULT NULL,
    scalecode       VARCHAR(50)  DEFAULT NULL,
    scaletype       VARCHAR(200) DEFAULT NULL,
    create_date     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_date     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code),
    KEY idx_stock_list_jp_stocktype (stocktype)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS STOCK_DATA_JP (
    code          VARCHAR(12)  NOT NULL,
    date          DATE         NOT NULL,
    Open          BIGINT       DEFAULT NULL,
    High          BIGINT       DEFAULT NULL,
    Low           BIGINT       DEFAULT NULL,
    Close         BIGINT       DEFAULT NULL,
    Volume        BIGINT       DEFAULT NULL,
    TransAmnt     BIGINT       DEFAULT NULL,
    5MvAvg        BIGINT       DEFAULT NULL,
    20MvAvg       BIGINT       DEFAULT NULL,
    50MvAvg       BIGINT       DEFAULT NULL,
    60MvAvg       BIGINT       DEFAULT NULL,
    120MvAvg      BIGINT       DEFAULT NULL,
    240MvAvg      BIGINT       DEFAULT NULL,
    UpperBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_3 BIGINT       DEFAULT NULL,
    DI_plus       BIGINT       DEFAULT NULL,
    DI_minus      BIGINT       DEFAULT NULL,
    ADX           BIGINT       DEFAULT NULL,
    create_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, date),
    KEY idx_stock_data_jp_date (date),
    CONSTRAINT fk_stock_data_jp_list FOREIGN KEY (code) REFERENCES STOCK_LIST_JP (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS STOCK_DATA_WEEK_JP (
    code          VARCHAR(12)  NOT NULL,
    date          DATE         NOT NULL,
    Open          BIGINT       DEFAULT NULL,
    High          BIGINT       DEFAULT NULL,
    Low           BIGINT       DEFAULT NULL,
    Close         BIGINT       DEFAULT NULL,
    Volume        BIGINT       DEFAULT NULL,
    TransAmnt     BIGINT       DEFAULT NULL,
    5MvAvg        BIGINT       DEFAULT NULL,
    20MvAvg       BIGINT       DEFAULT NULL,
    50MvAvg       BIGINT       DEFAULT NULL,
    60MvAvg       BIGINT       DEFAULT NULL,
    UpperBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_1 BIGINT       DEFAULT NULL,
    LowerBand60_3 BIGINT       DEFAULT NULL,
    DI_plus       BIGINT       DEFAULT NULL,
    DI_minus      BIGINT       DEFAULT NULL,
    ADX           BIGINT       DEFAULT NULL,
    create_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_date   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (code, date),
    KEY idx_stock_data_week_jp_date (date),
    CONSTRAINT fk_stock_data_week_jp_list FOREIGN KEY (code) REFERENCES STOCK_LIST_JP (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS STOCK_PREDICT_JP;
CREATE TABLE IF NOT EXISTS STOCK_PREDICT_JP (
    data_cutoff   DATE         NOT NULL,
    code          VARCHAR(12)  NOT NULL,
    probability   DECIMAL(10,6) NOT NULL,
    run_name      VARCHAR(200) NOT NULL,
    seq_len       INT          NOT NULL,
    horizon_days  INT          NOT NULL,
    rise_threshold DECIMAL(6,4) NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (data_cutoff, code),
    CONSTRAINT fk_stock_predict_jp_list FOREIGN KEY (code) REFERENCES STOCK_LIST_JP (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS STOCK_PREDICT_WEEK_JP (
    data_cutoff   DATE         NOT NULL,
    code          VARCHAR(12)  NOT NULL,
    probability   DECIMAL(10,6) NOT NULL,
    run_name      VARCHAR(200) NOT NULL,
    seq_len       INT          NOT NULL,
    horizon_days  INT          NOT NULL,
    rise_threshold DECIMAL(6,4) NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (data_cutoff, code),
    CONSTRAINT fk_stock_predict_week_jp_list FOREIGN KEY (code) REFERENCES STOCK_LIST_JP (code)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
