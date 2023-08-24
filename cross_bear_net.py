# editor by linbirg@2019-09-19
# 先改为py3版本，再考虑实盘优化，包括代码模块化、仓位控制、风险控制、止损、择时等

# 克隆自聚宽文章：https://www.joinquant.com/post/13382
# 标题：穿越牛熊基业长青的价值精选策略
# 作者：拉姆达投资
# changelog:
# edited@2020-02-04
# 1.增加移动止损 2. 移动止损>0不影响risk 
# edited@2020-02-05
# 1.优化持仓>g.stock_num时不再读取数据。2.购买时增加5日均线在10日均线上的择时过滤
# edited@2020-03-07
# 1.修复止损risk整数计算为0的bug；2. 均线策略增加MA20>MA30 3. 买的时候不再看ps in low（只进行pe5-40过滤，也为了有更多标的）
# 4. 增加sharp比率优化。
# edited@2020-03-15 1. 移动止损改为1/4 2. 现状单只股最大不超过40% 3.放宽ps在低区的限制到0.7
# edited@2020-03-18 增加pe_pb的数据存文件，并从文件加载数据计算分位的功能。
# edited@2020-03-19 增加大盘均线择时
# edited@2020-03-20 调整持仓逻辑修改为已有持仓只增不减,每年9月份检查一次坏的持仓，如果亏损太多选择继续持有
# edited@2022-10-26 暂时去掉市值的限制
# edited@2022-10-27 调仓逻辑调整为：涨一倍获利了结。宽止损。
# edited@2022-10-30 调仓逻辑为：每涨一倍卖出50%。
# edited@2022-11-1 调仓逻辑：每涨一倍卖出50%，每跌一半加仓一倍；每次加/3仓，留后续加仓资金；宽止损（80-90）；基本不移动止损（delta/5）
# edited@2023-8-24 实盘1策略，采用网格交易策略，选股采用优质小市值。 


'''
投资程序：
霍华．罗斯曼强调其投资风格在于为投资大众建立均衡、且以成长为导向的投资组合。选股方式偏好大型股，
管理良好且为领导产业趋势，以及产生实际报酬率的公司；不仅重视公司产生现金的能力，也强调有稳定成长能力的重要。
总市值大于等于50亿美元。
良好的财务结构。
较高的股东权益报酬。
拥有良好且持续的自由现金流量。
稳定持续的营收成长率。
优于比较指数的盈余报酬率。
'''

import pandas as pd
import numpy as np
import datetime as dt
import sys
# import jqdata


# from jqdata import get_trade_days

def is_python_2():
    return sys.version_info < (3,0)

def log_time(f):
    import time
    def decorater(*args,**kw):
        now = time.time() * 1000
        ret = f(*args,**kw)
        delta = time.time() * 1000 - now
        log.info('函数[%s]用时[%d]'%(f.__name__,delta))
        return ret
    
    return decorater
    

class DateHelper:
    @classmethod
    def to_date(cls,one):
        '''
        ### 将日期转换为Date类型。
        ### para:
        - one: 某一天，可以是Date、Datetime或者```%Y-%m-%d```格式的字符串
        '''
        import datetime
        if isinstance(one,str):
            one_date = datetime.datetime.strptime(one, "%Y-%m-%d")
            return one_date.date()
        
        if isinstance(one,datetime.datetime):
            return one.date()
        
        if isinstance(one,datetime.date):
            return one
        
        raise RuntimeError('不支持的日期格式')

    @classmethod
    def add_ndays(cls,one,ndays):
        import datetime
        one_date = cls.to_date(one)
        one_date = one_date + datetime.timedelta(ndays)
        return one_date 
    
    @classmethod
    def date_is_after(cls, one, other):
        one_date = cls.to_date(one)
        other_date = cls.to_date(other)
        
        is_after = one_date > other_date
        return is_after

    @classmethod
    def days_between(cls, one,other):
        one_date = cls.to_date(one)
        other_date = cls.to_date(other)
        
        interval = one_date - other_date
        return interval.days

