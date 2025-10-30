# 디렉토리 생성
def check_directory(dir_path):
    import os

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def createQuery(table, columns, values):
    query = f"INSERT INTO {table} ("
    query += ", ".join(columns)
    query += ") VALUES ("
    query += ", ".join([f"'{v}'" for v in values])
    query += ")"
    return query


def setup_custom_logger(dir, name):
    import logging

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.FileHandler(
        f"{dir}\\log\\logfile_{name}.log"
    )  # 로그 파일 이름 및 경로 지정
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    return logger


def write_log(logger, msg):
    logger.info(msg)
    print(msg)


def write_data(filename, msg):
    with open(filename, mode="a", newline="", encoding="utf-8") as file:
        file.write(msg)
        file.write("\n")


def create_sequences(data_input, data_target, seq_length, predict_days):
    import numpy as np

    x = []
    y = []
    for i in range(len(data_input) - seq_length - predict_days + 1):
        x.append(data_input[i : i + seq_length])
        y.append(data_target[i + seq_length : i + seq_length + predict_days])
    return np.array(x), np.array(y)


def save_list_to_csv(file_path, data):
    import os

    if os.path.exists(file_path):
        os.remove(file_path)

    with open(file_path, mode="w", newline="", encoding="utf-8") as file:
        import csv

        writer = csv.writer(file)
        writer.writerows(data)


def get_date_2year_ago():
    from datetime import datetime, timedelta

    two_years_ago = datetime.today() - timedelta(days=365 * 2)
    return two_years_ago.strftime("%Y-%m-%d")


def execute_query(db_config, query):
    import mysql.connector

    conn = mysql.connector.connect(**db_config)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
