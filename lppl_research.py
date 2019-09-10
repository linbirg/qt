from matplotlib import pyplot as plt
# import datetime
import lib.lppl as lppltool
import lib.datetime_utils as ut

import jqdatasdk as jq

import numpy as np
import pandas as pd
import seaborn as sns
sns.set_style('white')

times = []


def get_stock_closes(stock, end_date, ndays=350):
    start_date = ut.get_ndays_before(end_date, ndays)
    print("start_date:", start_date, " end_date:", end_date)
    df_list = jq.get_price(
        stock,
        start_date=start_date,
        end_date=end_date,
        frequency='daily',
        fields=['close'])
    return df_list['close'].tolist()


if __name__ == "__main__":
    user_name = '18602166903'
    passwd = '13773275'
    jq.auth(user_name, passwd)

    today = '2016-06-10'

    closes = get_stock_closes('000300.XSHG', today, 200)
    lppltool.set_closes(closes)
    print("len(closes)", len(closes))
    lppltool.set_lppl_flag(False)

    limits = ([8.4, 8.8], [-1, -0.1], [-20, 20], [.1, .9], [-1, 1], [12, 18],
              [0, 2 * np.pi])

    # limits = ([8.5, 8.6], [-0.25, -0.12], [-3, 3], [.15, .4], [0.05, 0.1],
    #           [4, 8], [0, 2 * np.pi])

    x = lppltool.Population(limits, 30, 0.3, 1.5, .1)
    for i in range(2):
        x.Fitness()
        x.Eliminate()
        x.Mate()
        x.Mutate()

    x.Fitness()
    values = x.BestSolutions(3)
    for x in values:
        print(x.print_individual())

    times = np.linspace(0, len(closes) + 50, len(closes) + 50 + 1)
    cnt = 50 + 1
    deps = [values[0].get_DataSeries()[1][-1] for i in range(cnt)]
    indexs = values[0].get_DataSeries()[1] + deps

    # data = pd.DataFrame({
    #     'Date': values[0].get_DataSeries()[0],
    #     'Index': values[0].get_DataSeries()[1],
    #     'Fit1': values[0].get_ExpData(),
    #     'Fit2': values[1].get_ExpData(),
    #     'Fit3': values[2].get_ExpData()
    # })
    data = pd.DataFrame({
        'Date': times,
        'Index': indexs,
        'Fit1': values[0].get_expre_data(times),
        'Fit2': values[1].get_expre_data(times),
        'Fit3': values[2].get_expre_data(times)
    })
    data = data.set_index('Date')
    data.plot(figsize=(14, 8))
    plt.show()
