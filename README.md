# README.md

## Environment Setup

Make sure you have the following versions installed:

- **Python Version:** 3.10.10
- https://www.python.org/downloads/release/python-31010/

## Package Installation

```bash
pip install pandas==2.1.4
pip install numpy==1.26.3
pip install requests==2.31.0
pip install finance-datareader==0.9.66
pip install beautifulsoup4==4.12.2
pip install plotly==5.18.0
pip install logging==0.4.9.6
pip install scikit-learn==1.3.2
pip install tensorflow==2.10.0

pip install mysqlclient=2.2.1
pip install mysql-connector-python
```

## Database Operations
```sql
CREATE DATABASE STOCK_DATA;
USE STOCK_DATA;

CREATE TABLE STOCK_LIST_KR (
    code varchar(10),
    name varchar(200),
    market varchar(200),
    is_used bit,
    order_no int,
    create_date datetime,
    update_date datetime,
    
    PRIMARY KEY (code)
);

CREATE TABLE STOCK_DATA_KR (
    code varchar(10),
    date date,
    Open DECIMAL(16,2), 
    High DECIMAL(16,2),
    Low DECIMAL(16,2),
    Close DECIMAL(16,2),
    `Change` DECIMAL(16,2),
    Volume DECIMAL(16,2),
    5MvAvg DECIMAL(16,2),
    20MvAvg DECIMAL(16,2),
    60MvAvg DECIMAL(16,2),
    112MvAvg DECIMAL(16,2),
    224MvAvg DECIMAL(16,2),
    UpperBand DECIMAL(16,2),
    LowerBand DECIMAL(16,2),
    20VolAvg DECIMAL(16,2),
    60VolAvg DECIMAL(16,2),
    TranAmnt DECIMAL(16,2),
    is_used bit,
    create_date datetime,
    update_date datetime,
    
    PRIMARY KEY (code, date),
    FOREIGN KEY (code) REFERENCES STOCK_LIST_KR(code)
);
```