class BzUtil():
    # 去极值
    @staticmethod
    def fun_winsorize(rs, type, num):
        # rs为Series化的数据
        rs = rs.dropna().copy()
        low_line, up_line = 0, 0
        if type == 1:   # 标准差去极值
            mean = rs.mean()
            #取极值
            mad = num*rs.std()
            up_line  = mean + mad
            low_line = mean - mad
        elif type == 2: #中位值去极值
            rs = rs.replace([-np.inf, np.inf], np.nan)
            median = rs.median()
            md = abs(rs - median).median()
            mad = md * num * 1.4826
            up_line = median + mad
            low_line = median - mad
        elif type == 3: # Boxplot 去极值
            if len(rs) < 2:
                return rs
            mc = sm.stats.stattools.medcouple(rs)
            rs.sort()
            q1 = rs[int(0.25*len(rs))]
            q3 = rs[int(0.75*len(rs))]
            iqr = q3-q1        
            if mc >= 0:
                    low_line = q1-1.5*np.exp(-3.5*mc)*iqr
                    up_line = q3+1.5*np.exp(4*mc)*iqr        
            else:
                    low_line = q1-1.5*np.exp(-4*mc)*iqr
                    up_line = q3+1.5*np.exp(3.5*mc)*iqr

        rs[rs < low_line] = low_line
        rs[rs > up_line] = up_line
        
        return rs
    
    #标准化
    @staticmethod
    def fun_standardize(s,type):
        '''
        s为Series数据
        type为标准化类型:1 MinMax,2 Standard,3 maxabs 
        '''
        data=s.dropna().copy()
        if int(type)==1:
            rs = (data - data.min())/(data.max() - data.min())
        elif type==2:
            rs = (data - data.mean())/data.std()
        elif type==3:
            rs = data/10**np.ceil(np.log10(data.abs().max()))
        return rs

    #中性化
    @staticmethod
    def fun_neutralize(s, df, module='pe_ratio', industry_type=None, level=2, statsDate=None):
        '''
        参数：
        s为stock代码 如'000002.XSHE' 可为list,可为str
        moduel:中性化的指标 默认为PE
        industry_type:行业类型(可选), 如果行业不指定，全市场中性化
        返回：
        中性化后的Series index为股票代码 value为中性化后的值
        '''
        s = df[df.code.isin(list(s))]
        s = s.reset_index(drop = True)
        s = pd.Series(s[module].values, index=s['code'])
        s = BzUtil.fun_winsorize(s,1,3)

        if industry_type:
            stocks = BzUtil.fun_get_industry_stocks(industry=industry_type, level=level, statsDate=statsDate)
        else:
            stocks = list(get_all_securities(['stock'], date=statsDate).index)

        df = df[df.code.isin(stocks)]
        df = df.reset_index(drop = True)
        df = pd.Series(df[module].values, index=df['code'])
        df = BzUtil.fun_winsorize(df,1, 3)
        rs = (s - df.mean())/df.std()

        return rs
    
    @classmethod
    def filter_paused(cls, stocks, end_date, day=1, x=1):
        '''
        @deprecated
        ### para:
        - stocks:股票池     
        - end_date:查询日期
        - day : 过滤最近多少天(包括今天)停牌过的股票,默认只过滤今天
        - x : 过滤最近day日停牌数>=x日的股票,默认1次

        ### 返回 :过滤后的股票池 
        '''
        if len(stocks) == 0:
            return stocks

        s = get_price(stocks, end_date=end_date, count =day, fields='paused').paused.sum()
        return s[s < x].index.tolist()

    @classmethod
    def filter_st(cls, stocks, end_date):
        if len(stocks) == 0:
            return stocks

        datas = get_extras('is_st', stocks, end_date = end_date , count=1).T
        return  datas[~datas.iloc[:,0]].index.tolist()

    @classmethod
    def filter_st_by_name(cls, stocks):
        no_st = []
        for s in stocks:
            info = get_security_info(s)
            up_name = info.display_name.upper()
            log.info('filter_st_by_name:%s'%(up_name))
            if up_name.startswith('ST') or up_name.startswith('*'):
                continue
            
            no_st.append(s)
        
        return no_st


    @staticmethod
    def remove_limit_up(stock_list):
        h = history(1, '1m', 'close', stock_list, df=False, skip_paused=False, fq='pre')
        h2 = history(1, '1m', 'high_limit', stock_list, df=False, skip_paused=False, fq='pre')
        tmpList = []
        for stock in stock_list:
            if h[stock][0] < h2[stock][0]:
                tmpList.append(stock)

        return tmpList

    # 剔除上市时间较短的产品
    @staticmethod
    def fun_delNewShare(current_dt, equity, deltaday):
        deltaDate = DateHelper.to_date(current_dt) - dt.timedelta(deltaday)
    
        tmpList = []
        for stock in equity:
            if get_security_info(stock).start_date < deltaDate:
                tmpList.append(stock)
    
        return tmpList
    
    @classmethod
    def remove_paused(cls, stock_list):
        current_data = get_current_data()
        tmpList = []
        for stock in stock_list:
            if not current_data[stock].paused:
                tmpList.append(stock)
        return tmpList
    
    # 根据行业取股票列表
    @staticmethod
    def fun_get_industry_stocks(industry, level=2, statsDate=None):
        if level == 2:
            stock_list = get_industry_stocks(industry, statsDate)
        elif level == 1:
            industry_list = BzUtil.fun_get_industry_levelI(industry)
            stock_list = []
            for industry_code in industry_list:
                tmpList = get_industry_stocks(industry_code, statsDate)
                stock_list = stock_list + tmpList
            stock_list = list(set(stock_list))
        else:
            stock_list = []

        return stock_list

    @classmethod
    def fun_get_factor(cls, df, factor_name, industry, level, statsDate):
        stock_list = BzUtil.fun_get_industry_stocks(industry, level, statsDate)
        rs = BzUtil.fun_neutralize(stock_list, df, module=factor_name, industry_type=industry, level=level, statsDate=statsDate)
        rs = BzUtil.fun_standardize(rs, 2)

        return rs

    
    @staticmethod
    def filter_without(stocks, bad_stocks):
        tmpList = []
        for stock in stocks:
            if stock not in bad_stocks:
                tmpList.append(stock)
        return tmpList

    @staticmethod
    def filter_intersection(stocks,others):
        ret = list(set(stocks) & set(others))
        return ret
    
    @classmethod
    def financial_data_filter_bigger(cls, stocks, factor=indicator.gross_profit_margin,val=40,startDate=None):
        q = query(indicator.code, factor).filter(factor>val,indicator.code.in_(stocks))
        df = get_fundamentals(q,date=startDate)
        
        return list(df['code'])
    
    @classmethod
    def filter_financial_data_area(cls, security_list, factor=valuation.pe_ratio, area=(5,35),startDate=None):
        q = query(indicator.code, factor).filter(factor>area[0],factor<area[1],indicator.code.in_(security_list))
        df = get_fundamentals(q,date=startDate)
        
        return list(df['code'])
    
    @classmethod
    def get_all_stocks(cls,startDate=None):
        q = query(valuation.code)
        df = get_fundamentals(q, date=startDate)
        return list(df['code'])

    @classmethod
    def print_with_name(cls, stocks):
        for s in stocks:
            info = get_security_info(s)
            log.info(info.code,info.display_name)


