# import math
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np
import jqdatasdk as jq
import talib as tl

# import logging as log


def get_ndays_before(day, ndays=29):
    d_today = datetime.datetime.strptime(day, "%Y-%m-%d")
    date_before = (d_today - timedelta(days=ndays)).strftime("%Y-%m-%d")

    return date_before


def get_stock_list(cur_date='2018-06-26',
                   begin_date='2018-01-01',
                   MARKET_MIN_CAP=100,
                   MARKET_MAX_CAP=500):
    """
    获取从指定日期开始的，市值在指定区间的，非st，股票列表, 以及详细信息（code，circulating_cap，circulating_market_cap）
    """

    # 总市值在100-500亿
    q = jq.query(jq.valuation.code, jq.valuation.circulating_cap,
                 jq.valuation.circulating_market_cap).filter(
                     jq.valuation.code.notin_(['002473.XSHE',
                                               '000407.XSHE']),  # why?
                     jq.valuation.circulating_market_cap < MARKET_MAX_CAP,
                     jq.valuation.circulating_market_cap >= MARKET_MIN_CAP)

    df = jq.get_fundamentals(q, date=begin_date)
    df.index = list(df['code'])
    # 去除st
    st = jq.get_extras(
        'is_st',
        list(df['code']),
        start_date=cur_date,
        end_date=cur_date,
        df=True)

    st = st.iloc[0]
    stock_list = list(st[st == False].index)

    return stock_list, df


def get_stocks_data(stocks, today, ndays=29):
    """ 根据过去{ndays}天的历史数据，从{stocks}列表中选区截至{today}的股票列表的详细数据。
        数据包含：
        'open', 'close', 'high', 'low', 'paused', 'volume',
        high_h,low_l,close_h,close_l,15_h,15_l,start,end,
        usual_wave, max_wave, start_end
    """
    start_date = get_ndays_before(today, ndays)

    df_list = jq.get_price(
        stocks,
        start_date=start_date,
        end_date=today,
        frequency='daily',
        fields=['open', 'close', 'high', 'low', 'paused', 'volume'])

    # 获取收盘价
    df_close = df_list['close']
    df_high = df_list['high']
    df_low = df_list['low']

    df_paused_sum = df_list['paused']
    df_paused_sum = pd.DataFrame(np.sum(df_paused_sum))
    df_paused_sum.columns = ['paused_sum']

    df_volume = df_list['volume']
    df_volume = df_volume.T
    df_volume = df_volume.ix[:, [-1]]
    # for col in df_volume.columns:
    #     df_volume[col] = df_volume[col] / (infos['circulating_cap'] * 100)

    df_volume.columns = ['volume']

    # 最高价的最高价
    df_high_h = pd.DataFrame(df_high.max())
    df_high_h.columns = ['high_h']

    # 最低价的最低价
    df_low_l = pd.DataFrame(df_low.min())
    df_low_l.columns = ['low_l']

    # 收盘价的最高价
    df_close_h = pd.DataFrame(df_high.max())
    df_close_h.columns = ['close_h']

    # 收盘价的最低价
    df_close_l = pd.DataFrame(df_close.min())
    df_close_l.columns = ['close_l']

    # 前15日最高价
    df_15_h = pd.DataFrame(df_high.head(15).max())
    df_15_h.columns = ['15_h']

    # 后15日最低价
    df_15_l = pd.DataFrame(df_low.tail(15).min())
    df_15_l.columns = ['15_l']

    # 开始日收盘价
    df_start = df_close.head(1)
    df_start.index = ['start']
    df_start = df_start.T

    # 结束日收盘价
    df_end = df_close.tail(1)
    df_end.index = ['end']
    df_end = df_end.T

    # 获取停牌
    df_paused = df_list['paused'].T
    df_paused = df_paused.ix[:, [-1]]
    df_paused.columns = ['paused']

    df_result = pd.concat(
        [df_start, df_end], axis=1, join_axes=[df_start.index])
    df_result = pd.concat(
        [df_result, df_paused], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_volume], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_high_h], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_low_l], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_close_h], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_close_l], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_15_h], axis=1, join_axes=[df_result.index])
    df_result = pd.concat(
        [df_result, df_15_l], axis=1, join_axes=[df_result.index])

    df_result['usual_wave'] = (
        df_result['close_h'] - df_result['close_l']) / df_result['start']

    df_result['max_wave'] = (
        df_result['high_h'] - df_result['low_l']) / df_result['start']
    df_result['start_end'] = (
        df_result['end'] - df_result['start']) / df_result['start']

    df_result['usual_wave'] = df_result['usual_wave'] / df_result['max_wave']
    df_result['start_end'] = df_result['start_end'] / df_result['usual_wave']

    return df_result


