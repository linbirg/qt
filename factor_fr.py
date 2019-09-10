"""
https://uqer.datayes.com/v3/community/share/5b28734482dc6c011600a06a
本篇文章主要参考了方正证券的研究报告————《“市场行为的宝藏”系列研究（二）：抢跑者的脚步声，基于价量互动的选股因子》

交易类因子是Alpha研究中重要的一个部分，我们可以通过行为学的眼光考察价量信息，从而挖掘出我们需要的Alpha因子。我们从市场中发现成交量泄漏了知情交易者的行动，成交量有时会先于价格出现波动，
即换手率与第二天股价的波动呈现出正相关性，而这种相关性的高低代表了信息泄露的程度，我们可以利用这一指标规避那些信息泄露程度高的股票，以防在股票博弈上陷入劣势。

本文通过考察量价波动关系构造FR（Front Running）因子，并对因子做改进，主要内容如下：

因子的灵感与构造逻辑；
通过收益分解优化因子；
最优复合因子及选股能力分析；
我们最终通过收益分解优化、复合的FR因子IC_IR达到2.54，多空对冲的年化收益为7.80%,年化波动4.09%,最大回撤4.50%，体现出较为稳健的选股能力。
基于A股“量在价先”的这类现象，我们可以做一个统计，统计根据换手率分组下不同组别涨跌幅绝对值的大小，结果发现随着换手率均值的上升，涨跌幅的绝对值也呈上升趋势，这个结果表明市场的确
存在信息泄露的现象，我们希望通过量价关系捕捉到价格异动的先兆，规避知情交易带来博弈上的劣势，因此我们构造了FR（Front Runnint）抢跑因子。

因子逻辑

我们在每月底回看过去一个月的交易数据，计算T日换手率与T+1日涨跌幅的关系，即FR = corr(turn, |ret|),其中turn是T日换手率，ret是T+1的涨跌幅的绝对值，corr是Pearson相关系数，在计算的
时候我们会剔除一月中停牌日数过多的股票；从表达式来看，因为FR是一个量价因子，为了验证FR是新的Alpha因子，我们在截面上对常见的因子(自由流通市值对数、20日动量、20日均换手率、60日波动
率)及行业因子(这里采用申万一级行业)进行回归剔除他们的影响，得到的残差即为纯净的FR因子，记为pure_fr。

二、因子收益分解优化
这里我们为了处理方便，我会同时计算FR与第二部分的收益分解优化后的因子。为了考察在A股大涨前和大跌前的信息泄露程度是否相同，信息泄露的因子在好消息和坏消息上是否具有相同的alpha，我们将
价格波动分解为上涨和下跌，我们在FR因子的逻辑基础上将过去一个月的交易数据根据T+1日的的涨跌幅分为两部分，如下图所示
图片注释
利用相对上涨的数据计算相关性，在横截面上回归掉市值、动量、换手率、波动率和行业，记为FRu,同理利用下跌的数据计算FRd，计算区间为(20080131-20180531)，月频更新，计算各自的原始IC及pure)IC,计算代码如下。
"""

import datetime
# import time
import os
import logging as log

import jqdatasdk as jq
import stocks_helper as helper
from lib import datetime_utils as dtUtils

# import numpy as np
import pandas as pd
# import copy
# import matplotlib.pyplot as plt
# import statsmodels.api as sm
# import scipy.stats as st
import seaborn as sns
sns.set_style('whitegrid')

log.basicConfig(level=log.DEBUG)
logger = log.getLogger(__name__)

g_path = "./data/FR_factor"


def check_or_create_dir(path="./data/FR_factor"):
    if not os.path.exists(path):
        logger.debug("create path:" + path)
        os.makedirs(path)


def get_trade_list(start, end):
    """
    return:
        trade_list: 时间区间内的交易日
        month_end:  月末时间
        month_start: 月初时间
    """
    trade_list = jq.get_trade_days(start, end)

    return trade_list


def remove_st(stocks, start, end):
    """
    去掉ST股票之后的股票列表
    """
    # 去除st
    st = jq.get_extras(
        'is_st', stocks, start_date=start, end_date=end, df=True)

    st = st.iloc[0]
    stock_list = list(st[st == False].index)

    return stock_list


def remove_new(stocks, tradeDate=None, day=1):
    """
    list: 去掉新股股票之后的股票列表
    """
    tradeDate = tradeDate if tradeDate is not None else datetime.datetime.now()
    nday = helper.get_ndays_before(str(tradeDate.date()), day)
    rm_news = []
    for s in stocks:
        info = jq.get_security_info(s)
        # 上市日期小于指定日期
        if str(info.start_date) < nday:
            rm_news.append(s)

    return rm_news


