import datetime
from datetime import timedelta

import jqdatasdk as jq


def get_ndays_before(day, ndays=29):
    d_today = datetime.datetime.strptime(day, "%Y-%m-%d")
    date_before = (d_today - timedelta(days=ndays)).strftime("%Y-%m-%d")

    return date_before


def get_stock_list(begin_date=None, MARKET_MIN_CAP=100, MARKET_MAX_CAP=500):
    """
    获取从指定日期开始的，市值在指定市值区间的股票列表, 以及详细信息（code，circulating_cap，circulating_market_cap）
    """

    # 总市值在100-500亿
    q = jq.query(jq.valuation.code, jq.valuation.circulating_cap,
                 jq.valuation.circulating_market_cap).filter(
                     jq.valuation.circulating_market_cap < MARKET_MAX_CAP,
                     jq.valuation.circulating_market_cap >= MARKET_MIN_CAP)

    df = jq.get_fundamentals(q, date=begin_date)
    df.index = list(df['code'])

    return df