# 根据过去{ndays}天的历史数据，从{stocks}列表中选区截至{today}的买列表。
def get_buy_stocks(stocks_infos):

    stocks_infos = stocks_infos[stocks_infos['paused'] == 0]
    stocks_infos = stocks_infos[stocks_infos['start_end'] < 0]
    stocks_infos = stocks_infos[stocks_infos['15_h'] == stocks_infos['high_h']]
    stocks_infos = stocks_infos[stocks_infos['15_l'] == stocks_infos['low_l']]

    stocks_infos = stocks_infos.sort_values(
        by='usual_wave', ascending=False).head(10)
    stocks_infos = stocks_infos.sort_values(
        by='start_end', ascending=False).tail(5)

    # print(stocks_infos)

    stocks_infos = stocks_infos[
        stocks_infos['start_end'] / stocks_infos['max_wave'] > -0.85]
    stocks_infos = stocks_infos[stocks_infos['max_wave'] < 0.7]

    print("buy_stocks:", stocks_infos)
    return stocks_infos.index


def calc_AR(stock, today, ndays):
    start_day = get_ndays_before(today, ndays)

    df_list = jq.get_price(
        stock,
        start_date=start_day,
        end_date=today,
        frequency='daily',
        fields=['open', 'high', 'low'])

    ar = sum(df_list['high'] - df_list['open']) / sum(
        df_list['open'] - df_list['low']) * 100
    return ar


def get_buyFlag_by_AR(ar):
    '''
    AR指标 在180以上时，股市极高活跃
    AR指标 在120 - 180时，股市高活跃
    AR指标 在70 - 120时，股市盘整
    AR指标 在60 - 70以上时，股市走低
    AR指标 在60以下时，股市极弱

    返回：1-极弱 2-走低 3-盘整 4-高活跃 5-极高活跃
    '''
    brFlag = 1

    if ar > 180:
        brFlag = 5
    elif ar > 120 and ar <= 180:
        brFlag = 4
    elif ar > 70 and ar <= 120:
        brFlag = 3
    elif ar > 60 and ar <= 70:
        brFlag = 2
    else:
        brFlag = 1

    return brFlag


def calc_RSI(stock, today, ndays=120, CON_FAST_RSI=20, CON_SLOW_RSI=60):
    """ 计算制定股票的RSI值，并返回(RSI_FAST,RSI_SLOW), 其中的快慢由CON_FAST_RSI和CON_SLOW_RSI指定 """
    start_day = get_ndays_before(today, ndays)

    df_list = jq.get_price(
        stock,
        start_date=start_day,
        end_date=today,
        frequency='daily',
        fields=['close'])

    closep = df_list['close'].values

    RSI_F = tl.RSI(closep, timeperiod=CON_FAST_RSI)
    RSI_S = tl.RSI(closep, timeperiod=CON_SLOW_RSI)

    return RSI_F, RSI_S


