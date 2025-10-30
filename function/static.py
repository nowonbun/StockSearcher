import configparser

config = configparser.ConfigParser()
config.read("config.ini")

dir = config["default"]["output_dir"]

db_config_jp = {
    "host": config["database"]["host"],
    "port": config["database"]["port"],
    "user": config["database"]["user"],
    "password": config["database"]["password"],
    "database": config["database"]["database_jp"],
}

db_config_kr = {
    "host": config["database"]["host"],
    "port": config["database"]["port"],
    "user": config["database"]["user"],
    "password": config["database"]["password"],
    "database": config["database"]["database_kr"],
}

start_date = config["default"]["start_date"]
end_date = config["default"]["end_date"]
period = int(config["default"]["period"])


# dir = config["default"]["output_dir"]
# period = int(config["default"]["period"])
# machine_name = config["machine"]["machine_name"]
# model_type = config["machine"]["modelType"]


# input_column = [
#     "Open",
#     "High",
#     "Low",
#     "Close",
#     "TranAmnt",
#     "5MvAvg",
#     "20MvAvg",
#     "60MvAvg",
#     "120MvAvg",
#     "240MvAvg",
#     "UpperBand20",
#     "LowerBand20",
#     "UpperBand60",
#     "LowerBand60",
# ]
# target_column = ["Close"]

# # 입력과 타겟 시퀀스 생성
# sequence_length = int(config["machine"]["sequence_length"])  # x축에 들어갈 데이터 길이
# predict_days = int(config["machine"]["predict_days"])  # 예측할 날짜
# machine_name = config["machine"]["machine_name"]
# weight = float(config["machine"]["weight"])
# weight2 = float(config["machine"]["weight2"])

# end_date = config["learn"]["end_date"]

# epochs = int(config["learn"]["epochs"])
# learning_weight = int(config["learn"]["weight"])
# learning_rate = 1 / learning_weight
# beta_1 = float(config["learn"]["beta_1"])
# beta_2 = float(config["learn"]["beta_2"])
# cut_rate = float(config["learn"]["cut_rate"])
# count = int(config["learn"]["count"])
# skip_number = int(config["learn"]["skip_number"])
# machine_download = bool(config["search"]["machine_download"])
