import mysql.connector


class db_connector():

    def __init__(self):
        pass

    def select(self, query, bufferd=True):
        cursor = self.dbconn.cursor(buffered=bufferd)
        cursor.execute(query)
        return cursor

    def merge(self, query, values, bufferd=True):
        try:
            cursor = self.dbconn.cursor(buffered=bufferd)
            cursor.execute(query, values)
            self.dbconn.commit()
        except Exception as e:
            self.dbconn.rollback()
            raise e

    def merge_bulk(self, query, values, bufferd=True):
        try:
            cursor = self.dbconn.cursor(buffered=bufferd)
            cursor.executemany(query, values)
            self.dbconn.commit()
        except Exception as e:
            self.dbconn.rollback()
            raise e

    def execute(self, query, bufferd=True):
        try:
            cursor = self.dbconn.cursor(buffered=bufferd)
            cursor.execute(query)
            self.dbconn.commit()
        except Exception as e:
            self.dbconn.rollback()
            raise e
    def __enter__(self):
        self.dbconn = mysql.connector.connect(host="localhost", user="stocksearcher", passwd="a12345", database="stocksearcher")
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        self.dbconn.close();
