/*
    일본 주식에서...
    1. 1일선이 5일선 상향
    2. 5일선이 8일선 하향
    3. 8일선 이후 피보나치

    거래 대금은 1억엔 이상
    주가는 2천원 이하
*/
select
    *
from
    stock_data_jp sd
where
    date = '2024-08-07'
    and close > `5MvAvg`
    and `5MvAvg` < `8MvAvg`
    and `8MvAvg` > `13MvAvg`
    and `13MvAvg` > `21MvAvg`
    and `21MvAvg` > `34MvAvg`
    and `34MvAvg` > `55MvAvg`
    and `55MvAvg` > `89MvAvg`
    -- and TransAmnt > 1000000000
    and TransAmnt > 100000000
    and `Close` < 2000;

/*
    일본 주식에서...
    1. 피보나치

    거래량은 1억엔 이상
*/
select
    *
from
    stock_data_jp sd
where
    date = '2024-08-07'
    and close > `5MvAvg`
    and `5MvAvg` > `8MvAvg`
    and `8MvAvg` > `13MvAvg`
    and `13MvAvg` > `21MvAvg`
    and `21MvAvg` > `34MvAvg`
    and `34MvAvg` > `55MvAvg`
    -- and `55MvAvg` > `89MvAvg`
    -- and TransAmnt > 1000000000 -- '1,000,000,000'
    and TransAmnt > 100000000 -- '100,000,000'
    and `Close` < 2000
    order by TransAmnt desc;

-----------------------------------------------

/*
    한국 주식에서...
    1. 1일선이 5일선 상향
    2. 5일선이 8일선 하향
    3. 8일선 이후 피보나치

    거래 대금은 10억원 이상
*/
select
    *
from
    stock_data_kr sd
where
    date = '2024-08-07'
    and close > `5MvAvg`
    and `5MvAvg` < `8MvAvg`
    and `8MvAvg` > `13MvAvg`
    and `13MvAvg` > `21MvAvg`
    and `21MvAvg` > `34MvAvg`
    and `34MvAvg` > `55MvAvg`
    and `55MvAvg` > `89MvAvg`
    and TranAmnt > 1000000000 -- '1,000,000,000'

/*
    한국 주식에서...
    1. 피보나치

    거래량은 10억원 이상
*/
select
    *
from
    stock_data_kr sd
where
    date = '2024-08-07'
    and close > `5MvAvg`
    and `5MvAvg` > `8MvAvg`
    and `8MvAvg` > `13MvAvg`
    and `13MvAvg` > `21MvAvg`
    and `21MvAvg` > `34MvAvg`
    and `34MvAvg` > `55MvAvg`
    and TranAmnt > 1000000000 -- '1,000,000,000'
    order by TranAmnt desc;


-----------------------------------------------


select
    *
from
    stock_data_jp sd
where
    date = '2024-08-07'
    and close > `5MvAvg`
    and `5MvAvg` > `8MvAvg`
    and `8MvAvg` > `13MvAvg`
    and `13MvAvg` > `21MvAvg`
    and `21MvAvg` > `34MvAvg`
    and `34MvAvg` > `55MvAvg`
    and `60MvAvg` * 0.95 < `close`
    and `60MvAvg` * 1.05 > `close`
    and TransAmnt > 500000000 -- '500,000,000'
    -- and `Close` < 2000;