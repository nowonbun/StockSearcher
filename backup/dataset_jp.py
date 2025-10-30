# stock_data.py에서 참조하는 함수
# 일본 주식 종목 리스트를 다운로드하는 함수
def get_stock_list_by_url(url):
    import pandas as pd
    from io import BytesIO
    import requests

    response = requests.get(url)

    if response.status_code == 200:
        excel_io = BytesIO(response.content)
        df = pd.read_excel(excel_io)
        return df

    else:
        print("파일을 다운로드하는 데 문제가 발생했습니다.")


# stock_data.py에서 참조하는 함수
# 일본 주식 종목 리스트를 저장하는 함수
def save_stock_list(db_config):
    import mysql.connector
    import entity.stock_list_node as stock_list_node
    import function.common as common

    # https://www.jpx.co.jp/markets/statistics-equities/misc/01.html
    df = get_stock_list_by_url(
        "https://www.jpx.co.jp//markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    )
    stocks = [
        stock_list_node.StockListNode(*row.tolist())
        for _, row in df.iterrows()
        if row.get("stocktype", "") not in ("ETF・ETN", "PRO Market")
    ]
    query = stock_list_node.generateSqlQuery(stocks)
    common.execute_query(db_config, query)
    print("stock_list 저장 완료")
    return stocks


# stock_data.py에서 참조하는 함수
# 주식 데이터를 필터링하는 함수
def filter_node(data2):
    data = {}
    data["timestamp"] = []
    data["open"] = []
    data["high"] = []
    data["low"] = []
    data["close"] = []
    data["volume"] = []

    for i in range(len(data2["timestamp"])):
        if (
            data2["open"][i] == None
            or data2["high"][i] == None
            or data2["low"][i] == None
            or data2["close"][i] == None
            or data2["volume"][i] == None
        ):
            continue
        data["timestamp"].append(data2["timestamp"][i])
        data["open"].append(data2["open"][i])
        data["high"].append(data2["high"][i])
        data["low"].append(data2["low"][i])
        data["close"].append(data2["close"][i])
        data["volume"].append(data2["volume"][i])
    return data


def get_stock_data(driver, stock, periodType, period, frequencyType, frequency):
    import function.stock_lib as stock_lib
    import requests
    import entity.stock_models as stock_models

    # stock = "9749.T"
    # share.PERIOD_TYPE_YEAR, share.PERIOD_TYPE_MONTH, share.PERIOD_TYPE_WEEK, share.PERIOD_TYPE_DAY
    # share.FREQUENCY_TYPE_MINUTE, share.FREQUENCY_TYPE_DAY, share.FREQUENCY_TYPE_MONTH, share.FREQUENCY_TYPE_YEAR
    for i in range(3):
        try:
            my_share = stock_lib.StockLib(stock)
            # print("GET - " + stock)
            ret = my_share.get_historical(
                driver, periodType, period, frequencyType, frequency
            )
            # print("OUT - " + stock)
            if ret is None:
                print(stock + " is None")
                return None
            return filter_node(ret)
        except requests.Timeout:
            print(stock + " timeout")
        except requests.RequestException as e:
            print("error - ", e)
        print(f"retry{i} - {stock}")


# stock_data.py에서 참조하는 함수
# 이동평균선을 계산하는 함수
def calculate_moving_average(data, idx, count):
    window_data = data[idx - (count - 1) : idx + 1]
    return sum(window_data) / count


# stock_data.py에서 참조하는 함수
# 볼린저 밴드를 계산하는 함수
def calculate_bollinger_bands(data, idx, window, k):
    import statistics

    window_data = data[idx - (window - 1) : idx + 1]
    mean = statistics.mean(window_data)
    std_dev = statistics.stdev(window_data)
    upper_band = mean + std_dev * k
    lower_band = mean - std_dev * k
    return upper_band, mean, lower_band


def get_calc_stock(data):
    from datetime import datetime

    # macd, signal, histogram = calculate_macd(data["close"])
    node = [
        [
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "TranAmnt",
            "5MvAvg",
            "20MvAvg",
            "50MvAvg",
            "60MvAvg",
            "120MvAvg",
            "240MvAvg",
            "UpperBand60_1",
            "LowerBand60_1",
            "LowerBand60_3",
        ]
    ]
    for i in range(len(data["timestamp"])):
        avg5 = calculate_moving_average(data["close"], i, 5)
        avg20 = calculate_moving_average(data["close"], i, 20)
        avg50 = calculate_moving_average(data["close"], i, 50)
        avg60 = calculate_moving_average(data["close"], i, 60)
        avg120 = calculate_moving_average(data["close"], i, 120)
        avg240 = calculate_moving_average(data["close"], i, 240)

        if avg5 == 0 or avg20 == 0 or avg50 == 0 or avg60 == 0 or avg120 == 0 or avg240 == 0:
            continue
        upper_band60_1, middle_band60_1, lower_band60_1 = calculate_bollinger_bands(
            data["close"], i, 60, 1
        )

        upper_band60_3, middle_band60_3, lower_band60_3 = calculate_bollinger_bands(
            data["close"], i, 60, 3
        )

        node.append(
            [
                datetime.fromtimestamp(data["timestamp"][i] / 1000).strftime(
                    "%Y-%m-%d"
                ),
                data["open"][i],
                data["high"][i],
                data["low"][i],
                data["close"][i],
                data["volume"][i],
                data["close"][i] * data["volume"][i],
                avg5,
                avg20,
                avg50,
                avg60,
                avg120,
                avg240,
                upper_band60_1,
                lower_band60_1,
                lower_band60_3,
            ]
        )
    return node


def insert_daily(params, stock, node):
    import mysql.connector
    import function.static as static
    from operator import attrgetter

    stock, period, db_config = params
    code, name, stocktype = attrgetter("code", "name", "stocktype")(stock)

    if len(node) > 1:
        conn = mysql.connector.connect(**db_config)
        query = """INSERT INTO STOCK_DATA (
                    code, 
                    date, 
                    open, 
                    high, 
                    low, 
                    close,
                    volume, 
                    transamnt, 
                    5mvavg, 
                    20mvavg, 
                    50mvavg,
                    60mvavg, 
                    120mvavg, 
                    240mvavg, 
                    upperband60_1,
                    lowerband60_1,
                    lowerband60_3,
                    create_date, 
                    update_date) VALUES """
        comma = ""
        for row in node[1:]:
            query += comma
            query += f" ('{code}', "
            for i in range(0, len(row)):
                query += f"'{row[i]}', "
            query += "now(), now())"
            comma = ","
        query += " ON DUPLICATE KEY UPDATE "
        query += f""" open = VALUES(open), 
                    high = VALUES(high), 
                    low = VALUES(low), 
                    close = VALUES(close), 
                    volume = VALUES(volume), 
                    transamnt = VALUES(transamnt), 
                    5mvavg = VALUES(5mvavg), 
                    20mvavg = VALUES(20mvavg), 
                    50mvavg = VALUES(50mvavg), 
                    60mvavg = VALUES(60mvavg), 
                    120mvavg = VALUES(120mvavg), 
                    240mvavg = VALUES(240mvavg), 
                    upperband60_1 = VALUES(upperband60_1),
                    lowerband60_1 = VALUES(lowerband60_1),
                    lowerband60_3 = VALUES(lowerband60_3),
                    update_date = now() """
        try:
            print(f"{code} has insert. name - {name} type - {stocktype}")
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            return node
        except Exception as e:
            print(e)
            print(query)
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    else:
        print(f"{code} has no data. name - {name} type - {stocktype}")


def insert_weekly(params, stock, node):
    import mysql.connector
    import function.static as static
    from operator import attrgetter

    stock, period, db_config = params
    code, name, stocktype = attrgetter("code", "name", "stocktype")(stock)
    if len(node) > 1:
        conn = mysql.connector.connect(**db_config)
        query = """INSERT INTO STOCK_DATA_WEEK (
                    code, 
                    date, 
                    open, 
                    high, 
                    low, 
                    close,
                    volume, 
                    transamnt, 
                    5mvavg, 
                    20mvavg, 
                    50mvavg, 
                    60mvavg, 
                    120mvavg, 
                    240mvavg, 
                    upperband60_1,
                    lowerband60_1,
                    create_date, 
                    update_date) VALUES """
        comma = ""
        for row in node[1:]:
            query += comma
            query += f" ('{code}', "
            for i in range(0, len(row) - 1):
                query += f"'{row[i]}', "
            query += "now(), now())"
            comma = ","
        query += " ON DUPLICATE KEY UPDATE "
        query += f""" open = VALUES(open), 
                    high = VALUES(high), 
                    low = VALUES(low), 
                    close = VALUES(close), 
                    volume = VALUES(volume), 
                    transamnt = VALUES(transamnt), 
                    5mvavg = VALUES(5mvavg), 
                    20mvavg = VALUES(20mvavg), 
                    50mvavg = VALUES(50mvavg), 
                    60mvavg = VALUES(60mvavg), 
                    120mvavg = VALUES(120mvavg), 
                    240mvavg = VALUES(240mvavg), 
                    upperband60_1 = VALUES(upperband60_1),
                    lowerband60_1 = VALUES(lowerband60_1),
                    update_date = now() """
        try:
            print(f"{code} has insert. name - {name} type - {stocktype}")
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            return node
        except Exception as e:
            print(e)
            print(query)
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    else:
        print(f"{code} has no data. name - {name} type - {stocktype}")


def get_stock_data_day_by_code(driver, params):
    import function.stock_lib as stock_lib
    from operator import attrgetter

    stock, period, db_config = params
    code, name, stocktype = attrgetter("code", "name", "stocktype")(stock)
    # 30년치를 일 1단위로 취득
    # data = get_stock_data(
    #     f"{code}.T", stock_lib.PERIOD_TYPE_YEAR, 30, stock_lib.FREQUENCY_TYPE_DAY, 1
    # )
    data = get_stock_data(
        driver,
        f"{code}.T",
        stock_lib.PERIOD_TYPE_YEAR,
        period,
        stock_lib.FREQUENCY_TYPE_DAY,
        1,
    )
    if data is None:
        print(f"{code} has no data. name - {name} type - {stocktype}")
        return None

    node = get_calc_stock(data)
    insert_daily(params, stock, node)


def get_stock_data_day_by_code_week(driver, params):
    import function.stock_lib as stock_lib
    from operator import attrgetter

    stock, period, db_config = params
    code, name, stocktype = attrgetter("code", "name", "stocktype")(stock)
    data = get_stock_data(
        driver,
        f"{code}.T",
        stock_lib.PERIOD_TYPE_YEAR,
        period,
        stock_lib.FREQUENCY_TYPE_WEEK,
        1,
    )
    if data is None:
        print(f"{code} has no data. name - {name} type - {stocktype}")
        return None
    node = get_calc_stock(data)
    insert_weekly(params, stock, node)


def main():
    # 일본 주식을 취득하는 모듈
    from concurrent.futures import ThreadPoolExecutor
    import function.common as common
    import function.static as static
    from selenium import webdriver
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By

    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")  # 필요하면

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    stocks = save_stock_list(static.db_config_jp)

    params = [(v, static.period, static.db_config_jp) for v in stocks]
    for param in params:
        try:
            get_stock_data_day_by_code(driver, param)
            get_stock_data_day_by_code_week(driver, param)
        except Exception as e:
            print(e)
    pass


if __name__ == "__main__":
    main()
