from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
import io
import sys
import json
from yahoo_finance_api2 import share
from yahoo_finance_api2.exceptions import YahooFinanceError


class myHandler(BaseHTTPRequestHandler):
    def __get_Parameter(self, key):
        if hasattr(self, "_myHandler__param") == False:
            if "?" in self.path:
                self.__param = dict(urlparse.parse_qsl(
                    self.path.split("?")[1], True))
            else:
                self.__param = {}
        if key in self.__param:
            return self.__param[key]
        return None

    def __get_Post_Parameter(self, key):
        if hasattr(self, "_myHandler__post_param") == False:
            data = self.rfile.read(int(self.headers['Content-Length']))
            if data is not None:
                self.__post_param = dict(urlparse.parse_qs(data.decode()))
            else:
                self.__post_param = {}
        if key in self.__post_param:
            return self.__post_param[key][0]
        return None

    def __set_Header(self, code):
        self.send_response(code)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()

    def __set_Body(self, data):
        self.wfile.write(data.encode())

    def do_GET(self):
        stock = self.__get_Parameter('stock')
        periodType_p = self.__get_Parameter('periodType')
        period_p = self.__get_Parameter('period')
        frequencyType_p = self.__get_Parameter('frequencyType')
        frequency_p = self.__get_Parameter('frequency')

        errorMsg = ''
        if stock == None:
            errorMsg += ' stock'
        if periodType_p == None:
            errorMsg += ' periodType'
        if period_p == None:
            errorMsg += ' period'
        if frequencyType_p == None:
            errorMsg += ' frequencyType'
        if frequency_p == None:
            errorMsg += ' frequency'

        if errorMsg != '':
            self.__set_Header(400)
            self.__set_Body(json.dumps({'error': 'not parameter :'+errorMsg}))
            return

        periodType = None
        if periodType_p == 'year':
            periodType = share.PERIOD_TYPE_YEAR
        elif periodType_p == 'month':
            periodType = share.PERIOD_TYPE_MONTH
        elif periodType_p == 'week':
            periodType = share.PERIOD_TYPE_WEEK
        elif periodType_p == 'day':
            periodType = share.PERIOD_TYPE_DAY
        else:
            self.__set_Header(400)
            self.__set_Body(json.dumps({'error': 'wrong parameter : periodType'}))
            return

        try:
            period = int(period_p)
        except TypeError as e:
            self.__set_Header(400)
            self.__set_Body(json.dumps({'error': 'wrong parameter : period'}))
            return

        frequencyType = None
        if frequencyType_p == 'year':
            frequencyType = share.FREQUENCY_TYPE_YEAR
        elif frequencyType_p == 'month':
            frequencyType = share.FREQUENCY_TYPE_MONTH
        elif frequencyType_p == 'day':
            frequencyType = share.FREQUENCY_TYPE_DAY
        elif frequencyType_p == 'minute':
            frequencyType = share.FREQUENCY_TYPE_MINUTE
        else:
            self.__set_Header(400)
            self.__set_Body(json.dumps({'error': 'wrong parameter : frequencyType'}))
            return

        try:
            frequency = int(frequency_p)
        except TypeError as e:
            self.__set_Header(400)
            self.__set_Body(json.dumps({'error': 'wrong parameter : frequency'}))
            return

        my_share = share.Share(stock)

        try:
            body = my_share.get_historical(periodType, period, frequencyType, frequency)
        except YahooFinanceError as e:
            self.__set_Header(502)
            self.__set_Body(json.dumps({'error': e}))
            return
        self.__set_Header(200)
        self.__set_Body(json.dumps(body))

    def do_POST(self):
        self.__set_Header(400)
        self.__set_Body(json.dumps({'error': 'You can''t access the post.'}))


httpd = HTTPServer(('', 80), myHandler)
httpd.serve_forever()
