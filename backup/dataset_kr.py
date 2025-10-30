from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import csv
import os
import numpy as np
import logging
import mysql.connector
import configparser

logger = None


def write_log(msg):
    logger.info(msg)
    print(msg)


# 주식 리스트 가져오기
def get_stock_list():
    import function.static as static
    import function.common as common

    conn = mysql.connector.connect(**static.db_config_kr)
    stocks = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT CODE,NAME,MARKET from STOCK_LIST order by order_no")
        stocks = [x for x in cursor.fetchall()]
    except Exception as e:
        print(e)
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    return stocks


# 주식 리스트 삽입
def insert_stock_list():
    import function.static as static
    import function.common as common
    import FinanceDataReader as fdr

    conn = mysql.connector.connect(**static.db_config_kr)
    index = 0
    try:
        cursor = conn.cursor()
        for index, row in fdr.StockListing("KRX").iterrows():
            cursor.execute(
                f"""
                INSERT INTO STOCK_LIST (code, name, market, order_no, create_date, update_date)
                VALUES ('{row['Code']}', '{row['Name']}', 'KRX', {index}, now(), now())
                ON DUPLICATE KEY UPDATE 
                    name = VALUES(name), 
                    market = VALUES(market), 
                    order_no = VALUES(order_no), 
                    update_date = now()
            """
            )
            index += 1
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

    write_log("list was created")


def get_calc_stock(stock_data):
    data = []
    stock_data["5MvAvg"] = stock_data["Close"].rolling(window=5).mean()
    stock_data["20MvAvg"] = stock_data["Close"].rolling(window=20).mean()
    stock_data["50MvAvg"] = stock_data["Close"].rolling(window=50).mean()
    stock_data["60MvAvg"] = stock_data["Close"].rolling(window=60).mean()
    stock_data["120MvAvg"] = stock_data["Close"].rolling(window=120).mean()
    stock_data["240MvAvg"] = stock_data["Close"].rolling(window=240).mean()

    stock_data["60Std"] = stock_data["Close"].rolling(window=60).std()

    stock_data["UpperBand60"] = stock_data["60MvAvg"] + (stock_data["60Std"] * 1)
    stock_data["LowerBand60"] = stock_data["60MvAvg"] - (stock_data["60Std"] * 1)

    stock_data["UpperBand60_3"] = stock_data["60MvAvg"] + (stock_data["60Std"] * 3)
    stock_data["LowerBand60_3"] = stock_data["60MvAvg"] - (stock_data["60Std"] * 3)

    stock_data["TransAmnt"] = stock_data["Close"] * stock_data["Volume"]

    for index, row in stock_data.iterrows():
        # 한 줄로 검사
        if any(
            np.isnan(row[col])
            for col in [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "5MvAvg",
                "20MvAvg",
                "50MvAvg",
                "60MvAvg",
                "120MvAvg",
                "240MvAvg",
                "UpperBand60",
                "LowerBand60",
                "UpperBand60_3",
                "LowerBand60_3",
                "TransAmnt",
            ]
        ):
            continue

        data.append(
            [
                index.strftime("%Y-%m-%d"),  # 0
                row["Open"],  # 1
                row["High"],  # 2
                row["Low"],  # 3
                row["Close"],  # 4
                row["Volume"],  # 5
                row["TransAmnt"],  # 6
                row["5MvAvg"],  # 7
                row["20MvAvg"],  # 8
                row["50MvAvg"],  # 9
                row["60MvAvg"],  # 10
                row["120MvAvg"],  # 11
                row["240MvAvg"],  # 12
                row["UpperBand60"],  # 13
                row["LowerBand60"],  # 14
                row["UpperBand60_3"],  # 15
                row["LowerBand60_3"],  # 16
            ]
        )
    return data


def insert_stock(tbl_name, code, data):
    import function.static as static

    if len(data) > 0:
        conn = mysql.connector.connect(**static.db_config_kr)
        query = ""
        try:
            cursor = conn.cursor()
            query = f"""INSERT INTO {tbl_name} (
                code, date, Open, High, Low, Close, Volume, TransAmnt, 
                5MvAvg, 20MvAvg, 50MvAvg, 60MvAvg, 120MvAvg, 240MvAvg, 
                UpperBand60_1, LowerBand60_1, 
                create_date, update_date, 
                LowerBand60_3) 
                VALUES """
            comma = ""
            for row in data:
                query += comma
                query += f""" (
                    '{code}', '{row[0]}', '{row[1]}', '{row[2]}', '{row[3]}', '{row[4]}', '{row[5]}', '{row[6]}', 
                    '{row[7]}', '{row[8]}', '{row[9]}', '{row[10]}', '{row[11]}', '{row[12]}' ,
                    '{row[13]}','{row[14]}',
                    now(), now(),
                    '{row[16]}') """
                comma = ","
            query += " ON DUPLICATE KEY UPDATE "
            query += f""" 
                        Open = VALUES(Open), 
                        High = VALUES(High), 
                        Low = VALUES(Low), 
                        Close = VALUES(Close), 
                        Volume = VALUES(Volume), 
                        TransAmnt = VALUES(TransAmnt), 
                        5MvAvg = VALUES(5MvAvg), 
                        20MvAvg = VALUES(20MvAvg), 
                        50MvAvg = VALUES(50MvAvg), 
                        60MvAvg = VALUES(60MvAvg), 
                        120MvAvg = VALUES(120MvAvg), 
                        240MvAvg = VALUES(240MvAvg), 
                        UpperBand60_1 = VALUES(UpperBand60_1), 
                        LowerBand60_1 = VALUES(LowerBand60_1), 
                        update_date = now(),  
                        LowerBand60_3 = VALUES(LowerBand60_3)"""
            cursor.execute(query)
            conn.commit()
            write_log(f"({code}) was created!")
        except Exception as e:
            conn.rollback()
            print(f"Error e: {e}")
            raise e
        finally:
            cursor.close()
            conn.close()


# 프로세스 처리
def process_stock_data(stock):
    import function.static as static
    import function.common as common
    import FinanceDataReader as fdr

    # print(f"Processing stock: {stock}")
    code, name, market = stock

    stock_data = fdr.DataReader(code, static.start_date, static.end_date)
    data = get_calc_stock(stock_data)
    insert_stock("STOCK_DATA", code, data)

    # 주봉 데이터 생성
    weekly_data = stock_data.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )
    data = get_calc_stock(weekly_data)
    insert_stock("STOCK_DATA_WEEK", code, data)


def main():
    import function.static as static
    import function.common as common

    global logger
    # logger 불러오기
    logger = common.setup_custom_logger(static.dir, "create_stock_dataset")
    insert_stock_list()

    stocks = get_stock_list()

    # 스레드 풀 생성
    with ThreadPoolExecutor(max_workers=5) as executor:
        # 각 주식에 대해 병렬로 작업 실행
        executor.map(process_stock_data, stocks)


if __name__ == "__main__":
    main()