class QuantLib():
    @classmethod
    def get_fundamentals_sum(cls, table_name='indicator', search=indicator.adjusted_profit, statsDate=None,stocks=None):
        
        def _table_name_2_table(name):
            if name == 'indicator':
                table = indicator 
            elif name == 'income':
                table = income
            elif name == 'cash_flow':
                table = cash_flow
            elif name == 'balance':
                table = balance
            
            return table
            
        # 取最近的五个季度财报的日期
        def __get_quarter(table_name, statsDate,stocks=None):
            '''
            返回最近 n 个财报的日期
            返回每个股票最近一个财报的日期
            '''
            # 取最新一季度的统计日期
            
            table = _table_name_2_table(table_name)
            
            q = query(table.code, table.statDate)
            
            if stocks is not None:
                q = query(table.code, table.statDate).filter(table.code.in_(stocks))
            

            df = get_fundamentals(q, date = statsDate)
            stock_last_statDate = {}
            tmpDict = df.to_dict()
            for i in range(len(list(tmpDict['statDate'].keys()))):
                # 取得每个股票的代码，以及最新的财报发布日
                stock_last_statDate[tmpDict['code'][i]] = tmpDict['statDate'][i]
            
            if is_python_2():
                df = df.sort("statDate",ascending= False)
            else:
                df = df.sort_values("statDate",ascending= False)
            # 取得最新的财报日期
            last_statDate = df.iloc[0,1]

            this_year = int(str(last_statDate)[0:4])
            this_month = str(last_statDate)[5:7]

            if this_month == '12':
                last_quarter       = str(this_year)     + 'q4'
                last_two_quarter   = str(this_year)     + 'q3'
                last_three_quarter = str(this_year)     + 'q2'
                last_four_quarter  = str(this_year)     + 'q1'
                last_five_quarter  = str(this_year - 1) + 'q4'

            elif this_month == '09':
                last_quarter       = str(this_year)     + 'q3'
                last_two_quarter   = str(this_year)     + 'q2'
                last_three_quarter = str(this_year)     + 'q1'
                last_four_quarter  = str(this_year - 1) + 'q4'
                last_five_quarter  = str(this_year - 1) + 'q3'

            elif this_month == '06':
                last_quarter       = str(this_year)     + 'q2'
                last_two_quarter   = str(this_year)     + 'q1'
                last_three_quarter = str(this_year - 1) + 'q4'
                last_four_quarter  = str(this_year - 1) + 'q3'
                last_five_quarter  = str(this_year - 1) + 'q2'

            else:  #this_month == '03':
                last_quarter       = str(this_year)     + 'q1'
                last_two_quarter   = str(this_year - 1) + 'q4'
                last_three_quarter = str(this_year - 1) + 'q3'
                last_four_quarter  = str(this_year - 1) + 'q2'
                last_five_quarter  = str(this_year - 1) + 'q1'
        
            return last_quarter, last_two_quarter, last_three_quarter, last_four_quarter, last_five_quarter, stock_last_statDate

        # 查财报，返回指定值
        def __get_fundamentals_value(table_name, search, myDate, stocks=None):
            '''
            输入查询日期
            返回指定的财务数据，格式 dict
            '''
            table = _table_name_2_table(table_name)
                
            q = query(table.code, search, table.statDate)
            
            if stocks is not None:
                q = query(table.code, search, table.statDate).filter(table.code.in_(stocks))

            df = get_fundamentals(q, statDate = myDate).fillna(value=0)

            tmpDict = df.to_dict()
            stock_dict = {}
            name = str(search).split('.')[-1]
            for i in range(len(list(tmpDict['statDate'].keys()))):
                tmpList = []
                tmpList.append(tmpDict['statDate'][i])
                tmpList.append(tmpDict[name][i])
                stock_dict[tmpDict['code'][i]] = tmpList

            return stock_dict

        
        # 得到最近 n 个季度的统计时间
        last_quarter, last_two_quarter, last_three_quarter, last_four_quarter, last_five_quarter, stock_last_statDate = __get_quarter(table_name, statsDate)
    
        last_quarter_dict       = __get_fundamentals_value(table_name, search, last_quarter,stocks)
        last_two_quarter_dict   = __get_fundamentals_value(table_name, search, last_two_quarter,stocks)
        last_three_quarter_dict = __get_fundamentals_value(table_name, search, last_three_quarter,stocks)
        last_four_quarter_dict  = __get_fundamentals_value(table_name, search, last_four_quarter,stocks)
        last_five_quarter_dict  = __get_fundamentals_value(table_name, search, last_five_quarter,stocks)

        tmp_list = []
        stock_list = list(stock_last_statDate.keys())
        for stock in stock_list:
            tmp_dict = {}
            tmp_dict['code'] = stock
            value_list = []
            if stock in last_quarter_dict:
                if stock_last_statDate[stock] == last_quarter_dict[stock][0]:
                    value_list.append(last_quarter_dict[stock][1])

            if stock in last_two_quarter_dict:
                value_list.append(last_two_quarter_dict[stock][1])

            if stock in last_three_quarter_dict:
                value_list.append(last_three_quarter_dict[stock][1])

            if stock in last_four_quarter_dict:
                value_list.append(last_four_quarter_dict[stock][1])

            if stock in last_five_quarter_dict:
                value_list.append(last_five_quarter_dict[stock][1])

            for i in range(4 - len(value_list)):
                value_list.append(0)
            
            tmp_dict['0Q'] = value_list[0]
            tmp_dict['1Q'] = value_list[1]
            tmp_dict['2Q'] = value_list[2]
            tmp_dict['3Q'] = value_list[3]
            tmp_dict['sum_value'] = value_list[0] + value_list[1] + value_list[2] + value_list[3]
            tmp_list.append(tmp_dict)
        df = pd.DataFrame(tmp_list)

        return df
    
    @classmethod
    def get_fundamentals_tty(cls,table_name, search, statsDate, stocks=None):
        df = QuantLib.get_fundamentals_sum(table_name, search, statsDate,stocks)
        df = df.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df.rename(columns={'sum_value':'ttm_1y'}, inplace=True)
        df = df.fillna(value = 0)
        return df
    
    @classmethod
    @log_time
    def get_last_3y_inc_ttm_higher(cls,statsDate,stocks=None,hold=0.1):
        # stocks == None 表示所有股票
        df = QuantLib.get_fundamentals_tty('income', income.operating_revenue, statsDate,stocks)
        df2 = QuantLib.get_fundamentals_tty('income', income.operating_revenue, statsDate - dt.timedelta(365),stocks)
        df2.rename(columns={'ttm_1y':'ttm_2y'}, inplace=True)

        df3 = QuantLib.get_fundamentals_tty('income', income.operating_revenue, statsDate - dt.timedelta(365*2),stocks)
        df3.rename(columns={'ttm_1y':'ttm_3y'}, inplace=True)

        df4 = QuantLib.get_fundamentals_tty('income', income.operating_revenue, statsDate - dt.timedelta(365*3),stocks)
        df4.rename(columns={'ttm_1y':'ttm_4y'}, inplace=True)

        df = df.merge(df2, on='code')
        df = df.fillna(value=0)
        df['inc_operating_revenue_1y'] = 1.0*(df['ttm_1y'] - df['ttm_2y']) / abs(df['ttm_2y'])

        df = df.merge(df3, on='code')
        df['inc_operating_revenue_2y'] = 1.0*(df['ttm_2y'] - df['ttm_3y']) / abs(df['ttm_3y'])

        df = df.merge(df4, on='code')
        df['inc_operating_revenue_3y'] = 1.0*(df['ttm_3y'] - df['ttm_4y']) / abs(df['ttm_4y'])

        df = df[(df['inc_operating_revenue_3y'] > hold) & (df['inc_operating_revenue_2y'] > hold) & (df['inc_operating_revenue_1y'] > hold)]
        return df