def get_buyFlag_by_RSI(rsi_f, rsi_s):
    '''
    慢速RSI 在55以上时，单边上涨市场，快速RSI上穿慢速RSI即可建仓
    慢速RSI 在55以下时，调整震荡市场，谨慎入市，取连续N天快速RSI大于慢速RSI建仓
    慢速RSI 在60以上时，牛市，无需减仓操作持仓即可

    返回值："上行" 50 "高位" 40 "持仓" 30 "盘整建仓" 20 "下行" 10
    '''
    rsiS = rsi_s[-1]
    # rsiF = rsi_f[-1]

    is_fast_greater_slow = [rsi_f[i] > rsi_s[i] for i in range(len(rsi_s))]

    # 基准仓位值
    bsFlag = 10

    if rsiS > 55 and is_fast_greater_slow[-1]:
        bsFlag = 50  # "上行"
    elif rsiS > 68:
        bsFlag = 40  # "高位"
    elif rsiS > 60:
        bsFlag = 30  # "持仓"
    elif rsiS <= 55 and is_fast_greater_slow[-1] and is_fast_greater_slow[-2] and is_fast_greater_slow[-3] and is_fast_greater_slow[-4] and is_fast_greater_slow[-5]:
        bsFlag = 20  # "盘整建仓"
    else:
        bsFlag = 10  # "下行"

    return bsFlag


def get_stock_buyflag_by_risk(stock, today, ndays=29):
    rsi_f, rsi_s = calc_RSI(stock, today, ndays)
    rsi = get_buyFlag_by_RSI(rsi_f, rsi_s)

    ar_day3 = calc_AR(stock, today, ndays)
    ar_day2 = calc_AR(stock, get_ndays_before(today, 1), ndays)
    ar_day1 = calc_AR(stock, get_ndays_before(today, 2), ndays)

    # log.debug(stock, "rsi:", rsi, "ar_day3:", ar_day3, "ar_day2", ar_day2,
    #           "ar_day1", ar_day1)

    print(stock, "rsi:", rsi, "ar_day3:", ar_day3, "ar_day2", ar_day2,
          "ar_day1", ar_day1)

    buy_flag = 2

    if rsi == 10:
        buy_flag = 0
    elif rsi == 20:
        buy_flag = 2
    else:
        buy_flag = 1

    # 趋势控制
    if ar_day1 < 60 and ar_day2 < 60 and ar_day3 < 60:
        # 持续低迷
        print("持续低迷")
        buy_flag = 0
    elif ar_day2 * 0.3 > ar_day3:
        # 急跌
        print("急跌")
        buy_flag = 0
    elif ar_day1 < ar_day2 and ar_day2 < ar_day3 and ar_day3 < 80 and ar_day3 > 65:
        # 弱市回升
        print("弱市回升")
        buy_flag = 1
    elif ar_day1 > ar_day2 and ar_day2 > ar_day3 and ar_day3 < 150 and ar_day1 > 200:
        # 强市下跌
        print("强市下跌")
        buy_flag = 0
    elif ar_day1 > ar_day2 and ar_day2 > ar_day3 and ar_day3 < 150 and ar_day1 > 150:
        # 中市下跌
        print("中市下跌")
        buy_flag = 2
    elif ar_day1 > ar_day2 * 0.95 and ar_day2 > ar_day3 and ar_day3 < ar_day2 * 0.6 and ar_day1 > 180:
        # 强市下跌
        print("强市下跌")
        buy_flag = 0
    elif ar_day1 > 70 and ar_day2 > 70 and ar_day3 > 70:
        # 维持正常
        print("维持正常")
        buy_flag = 1

    else:
        print("其他情况")
        buy_flag = 2

    return buy_flag


if __name__ == "__main__":
    user_name = '18602166903'
    passwd = '13773275'
    jq.auth(user_name, passwd)

    today = '2018-09-04'

    buy_flag = get_stock_buyflag_by_risk("000300.XSHG", today, 10)

    print("buy_flag", buy_flag)

    if buy_flag != 0:
        stocks, stocks_info = get_stock_list(
            today,
            begin_date='2018-01-02',
            MARKET_MIN_CAP=10,
            MARKET_MAX_CAP=1000)
        stocks_infos = get_stocks_data(stocks, today)
        buy_stocks = get_buy_stocks(stocks_infos)
        print(buy_stocks)

        for stock in buy_stocks:
            buy_flag = get_stock_buyflag_by_risk(stock, today, 10)
            print("stock:", stock, "buy_flag:", buy_flag)
