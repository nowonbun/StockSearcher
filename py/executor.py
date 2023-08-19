from readExcel import read_excel
from dbConnector import db_connector
from yahoo_finance_api2 import share
from yahoo_finance_api2.exceptions import YahooFinanceError
from datetime import date
from dateutil.relativedelta import relativedelta
from datetime import datetime
from multiprocessing import Process, Lock
import joblib

def create_table():
    with db_connector() as dbconn:
        dbconn.execute("""
        create table if not exists stocklist(
            code nvarchar(10) Primary key,
            date nvarchar(8),
            name nvarchar(200),
            stockcode nvarchar(200),
            type33code nvarchar(200),
            type17code nvarchar(200),
            typescalecode nvarchar(200)
        )
        """)

        dbconn.execute("""
        create table if not exists stockdata(
            code nvarchar (10),
            timestamp bigint,
            date date,
            open_price bigint,
            high_price bigint,
            low_price bigint,
            closed_price bigint,
            volume_price bigint,
            isuse bit default 1,
        
            primary key (code,timestamp),
            foreign key (code) references stocklist(code)
        )
        """)

        dbconn.execute("""
        create table if not exists normalMoveAvg(
            code nvarchar (10),
            date date,
            MvAvg5 bigint,
            MvAvg20 bigint,
            MvAvg60 bigint,
            MvAvg120 bigint,
            MvAvg240 bigint,
            volume_price bigint,
            isuse bit default 1,
        
            primary key (code,date),
            foreign key (code) references stocklist(code)
        )
        """)

        dbconn.execute("""
        create table if not exists fibonachiMoveAvg(
            code nvarchar (10),
            date date,
            MvAvg5 bigint,
            MvAvg8 bigint,
            MvAvg13 bigint,
            MvAvg21 bigint,
            MvAvg34 bigint,
            MvAvg55 bigint,
            MvAvg89 bigint,
            MvAvg144 bigint,
            MvAvg233 bigint,
            volume_price bigint,
            isuse bit default 1,
        
            primary key (code,date),
            foreign key (code) references stocklist(code)
        )
        """)

        dbconn.execute("""
        create table if not exists bollingerbandMoveAvg(
            code nvarchar (10),
            date date,
            upperline bigint,
            lowerline bigint,
            MvAvg60 bigint,
            StDv bigint,
            volume_price bigint,
            isuse bit default 1,
            primary key (code,date),
            foreign key (code) references stocklist(code)
        )
        """)


def init_code():
    re = read_excel()
    list = re.run()

    with db_connector() as dbconn:
        dbconn.execute("set FOREIGN_KEY_CHECKS = 0")
        dbconn.execute("truncate table bollingerbandMoveAvg")
        dbconn.execute("truncate table fibonachiMoveAvg")
        dbconn.execute("truncate table normalMoveAvg")
        dbconn.execute("truncate table stockdata")
        dbconn.execute("truncate table stocklist")
        dbconn.execute("set FOREIGN_KEY_CHECKS = 1")

        dbconn.merge_bulk("insert into stocklist (code, date, name, stockcode, type33code, type17code, typescalecode) values (%s, %s, %s, %s, %s, %s, %s)", list)
        pass



def insert_stockdata():
    with db_connector() as dbconn:
        #debug = 1
        # dbconn.execute("delete from stockdata where date >= %s" % str(date.today() + relativedelta(years=-3)))
        # for row in dbconn.select("select code,date,name,stockcode,type33code,type17code,typescalecode from stocklist"):
        # node = []
        # for row in dbconn.select("select code from stocklist"):
        #     try:
        #         print(str(debug) + "   " + row[0])
        #         my_share = share.Share(row[0] + ".T")
        #         data = my_share.get_historical(share.PERIOD_TYPE_YEAR, 3, share.FREQUENCY_TYPE_DAY, 1)
        #         # data = my_share.get_historical(share.PERIOD_TYPE_MONTH, 1, share.FREQUENCY_TYPE_DAY, 1)
        #         # dbconn.execute("delete from stockdata where date >= %s and code = %s" % (str(date.today() + relativedelta(years=-3)), row[0]))
        #         idx = 0
        #         node = []
        #         for timestamp in data["timestamp"]:
        #             node.append(tuple([
        #                 row[0], timestamp, datetime.utcfromtimestamp(timestamp/1000).strftime("%Y-%m-%d"), data["open"][idx], data["high"][idx], data["low"][idx], data["close"][idx], data["volume"][idx], 1
        #             ]))
        #             idx = idx+1
        #         # dbconn.merge_bulk("insert into stockdata (code, timestamp, date, open_price, high_price, low_price, closed_price, volume_price, isuse) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)", node)
        #         debug = debug+1
        #         #dbconn.execute("delete from stockdata where date >= %s and code = %s" % (str(date.today() + relativedelta(years=-3)), row[0]))
        #         #dbconn.merge_bulk("insert into stockdata (code, timestamp, date, open_price, high_price, low_price, closed_price, volume_price, isuse) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)", node)
        #     except Exception as e:
        #         print(e)
        # pass
    
        def function(row):
            try:
                print(row[0])
                my_share = share.Share(row[0] + ".T")
                data = my_share.get_historical(share.PERIOD_TYPE_YEAR, 3, share.FREQUENCY_TYPE_DAY, 1)
                # data = my_share.get_historical(share.PERIOD_TYPE_MONTH, 1, share.FREQUENCY_TYPE_DAY, 1)
                # dbconn.execute("delete from stockdata where date >= %s and code = %s" % (str(date.today() + relativedelta(years=-3)), row[0]))
                idx = 0
                node = []
                for timestamp in data["timestamp"]:
                    node.append(tuple([
                        row[0], timestamp, datetime.utcfromtimestamp(timestamp/1000).strftime("%Y-%m-%d"), data["open"][idx], data["high"][idx], data["low"][idx], data["close"][idx], data["volume"][idx], 1
                    ]))
                    idx = idx+1
                # dbconn.merge_bulk("insert into stockdata (code, timestamp, date, open_price, high_price, low_price, closed_price, volume_price, isuse) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)", node)
                #dbconn.execute("delete from stockdata where date >= %s and code = %s" % (str(date.today() + relativedelta(years=-3)), row[0]))
                #dbconn.merge_bulk("insert into stockdata (code, timestamp, date, open_price, high_price, low_price, closed_price, volume_price, isuse) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)", node)
                return node
            except Exception as e:
                print(e)
            pass
        
        result = joblib.Parallel(n_jobs=-1)(joblib.delayed(function)(i) for i in dbconn.select("select code from stocklist"))
        dbconn.execute("delete from stockdata where date >= %s" % str(date.today() + relativedelta(years=-3)))
        
        print("****************INSERT****************")
        for node in result:
            print(node[0])
            dbconn.merge_bulk("insert into stockdata (code, timestamp, date, open_price, high_price, low_price, closed_price, volume_price, isuse) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)", node)  
        # dbconn.execute("delete from stockdata where date >= %s" % str(date.today() + relativedelta(years=-3)))
        # dbconn.merge_bulk("insert into stockdata (code, timestamp, date, open_price, high_price, low_price, closed_price, volume_price, isuse) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)", node)
    pass