class ValueLib:
    '''
    1.总市值≧市场平均值*1.0。
    2.最近一季流动比率≧市场平均值（流动资产合计/流动负债合计）。
    3.近四季股东权益报酬率（roe）≧市场平均值。
    4.近五年自由现金流量均为正值。（cash_flow.net_operate_cash_flow - cash_flow.net_invest_cash_flow）
    5.近四季营收成长率介于6%至30%（）。    'IRYOY':indicator.inc_revenue_year_on_year, # 营业收入同比增长率(%)
    6.近四季盈余成长率介于8%至50%。(eps比值)
    # added by yzr@2021/1/10
    7.近三年年均营收增加大于10%
    '''
    @classmethod
    def filter_by_mkt_cap_bigger_mean(cls, stocks, panel):
        '''
        ### 总市值≧市场平均值*1.0。
        ### para:
        - stocks:待过滤股票列表
        - panel:取好的财务数据

        ### return:
            过滤后的股票列表
        '''
        df_mkt = panel.loc[['circulating_market_cap'], 3, :]
        log.info('市场流通市值均值[%f]'%(df_mkt['circulating_market_cap'].mean()))
        df_mkt = df_mkt[df_mkt['circulating_market_cap']
                        > df_mkt['circulating_market_cap'].mean()*0.5]

        stocks_cap_bigger_mean = set(df_mkt.index)
        log.info('总市值≧市场平均值:%d'%(len(stocks_cap_bigger_mean)))

        return [s for s in stocks if s in stocks_cap_bigger_mean]
    
    @classmethod
    def filter_by_last_quart_cr_bigger_mean(cls, stocks, panel):
        '''
        ### 最近一季流动比率≧市场平均值（流动资产合计/流动负债合计）。
        '''
        df_cr = panel.loc[['total_current_assets',
                        'total_current_liability'], 3, :]
        # 替换零的数值
        df_cr = df_cr[df_cr['total_current_liability'] != 0]
        df_cr['cr'] = df_cr['total_current_assets'] / df_cr['total_current_liability']
        df_cr_temp = df_cr[df_cr['cr'] > df_cr['cr'].mean()*0.8]
        stocks_cr_bigger_mean = set(df_cr_temp.index)
        log.info('最近一季流动比率≧市场平均值(0.8):%d'%(len(stocks_cr_bigger_mean)))
        return [s for s in stocks if s in stocks_cr_bigger_mean]
    
    @classmethod
    def filter_by_4quart_roe_bigger_mean(cls, stocks, panel):
        '''
        ### 近四季股东权益报酬率（roe）≧市场平均值。
        '''
        l3 = set()
        for i in range(4):
            roe_mean = panel.loc['roe', i, :].mean()
            log.info('roe_mean:%f'%(roe_mean))
            df_3 = panel.iloc[:, i, :]
            df_temp_3 = df_3[df_3['roe'] > roe_mean]
            if i == 0:
                l3 = set(df_temp_3.index)

            if i > 0:
                l_temp = df_temp_3.index
                l3 = l3 & set(l_temp)
        stocks_4roe_bigger_mean = set(l3)
        log.info('近四季股东权益报酬率（roe）≧市场平均值:%d'%(len(stocks_4roe_bigger_mean)))
        return [s for s in stocks if s in stocks_4roe_bigger_mean]

    @classmethod
    def filter_by_5year_cf_neg(cls, stocks, current_dt):
        '''
        ### 近五年自由现金流量均为正值。
        ```cash_flow.net_operate_cash_flow - cash_flow.net_invest_cash_flow```
        '''
        y = DateHelper.to_date(current_dt).year 
        l4 = set()
        for i in range(1, 6):
            df = get_fundamentals(query(cash_flow.code, cash_flow.statDate, cash_flow.net_operate_cash_flow,
                                        cash_flow.net_invest_cash_flow), statDate=str(y-i))
            if len(df) <= 200:
                continue

            df['FCF'] = df['net_operate_cash_flow']-df['net_invest_cash_flow']
            df = df[df['FCF'] > 0]
            l_temp = df['code'].values
            if len(l4) == 0:
                l4 = l_temp
                continue

            l4 = set(l4) & set(l_temp)
            
        stocks_neg_5year_cach_flow = set(l4)
        log.info('近五年自由现金流量均为正值:%d'%(len(stocks_neg_5year_cach_flow)))
        return [s for s in stocks if s in stocks_neg_5year_cach_flow]
    
    @classmethod
    def filter_by_4q_inc_revenue_between(cls, stocks, panel, area=(6,60)):
        '''
        ### 近四季营收成长率介于6%至30%.   
          ```'IRYOY':indicator.inc_revenue_year_on_year # 营业收入同比增长率(%)```
        '''
        l5 = set()
        for i in range(4):
            df_5 = panel.iloc[:, i, :]
            df_temp_5 = df_5[(df_5['inc_revenue_year_on_year'] > area[0])
                            & (df_5['inc_revenue_year_on_year'] < area[1])]
            if i == 0:
                l5 = set(df_temp_5.index)

            if i > 0:
                l_temp = df_temp_5.index
                l5 = l5 & set(l_temp)
        stocks_4q_inc_revenue_between = set(l5)
        log.info('近四季营收成长率介于%d至%d:%d'%(area[0], area[1], len(stocks_4q_inc_revenue_between)))
        return [s for s in stocks if s in stocks_4q_inc_revenue_between]

    @classmethod
    @log_time
    def filter_by_4q_eps_between(cls, stocks, panel, area=(0.08,0.8)):
        '''
        ### 近四季盈余成长率介于8%至50%。(eps比值)
        '''
        l6 = set()
        for i in range(4):
            df_6 = panel.iloc[:, i, :]
            df_temp = df_6[(df_6['eps'] > area[0]) & (df_6['eps'] < area[1])]
            log.info('季盈余成长率(eps)均值：%.2f', df_6['eps'].mean()) 
            if i == 0:
                l6 = set(df_temp.index)

            if i > 0:
                l_temp = df_temp.index
                l6 = l6 & set(l_temp)
        stocks_4q_eps_bt = set(l6)
        log.info("近四季盈余成长率介于%d至%d:%d"%(area[0]*100, area[1]*100, len(stocks_4q_eps_bt)))
        return [s for s in stocks if s in stocks_4q_eps_bt]

    @classmethod
    @log_time
    def get_quarter_fundamentals(cls, stocks, num):
        '''
        ### 获取多期财务数据内容
        '''
        def get_curr_quarter(str_date):
            '''
            ### para:
            - str_date: 字符串格式的日期
            ```
            eg: '2019-03-31'
            ```
            '''
            quarter = str_date[:4]+'q'+str(int(str_date[5:7])//3) # //为整除
            return quarter


        def get_pre_quarter(quarter):
            '''
            ### 上一季
            ### para:
            - quarter:当前季 ```eg:2019q1```

            ### return: 上一季
            '''
            if quarter[-1] == '1':
                return str(int(quarter[:4])-1) + 'q4'
                
            if not quarter[-1] == '1':
                return quarter[:-1] + str(int(quarter[-1])-1)   

        q = query(valuation.code, income.statDate,
                income.pubDate).filter(valuation.code.in_(stocks))
        df = get_fundamentals(q)
        df.index = df.code
        stat_dates = set(df.statDate)
        stat_date_stocks = {sd: [
            stock for stock in df.index if df['statDate'][stock] == sd] for sd in stat_dates}

        q = query(valuation.code, valuation.code, valuation.circulating_market_cap, balance.total_current_assets, balance.total_current_liability,
                indicator.roe, cash_flow.net_operate_cash_flow, cash_flow.net_invest_cash_flow, indicator.inc_revenue_year_on_year, indicator.eps,
                indicator.gross_profit_margin
                )

        stat_date_panels = {sd: None for sd in stat_dates}

        for sd in stat_dates:
            quarters = [get_curr_quarter(sd)]
            for i in range(num-1):
                quarters.append(get_pre_quarter(quarters[-1]))
            nq = q.filter(valuation.code.in_(stat_date_stocks[sd]))

            pre_panel = {quarter: get_fundamentals(
                nq, statDate=quarter) for quarter in quarters}

            for quart in pre_panel:
                pre_panel[quart].index = pre_panel[quart].code.values

            panel = pd.Panel(pre_panel)
            panel.items = range(len(quarters))

            stat_date_panels[sd] = panel.transpose(2, 0, 1)

        final_panel = pd.concat(stat_date_panels.values(), axis=2)

        return final_panel.dropna(axis=2)


    @classmethod
    @log_time
    def filter_by_gross_profit_margin_bigger(cls,stocks,panel):
        '''
        近四季销售毛利率(%)(毛利/营业收入)≧median
        '''
        # gross_margin_stocks = BzUtil.financial_data_filter_bigger(stocks,indicator.gross_profit_margin,val)
        # log.info('销售毛利率(%)≧40:'+str(len(gross_margin_stocks)))
        # return BzUtil.filter_intersection(stocks, gross_margin_stocks)
        # df_gross = panel.loc['gross_profit_margin', 3, :]
        # log.info('销售毛利率中位数:%.2f'%(df_gross['gross_profit_margin'].median()))
        # df_gross_bigger_median = df_gross[df_gross['gross_profit_margin']>df_gross['gross_profit_margin'].median()]
        l7 = set()
        for i in range(4):
            median = panel.loc['gross_profit_margin',i,:].median()
            df_7 = panel.iloc[:, i, :]
            log.info('销售毛利率中位数:%.2f'%(median))
            df_temp = df_7[df_7['gross_profit_margin'] > 0.8*median]
            
            if i == 0:
                l7 = set(df_temp.index)

            if i > 0:
                l_temp = df_temp.index
                l7 = l7 & set(l_temp)
        stocks_gross_big_median_stocks = set(l7)
        log.info("近四季销售毛利率大于中位数(0.8):%d"%(len(stocks_gross_big_median_stocks)))
        return [s for s in stocks if s in stocks_gross_big_median_stocks]
    
    @classmethod
    @log_time
    def filter_by_3y_inc_revune_ttm_higher(cls,statsDate,stocks,hold=0.1):
        '''
        7. 近三年营收增长大于10%
        '''
        df = QuantLib.get_last_3y_inc_ttm_higher(statsDate=statsDate,stocks=stocks,hold=hold)
        return list(df['code'])


    @classmethod
    @log_time
    def filter_stocks_for_buy(cls, current_dt):
        all_stocks = BzUtil.get_all_stocks()
        # panel_data = cls.get_quarter_fundamentals(all_stocks, 4)
        # g.panel = panel_data
        if not hasattr(g,'panel') or g.panel is None:
            g.panel = cls.get_quarter_fundamentals(all_stocks, 4)

        panel_data = g.panel

        filter_stocks = cls.filter_by_4q_eps_between(all_stocks,panel_data)
        filter_stocks = cls.filter_by_4q_inc_revenue_between(filter_stocks,panel_data)
        filter_stocks = cls.filter_by_4quart_roe_bigger_mean(filter_stocks,panel_data)
        filter_stocks = cls.filter_by_5year_cf_neg(filter_stocks, current_dt)
        filter_stocks = cls.filter_by_last_quart_cr_bigger_mean(filter_stocks,panel_data)
        log.info('eps,revenue,roe,cf,cr选出以下股票：')
        BzUtil.print_with_name(filter_stocks)
        
        filter_stocks = BzUtil.filter_st(filter_stocks, current_dt)
        filter_stocks = BzUtil.filter_st_by_name(filter_stocks)
        filter_stocks = BzUtil.remove_paused(filter_stocks)
        
        filter_stocks = BzUtil.filter_financial_data_area(filter_stocks,factor=valuation.pe_ratio, area=(5,60))
        
        log.info('去除st停盘股票，考虑pe5-60选出以下股票：')
        BzUtil.print_with_name(filter_stocks)
        
        # 2022.10.26 去掉市值限制
        # filter_stocks = cls.filter_by_mkt_cap_bigger_mean(filter_stocks,panel_data)
        # log.info('考虑市值大于均值选出以下股票：')
        # BzUtil.print_with_name(filter_stocks)
        # 增加高增长选股的毛利选股
        # filter_stocks = cls.filter_by_gross_profit_margin_bigger(filter_stocks, panel_data)
        # log.info('考虑毛利率，不考虑ps低过滤选出以下股票：')
        # BzUtil.print_with_name(filter_stocks)
        # ps
        # filter_stocks = cls.filter_by_in_low_ps(filter_stocks)
        # log.info('考虑ps在低区选出以下股票：')
        # BzUtil.print_with_name(filter_stocks)

        filter_stocks = cls.filter_by_3y_inc_revune_ttm_higher(statsDate=current_dt,stocks=filter_stocks)
        log.info('3年营收增长大于10%选出以下股票：')
        BzUtil.print_with_name(filter_stocks)

        return filter_stocks
    
    @classmethod
    @log_time
    def filter_for_sell(cls, stocks, current_dt):
        all_stocks = BzUtil.get_all_stocks()
        if not hasattr(g,'panel') or g.panel is None:
            g.panel = cls.get_quarter_fundamentals(all_stocks, 4)
        
        panel_data = g.panel

        filter_stocks = cls.filter_by_4q_eps_between(stocks,panel_data)
        log.info('4q_eps filter：')
        BzUtil.print_with_name(filter_stocks)

        filter_stocks = cls.filter_by_4q_inc_revenue_between(filter_stocks,panel_data)
        log.info('4q_inc_revenue filter：')
        BzUtil.print_with_name(filter_stocks)

        filter_stocks = cls.filter_by_4quart_roe_bigger_mean(filter_stocks,panel_data)
        log.info('4quart_roe_bigger filter：')
        BzUtil.print_with_name(filter_stocks)

        filter_stocks = cls.filter_by_5year_cf_neg(filter_stocks, current_dt)
        log.info('5year_cf_neg filter：')
        BzUtil.print_with_name(filter_stocks)

        filter_stocks = cls.filter_by_last_quart_cr_bigger_mean(filter_stocks,panel_data)
        # 2022.10.26 去掉市值限制
        # filter_stocks = cls.filter_by_mkt_cap_bigger_mean(filter_stocks,panel_data)
        log.info('last_quart_cr and mkt cap filter：')
        BzUtil.print_with_name(filter_stocks)

        filter_stocks = BzUtil.filter_st(filter_stocks, current_dt)
        filter_stocks = BzUtil.filter_st_by_name(filter_stocks)
        # 增加高增长选股的毛利选股
        # filter_stocks = cls.filter_by_gross_profit_margin_bigger(filter_stocks,panel_data)

        filter_stocks = BzUtil.filter_financial_data_area(filter_stocks,factor=valuation.pe_ratio, area=(4,100))
        log.info('st and pe filter：')
        BzUtil.print_with_name(filter_stocks)

        # filter_stocks = cls.filter_by_3y_inc_revune_ttm_higher(statsDate=current_dt,stocks=filter_stocks)
        # log.info('3年营收增长大于10%选出以下股票：')
        # BzUtil.print_with_name(filter_stocks)
        
        can_hold = [s for s in stocks if s in filter_stocks]

        return can_hold

            


class Trader():
    def __init__(self, context,strategy=None):
        self.context = context

        self.strategy = strategy
        if self.strategy is None:
            self.strategy = TradeStrategyHL(self.context)
    
    def positions_num(self):
        return len(list(self.context.portfolio.positions.keys()))
    
    @classmethod
    def print_holdings(cls, context):
        if len(list(context.portfolio.positions.keys())) <= 0:
            log.info('没有持仓。')
            return
        
        import prettytable as pt

        tb = pt.PrettyTable(["名称","时间", "持仓天数","数量", "价值","盈亏"])
        total_balance = 0
        for p in context.portfolio.positions:
            pos_obj = context.portfolio.positions[p]
            p_balance = (pos_obj.price-pos_obj.avg_cost) * pos_obj.total_amount
            total_balance += p_balance
            tb.add_row([get_security_info(p).display_name + "(" + p + ")", 
                str(DateHelper.to_date(pos_obj.init_time)), 
                str(DateHelper.days_between(DateHelper.to_date(context.current_dt),DateHelper.to_date(pos_obj.init_time))), 
                pos_obj.total_amount,
                round(pos_obj.value,2),
                round(p_balance,2)])
        
        log.info(str(tb))
        log.info('总权益：', round(context.portfolio.total_value, 2),' 总持仓：',round(context.portfolio.positions_value,2),' 总盈亏:',round(total_balance,2))
    


# 获取前N个单位时间当时的收盘价
def get_close(stock, n, unit):
    return attribute_history(stock, n, unit, 'close')['close'][0]
    
# 获取现价相对N个单位前价格的涨幅
def get_return(stock, n, unit):
    price_before = attribute_history(stock, n, unit, 'close')['close'][0]
    price_now = get_close(stock, 1, '1m')
    if not isnan(price_now) and not isnan(price_before) and price_before != 0:
        return price_now / price_before
    
    # else
    return 0

'''
思路：
1、选上市200天以上主板成熟个股；
2、价格低于价值（pb< 1）；
3、公司真的在不断赚钱，赚真钱，主要用到：
（1）经营现金流：这个比利润真实，不像利润容易作假；
（2）扣非净利润：别靠做账做出假利润；
（3）总资产收益率：别靠负债做高ROE；
（4）净利润同比增长：说明经营良好；
再加上排序指标，取前5支，每月调仓。
随着股市波动，在大牛市顶端会自动空仓留住利润，因为那个位置选不出有价值的票了。
'''
# 通过基本的财务指标获取列表
@log_time
def sort_stocks_by_rank(initial_list,yesterday):
    # q = query(
    #     valuation.code, valuation.market_cap, valuation.circulating_market_cap
    # ).filter(
    #     valuation.code.in_(initial_list),
    #     valuation.pb_ratio > 0,
    #     # # valuation.market_cap > 50,
    #     indicator.inc_return > 0,
    #     indicator.inc_total_revenue_year_on_year > 0,
    #     # indicator.inc_net_profit_year_on_year > 0,
    #     indicator.ocf_to_operating_profit > 90,
    #     # valuation.pb_ratio < 1,
    #     cash_flow.subtotal_operate_cash_inflow > 1e6,
    #     indicator.adjusted_profit > 1e6,
    #     indicator.roa > 0.15,
    #     indicator.inc_net_profit_year_on_year > 0
    # # 	valuation.code.in_(initial_list)
    # ).order_by(indicator.roa.desc())
    # df = get_fundamentals(q, date=yesterday)
    # df.index = df.code
    weights = [1.0, 1.0, 1.6, 0.8, 2.0]
    q = query(
        valuation.code, indicator.roa,indicator.roe,valuation.pe_ratio,indicator.inc_net_profit_year_on_year,indicator.inc_total_revenue_year_on_year,valuation.pb_ratio,indicator.inc_return,indicator.ocf_to_operating_profit,balance.good_will,balance.total_assets,cash_flow.subtotal_operate_cash_inflow,indicator.adjusted_profit,valuation.market_cap, valuation.circulating_market_cap
    ).filter(
        valuation.code.in_(initial_list),
        valuation.pb_ratio > 0,
        indicator.inc_return > 0,
        indicator.inc_total_revenue_year_on_year > 20,
        indicator.inc_net_profit_year_on_year > 20,
        indicator.ocf_to_operating_profit > 90,
        cash_flow.subtotal_operate_cash_inflow > 1e6,
        indicator.adjusted_profit > 1e6,
        indicator.roa > 0.15
    ).order_by(valuation.market_cap.asc())
    df = get_fundamentals(q, date=yesterday)
    df.index = df.code
    df['good/total'] = df['good_will']/df['total_assets']
    df.fillna(0, inplace=True)
    df = df[df['good/total']<0.2]
    
    #获取原始值
    MC, CMC, PN, TV, RE = [], [], [], [], []
    initial_list = list(df.index)
    for stock in initial_list:
        #总市值
        mc = df.loc[stock]['market_cap']
        MC.append(mc)
        #流通市值
        cmc = df.loc[stock]['circulating_market_cap']
        CMC.append(cmc)
        #当前价格
        pricenow = get_close(stock, 1, '1m')
        PN.append(pricenow)
        #5日累计成交量
        total_volume_n = attribute_history(stock, 1200, '1m', 'volume')['volume'].sum()
        TV.append(total_volume_n)
        #60日涨幅
        m_days_return = get_return(stock, 60, '1d') 
        RE.append(m_days_return)
    #合并数据
    df = pd.DataFrame(index=initial_list,
        columns=['market_cap','circulating_market_cap','price_now','total_volume_n','m_days_return'])
    df['market_cap'] = MC
    df['circulating_market_cap'] = CMC
    df['price_now'] = PN
    df['total_volume_n'] = TV
    df['m_days_return'] = RE
    df = df.dropna()
    min0, min1, min2, min3, min4 = min(MC), min(CMC), min(PN), min(TV), min(RE)
    #计算合成因子
    temp_list = []
    for i in range(len(list(df.index))):
        score = weights[0] * math.log(min0 / df.iloc[i,0]) + weights[1] * math.log(min1 / df.iloc[i,1]) + weights[2] * math.log(min2 / df.iloc[i,2]) + weights[3] * math.log(min3 / df.iloc[i,3]) + weights[4] * math.log(min4 / df.iloc[i,4])
        temp_list.append(score)
    df['score'] = temp_list
    
    #排序并返回最终选股列表
    # df = df.sort_values(by='score', ascending=False)
    if is_python_2():
        df = df.sort('score',ascending= False)
    else:
        df = df.sort_values(by='score', ascending=False)
    
    final_list = list(df.index)
    
    return final_list
    
# 2-1 过滤ST及其他具有退市标签的股票
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not (
            current_data[stock].is_st or
            'ST' in current_data[stock].name or
            '*' in current_data[stock].name or
            '退' in current_data[stock].name)]