def get_stocks_turnover(begin_date=None,
                        MARKET_MIN_CAP=10,
                        MARKET_MAX_CAP=1000):
    """
    获取从指定日期开始的，市值在指定市值区间的股票列表，以及详细信息（code，turnover_ratio，circulating_cap，circulating_market_cap）
    """

    # 总市值在100-500亿
    q = jq.query(jq.valuation.code, jq.valuation.turnover_ratio,
                 jq.valuation.circulating_cap,
                 jq.valuation.circulating_market_cap).filter(
                     jq.valuation.circulating_market_cap < MARKET_MAX_CAP,
                     jq.valuation.circulating_market_cap >= MARKET_MIN_CAP)

    df = jq.get_fundamentals(q, date=begin_date)
    df.index = list(df['code'])

    return df


def get_stocks_price(stocks, begin_date, end_date=None):
    """获取stocks的行情数据。end_date如果未none，默认今天
    """
    end_date = end_date if end_date is not None else datetime.datetime.now(
    ).date()
    df_list = jq.get_price(
        stocks,
        start_date=begin_date,
        end_date=end_date,
        frequency='daily',
        fields=['open', 'close', 'high', 'low', 'paused', 'volume'])

    return df_list


def next_trade_day(day, ndays=1):
    return dtUtils.get_next_tradeday_after(day, ndays)


def get_stocks_ret_T1(stocks, date):
    next_day = next_trade_day(date)
    df_p = get_stocks_price(stocks, date, next_day)
    df_close = df_p['close'].T
    ret = (df_close.iloc[:, 0] - df_close.iloc[:, 1]) / df_close.iloc[:, 0]

    return ret, df_close.iloc[:, 0]


def get_one_day_frame(date):
    df_turnovers = get_stocks_turnover(date)
    ret, close = get_stocks_ret_T1(list(df_turnovers['code']), date)
    df_turnovers['date'] = date
    df_turnovers['ret'] = ret
    df_turnovers['close'] = close

    return df_turnovers


def get_ndays_frame(date, ndays, csv="fr.csv"):
    frams = []
    pd_csv = read_csv(csv)
    for i in range(ndays):
        day = next_trade_day(date, i)
        if not csv_contain_day(pd_csv, day):
            frame = get_one_day_frame(day)
            frams.append(frame)

    frams.append(pd_csv)
    df = pd.concat(frams)

    return df


def read_csv(filename="fr.csv"):
    file_path = g_path + "/" + filename
    check_or_create_dir(g_path)
    pd_csv = pd.DataFrame()
    if os.path.exists(file_path):
        pd_csv = pd.read_csv(file_path)
    # logger.debug(pd_csv)

    return pd_csv


def list_remove_dup(li):
    """列表去重
    """
    nw_li = list(set(li))
    nw_li.sort(key=li.index)
    return nw_li


def pd_save_to_csv(frames, filename="fr.csv"):
    file_path = g_path + "/" + filename
    pd_csv = read_csv(filename)
    days = list_remove_dup(list(frames['date']))
    pd_days = []
    for day in days:
        if not csv_contain_day(pd_csv, day):
            pd_days.append(frames[frames['date'] == day])

    pd_days.append(pd_csv)

    pd_all = pd.concat(pd_days)
    pd_all.to_csv(file_path, index=False)


def csv_contain_day(pd_csv, day):
    return not pd_csv.empty and len(pd_csv[pd_csv['date'] == day]) > 0


def func(df):
    # print(df)
    return df['turnover_ratio'].corr(df['ret'])


if __name__ == "__main__":
    user_name = '18602166903'
    passwd = '13773275'
    jq.auth(user_name, passwd)

    frame = get_ndays_frame('2018-08-01', 20, 'fr_data.csv')
    pd_save_to_csv(frame, 'fr_data.csv')
    # file_path = g_path + "/fr.csv"
    # frame.to_csv(file_path)

    # signal_fr = frame.groupby('code').apply(func)
    signal_fr = frame.groupby('code').apply(
        lambda df: df['turnover_ratio'].corr(df['ret'], method='pearson'))
    # signal_fr.dropna(axis=1)

    frame_positive = frame[frame['ret'] > 0]
    frame_negative = frame[frame['ret'] < 0]
    signal_fru = frame_positive.groupby('code').apply(
        lambda df: df['turnover_ratio'].corr(df['ret'], method='pearson'))

    signal_frd = frame_negative.groupby('code').apply(
        lambda df: df['turnover_ratio'].corr(df['ret'], method='pearson'))

    signal = pd.concat(
        [signal_fr, signal_fru, signal_frd], axis=1, join='outer')
    signal.columns = ['fr', 'fru', 'frd']
    signal['code'] = signal.index
    signal['date'] = dtUtils.get_next_tradeday_after('2018-08-01', 20)
    signal.dropna(inplace=True)

    logger.debug(signal)
    pd_save_to_csv(signal, 'fr.csv')
    # logger.debug(df_close.at['002871.XSHE','2018-08-16'])
