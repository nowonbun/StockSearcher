from executor import create_table
from executor import init_code
from executor import insert_stockdata
from datetime import date
from datetime import datetime
from dateutil.relativedelta import relativedelta

from yahoo_finance_api2 import share
from yahoo_finance_api2.exceptions import YahooFinanceError
import joblib
from multiprocessing import Process, Lock
from dbConnector import db_connector

# 테이블 생성
# create_table()

# 코드 생성 및 초기화
# init_code()

# 주식 데이터 취득해서 insert 하기
insert_stockdata()