# 2-2 过滤停牌股票
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]
            
# 2-3 过滤科创板
def filter_kcb_stock(stock_list):
    return [stock for stock in stock_list if not (stock.startswith('68'))]

# 2-4 过滤创业板
def filter_cyb_stock(stock_list):
    return [stock for stock in stock_list if not (stock.startswith('30'))]

#  准备股票池
def prepare_stock_list(context):
    # type: (Context) -> list
    # 去掉次新股
    by_date = context.previous_date - datetime.timedelta(days=375)
    check_out_lists = get_all_securities(date=by_date).index.tolist()
    log.info("次新过滤:%d"%(len(check_out_lists)))
    #选市值在200亿元以下
    # check_out_lists = market_cap_filter(context, check_out_lists)
    
    # 去科创，ST
    check_out_lists = filter_kcb_stock(check_out_lists)
    check_out_lists = filter_cyb_stock(check_out_lists)
    check_out_lists = filter_st_stock(check_out_lists)
    check_out_lists = filter_paused_stock(check_out_lists)
    # check_out_lists = get_recent_limit_up_stock(context, check_out_lists, 120)
    # log.info("120日涨停过滤:%d"%(len(check_out_lists)))
    
    # check_out_lists = get_recent_in_low_stock(context, check_out_lists, 120)
    # log.info("120日低位过滤:%d"%(len(check_out_lists)))
    
    check_out_lists = sort_stocks_by_rank(check_out_lists,yesterday = context.previous_date)
    log.info("财务过滤:%d"%(len(check_out_lists)))
    
    return check_out_lists
    
## 开盘前运行函数
# @log_time
def get_buy_stocks(context):

    check_out_lists = ValueLib.filter_stocks_for_buy(context.current_dt)
    log.info("最终选出股票数量:%d"%(len(check_out_lists)))
        
    return check_out_lists
    
# 自定义下单
# 根据Joinquant文档，当前报单函数都是阻塞执行，报单函数（如order_target_value）返回即表示报单完成
# 报单成功返回报单（不代表一定会成交），否则返回None
def order_target_value_(security, value):
    if value == 0:
        log.debug("Selling out %s" % (security))
    else:
        log.debug("Order %s to value %f" % (security, value))
    
    # 如果股票停牌，创建报单会失败，order_target_value 返回None
    # 如果股票涨跌停，创建报单会成功，order_target_value 返回Order，但是报单会取消
    # 部成部撤的报单，聚宽状态是已撤，此时成交量>0，可通过成交量判断是否有成交
    return order_target_value(security, value)


# 开仓，买入指定价值的证券
# 报单成功并成交（包括全部成交或部分成交，此时成交量大于0），返回True
# 报单失败或者报单成功但被取消（此时成交量等于0），返回False
def open_position(security, value):
    order = order_target_value_(security, value)
    if order != None and order.filled > 0:
        return True
    return False


# 平仓，卖出指定持仓
# 平仓成功并全部成交，返回True
# 报单失败或者报单成功但被取消（此时成交量等于0），或者报单非全部成交，返回False
def close_position(position):
    security = position.security
    order = order_target_value_(security, 0)  # 可能会因停牌失败
    if order != None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            return True
    
    return False

        
class NetPositionManager:
    
    def __init__(self,max_num,fn_get_stocks):
        self.max_num = max_num
        self.fn_get_stocks = fn_get_stocks
        
        # 记录meta ： {'ms':(mean,std,context.current_dt),'open':(price,value,percent,context.current_dt)
        self.holds = {}
        
    def record_hold(self,stock,meta):
        self.holds[stock] = meta
        
    def remove_hold(self,stock):
        if stock not in self.holds:
            return
        
        self.holds.pop(stock)
        
    def update_last_percent(self,stock,price,last_percent,today):
        if stock not in self.holds:
            return
        
        last_price,value,percent,last_date = self.holds[stock]['open']
        self.holds[stock]['open'] = price,value,last_percent,today
        # log.info("len(holds):%d"%len(self.holds))
        
    def _get_mean_std_with_update(self,stock,yesterday,N=360):
        
        def _get_mean_std_by_get_price(stock,yesterday,N=360):
            df = get_price(stock, end_date=yesterday, frequency='daily', fields=['close'], count=N)
            
            mean = df['close'].mean()
            std = df['close'].std()
            
            return mean,std
        
        if stock in self.holds:
            mean,std,last_date = self.holds[stock]['ms']
            # 半年更新一次
            if DateHelper.days_between(yesterday,last_date) < 120:
                return mean,std
            
            mean,std = _get_mean_std_by_get_price(stock,yesterday,N)
            self.holds[stock]['ms'] = mean,std,yesterday

            return mean,std
            
        # 不在持仓中
        mean,std = _get_mean_std_by_get_price(stock,yesterday,N)
        
        return mean,std
            
        
    def _get_stock_meta_with_update(self,stock,yesterday,N=360):
        ''''''
        mean,std = self._get_mean_std_with_update(stock,yesterday,N)
        if stock in self.holds:
            price,value,percent,_ = self.holds[stock]['open']
        else:
            price,value,percent = None,None,None
        
        return mean,std,price,value,percent
        
    
    def _calc_percent(self,price,mean,std):
        trg_percent = 5
        alpha = 0
            
        if (price >= mean + 2*std and price < mean + 3*std):
            trg_percent = 4
            alpha = 2
        
        elif price >= mean + 3 * std and price < mean + 4 * std:
            trg_percent = 3
            alpha = 3
            
        elif (price >= mean + 4 * std and price < mean + 6 * std):
            trg_percent = 2
            alpha = 4
        
        elif (price >= mean + 6 * std):
            trg_percent = 0
            alpha = 6
            
        # 低于均值，加仓    
        elif price <= mean - 3* std:
            trg_percent = 10
            alpha = -3
            
        elif price > mean - 3* std and price <= mean - 2*std:
            trg_percent = 9
            alpha = -2
            
        elif price > mean - 2* std and price <= mean - std:
            trg_percent = 8
            alpha = -1
            
        elif price > mean - std and price <= mean + std:
            trg_percent = 7
            alpha = 0
            
        return trg_percent,alpha
        
    def _get_close(self,stock, n, unit):
        return attribute_history(stock, n, unit, 'close')['close'][0]
        
    def adjust(self,context):
        position_count = len(context.portfolio.positions)
        if self.max_num <= position_count:
            log.info("仓位已满，只调仓，不开仓。")
            self.adjust_only(context)
            return
        
        self.positions_open(context)
        
    @log_time
    def positions_open(self,context):
        self.open_only(context)
        self.adjust_only(context)
    
    def open_only(self,context):
        position_count = len(context.portfolio.positions)
        if self.max_num <= position_count:
            log.info("仓位已满，只调仓，不开仓。")
            return
        
        # buy_stocks = get_buy_stocks(context)
        buy_stocks = self.fn_get_stocks(context)
        buy_stocks = [s for s in buy_stocks if s not in context.portfolio.positions ]
    
        value = context.portfolio.total_value / self.max_num
        
        for stock in buy_stocks:
            
            mean,std = self._get_mean_std_with_update(stock,context.previous_date)
            price = self._get_close(stock, 1, '1m')
            
            if price > mean + std:
                log.info("[%s]价格[%.2f]高于1std[%.2f]，不开仓。"%(stock,price,mean+std))
                continue
            
            percent,alpha = self._calc_percent(price,mean,std)
            log.info("[%s]价格[%.2f]不超过[%d]std[%.2f]，开[%d]成仓。"%(stock,price,alpha,std,percent))
               
            open_position(stock, value*percent/10.0)
            
            self.record_hold(stock,{'ms':(mean,std,context.current_dt),'open':(price,value,percent,context.current_dt)})
            
            if len(context.portfolio.positions) >= self.max_num:
               break
    @log_time    
    def adjust_only(self,context):
        holding_list = list(context.portfolio.positions)
        if holding_list is None or len(holding_list) <= 0:
            log.info("没有持仓")
            return
        
        
        # current_data = get_current_data()
        
        for stock in holding_list:
            mean,std,last_price,open_value,last_percent = self._get_stock_meta_with_update(stock,context.previous_date)
            price = self._get_close(stock, 1, '1m')
            
            position = context.portfolio.positions[stock]
            
            if open_value is None:
                log.info("warning! 存在未记录的持仓[%s]"%(stock))
                # open_value = position.value*2
                open_value = context.portfolio.total_value / self.max_num
                last_percent = int(position.value*10/open_value)
                last_price = position.avg_cost
                self.record_hold(stock,{'ms':(mean,std,context.current_dt),'open':(last_price,open_value,last_percent,context.current_dt)})
            
            # value = context.portfolio.total_value / g.stock_num
            
            trg_percent,alpha = self._calc_percent(price,mean,std)
                
            log.info('[%s]波动幅度在[%d]std[%.2f],调整仓位至[%d]成'%(position.security,alpha,alpha*std,trg_percent))
            
            if last_percent == trg_percent:
                log.info("[%s]仓位未变动，不操作。"%(stock))
                continue
            
            # target_val = open_value * trg_percent/10.0
            target_val = position.value * trg_percent/last_percent*1.0
                
            if target_val <= 0:
                if price < position.avg_cost * 1.1:
                    log.info('[%s]盈利未超过百分之10，暂不清仓。[p:%.2f,avg_cost:%.2f]'%(stock,price,position.avg_cost))
                    continue
                
                if close_position(position):
                    self.remove_hold(stock)
                    log.info('[%s]卖出[price:%.2f,avg_cost:%.2f,mean:%.2f,std:%.2f]'%(position.security,price,position.avg_cost,mean,std))
                
                continue
                
            
            delta = target_val - position.value 
            
            if abs(delta) < price * 100:
                 log.info("[%s]仓位变动太小，不操作"%(stock))
                 continue
             
            if (delta < 0 and price < last_price * 1.5):
                log.info('[%s]距离上次操作未盈利超过百分之50，暂不减仓。[cur_p:%.2f,last_price:%.2f]'%(stock,price,last_price))
                continue
            
            if (delta > 0 and price > last_price * 0.7):
                log.info('[%s]距离上次操作未超过百分之30，暂不加仓。[cur_p:%.2f,last_price:%.2f]'%(stock,price,last_price))
                continue
            
            log.info("[%s]调整仓位[%.2f]至目标价值[%.2f],仓位变化[%.2f]"%(stock,position.value,target_val,target_val-position.value))
            
            if open_position(stock, target_val):
                self.update_last_percent(stock,price,trg_percent,context.current_dt) 
            
    
    def yearly_adjust(self,context):
        # 每6个月调整一次持仓
        current_day = DateHelper.to_date(context.current_dt)
        if  not (current_day.month%6 == 0):
            return
        
        holding_list = list(context.portfolio.positions)
        
        if holding_list is None or len(holding_list) <= 0:
            log.info("没有持仓")
            return
        
        buy_stocks = self.fn_get_stocks(context)
        
        
        for h in holding_list:
            if h in buy_stocks:continue
        
            if h not in buy_stocks:
                log.info('[%s]不在待买股票列表中，将执行年度清仓。'%h)
                position = context.portfolio.positions[h]
                
                price = self._get_close(h, 1, '1m')
                
                if price < position.avg_cost * 1.1:
                    log.info('[%s]盈利未超过百分之10，暂不清仓。[p:%.2f,avg_cost:%.2f]'%(h,price,position.avg_cost))
                    continue
                
                if close_position(position):
                    self.remove_hold(h)
           
## 开盘时运行函数
def market_open(context):
    log.info("运行 market_open 函数")
    # g.stopper.check_stop(context)
    g.trader.adjust(context)
    
def monthly_adjust(context):
    # 每年10月调整一次持仓
    g.trader.yearly_adjust(context)
    

## 收盘后运行函数
def after_market_close(context):
    Trader.print_holdings(context)
    
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    # log.info('##############################################################')
 


def initialize(context):
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    log.set_level('order', 'error')
    # 策略参数设置
    # 操作的股票列表
    
    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003,
                             close_commission=0.0003, min_commission=5), type='stock')

    
    run_daily(market_open, time='10:00', reference_security='000300.XSHG')
    run_monthly(monthly_adjust, 5, time='14:30', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')


# 开盘前运行函数
def before_market_open(context):
    pass
   


def adjust_risk_before_market_open(context):
    pass

    

def check_stop_at_noon(context):
    pass


@log_time
def after_code_changed(context):
    g.stock_num = 4
    
    g.trader = NetPositionManager(g.stock_num,get_buy_stocks)