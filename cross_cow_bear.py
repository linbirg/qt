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
    
    # 行业列表
    @staticmethod
    def fun_get_industry(cycle=None):
        # cycle 的参数：None取所有行业，True取周期性行业，False取非周期性行业
        industry_dict = {
            'A01':False,# 农业 	1993-09-17
            'A02':False,# 林业 	1996-12-06
            'A03':False,# 畜牧业 	1997-06-11
            'A04':False,# 渔业 	1993-05-07
            'A05':False,# 农、林、牧、渔服务业 	1997-05-30
            'B06':True, # 煤炭开采和洗选业 	1994-01-06
            'B07':True, # 石油和天然气开采业 	1996-06-28
            'B08':True, # 黑色金属矿采选业 	1997-07-08
            'B09':True, # 有色金属矿采选业 	1996-03-20
            'B11':True, # 开采辅助活动 	2002-02-05
            'C13':False, #	农副食品加工业 	1993-12-15
            'C14':False,# 食品制造业 	1994-08-18
            'C15':False,# 酒、饮料和精制茶制造业 	1992-10-12
            'C17':True,# 纺织业 	1992-06-16
            'C18':True,# 纺织服装、服饰业 	1993-12-31
            'C19':True,# 皮革、毛皮、羽毛及其制品和制鞋业 	1994-04-04
            'C20':False,# 木材加工及木、竹、藤、棕、草制品业 	2005-05-10
            'C21':False,# 家具制造业 	1996-04-25
            'C22':False,# 造纸及纸制品业 	1993-03-12
            'C23':False,# 印刷和记录媒介复制业 	1994-02-24
            'C24':False,# 文教、工美、体育和娱乐用品制造业 	2007-01-10
            'C25':True, # 石油加工、炼焦及核燃料加工业 	1993-10-25
            'C26':True, # 化学原料及化学制品制造业 	1990-12-19
            'C27':False,# 医药制造业 	1993-06-29
            'C28':True, # 化学纤维制造业 	1993-07-28
            'C29':True, # 橡胶和塑料制品业 	1992-08-28
            'C30':True, # 非金属矿物制品业 	1992-02-28
            'C31':True, # 黑色金属冶炼及压延加工业 	1994-01-06
            'C32':True, # 有色金属冶炼和压延加工业 	1996-02-15
            'C33':True, # 金属制品业 	1993-11-30
            'C34':True, # 通用设备制造业 	1992-03-27
            'C35':True, # 专用设备制造业 	1992-07-01
            'C36':True, # 汽车制造业 	1992-07-24
            'C37':True, # 铁路、船舶、航空航天和其它运输设备制造业 	1992-03-31
            'C38':True, # 电气机械及器材制造业 	1990-12-19
            'C39':False,# 计算机、通信和其他电子设备制造业 	1990-12-19
            'C40':False,# 仪器仪表制造业 	1993-09-17
            'C41':True, # 其他制造业 	1992-08-14
            'C42':False,# 废弃资源综合利用业 	2012-10-26
            'D44':True, # 电力、热力生产和供应业 	1993-04-16
            'D45':False,# 燃气生产和供应业 	2000-12-11
            'D46':False,# 水的生产和供应业 	1994-02-24
            'E47':True, # 房屋建筑业 	1993-04-29
            'E48':True, # 土木工程建筑业 	1994-01-28
            'E50':True, # 建筑装饰和其他建筑业 	1997-05-22
            'F51':False,# 批发业 	1992-05-06
            'F52':False,# 零售业 	1992-09-02
            'G53':True, # 铁路运输业 	1998-05-11
            'G54':True, # 道路运输业 	1991-01-14
            'G55':True, # 水上运输业 	1993-11-19
            'G56':True, # 航空运输业 	1997-11-05
            'G58':True, # 装卸搬运和运输代理业 	1993-05-05
            'G59':False,# 仓储业 	1996-06-14
            'H61':False,# 住宿业 	1993-11-18
            'H62':False,# 餐饮业 	1997-04-30
            'I63':False,# 电信、广播电视和卫星传输服务 	1992-12-02
            'I64':False,# 互联网和相关服务 	1992-05-07
            'I65':False,# 软件和信息技术服务业 	1992-08-20
            'J66':True, # 货币金融服务 	1991-04-03
            'J67':True, # 资本市场服务 	1994-01-10
            'J68':True, # 保险业 	2007-01-09
            'J69':True, # 其他金融业 	2012-10-26
            'K70':True, # 房地产业 	1992-01-13
            'L71':False,# 租赁业 	1997-01-30
            'L72':False,# 商务服务业 	1996-08-29
            'M73':False,# 研究和试验发展 	2012-10-26
            'M74':True, # 专业技术服务业 	2007-02-15
            'N77':False,# 生态保护和环境治理业 	2012-10-26
            'N78':False,# 公共设施管理业 	1992-08-07
            'P82':False,# 教育 	2012-10-26
            'Q83':False,# 卫生 	2007-02-05
            'R85':False,# 新闻和出版业 	1992-12-08
            'R86':False,# 广播、电视、电影和影视录音制作业 	1994-02-24
            'R87':False,# 文化艺术业 	2012-10-26
            'S90':False,# 综合 	1990-12-10
            }

        industry_list = []
        if cycle == True:
            for industry in list(industry_dict.keys()):
                if industry_dict[industry] == True:
                    industry_list.append(industry)
        elif cycle == False:
            for industry in list(industry_dict.keys()):
                if industry_dict[industry] == False:
                    industry_list.append(industry)
        else:
            industry_list = list(industry_dict.keys())

        return industry_list

    # 一级行业列表
    @staticmethod
    def fun_get_industry_levelI(industry=None):
        industry_dict = {
            'A':['A01', 'A02', 'A03', 'A04', 'A05'] #农、林、牧、渔业
            ,'B':['B06', 'B07', 'B08', 'B09', 'B11'] #采矿业
            ,'C':['C13', 'C14', 'C15', 'C17', 'C18', 'C19', 'C20', 'C21', 'C22', 'C23', 'C24', 'C25', 'C26', 'C27', 'C28', 'C29', 'C30', 'C31', 'C32',\
                'C33', 'C34', 'C35', 'C36', 'C37', 'C38', 'C39', 'C40', 'C41', 'C42'] #制造业
            ,'D':['D44', 'D45', 'D46'] #电力、热力、燃气及水生产和供应业
            ,'E':['E47', 'E48', 'E50'] #建筑业
            ,'F':['F51', 'F52'] #批发和零售业
            ,'G':['G53', 'G54', 'G55', 'G56', 'G58', 'G59']	#交通运输、仓储和邮政业
            ,'H':['H61', 'H62'] #住宿和餐饮业
            ,'I':['I63', 'I64', 'I65']	#信息传输、软件和信息技术服务业
            ,'J':['J66', 'J67', 'J68', 'J69']	#金融业
            ,'K':['K70']	#房地产业
            ,'L':['L71', 'L72']	#租赁和商务服务业
            ,'M':['M73', 'M74']	#科学研究和技术服务业
            ,'N':['N78']	#水利、环境和公共设施管理业
            #,'O':[] #居民服务、修理和其他服务业
            ,'P':['P82']	#教育
            ,'Q':['Q83']	#卫生和社会工作
            ,'R':['R85', 'R86', 'R87'] #文化、体育和娱乐业
            ,'S':['S90']	#综合
            }
        if industry:
            return industry_dict[industry]
        
        return industry_dict
    
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


class PeLib():
    
    @staticmethod
    def fun_get_ps(statsDate, deltamonth,stocks):
        statsDate = DateHelper.to_date(statsDate)
        statsDate = None if deltamonth ==0 else statsDate - dt.timedelta(30*deltamonth)
        __df = get_fundamentals(query(valuation.code, valuation.pe_ratio).filter(valuation.code.in_(stocks)), date = statsDate)
        __df.rename(columns={'pe_ratio':deltamonth}, inplace=True)
        return __df
    
    @staticmethod
    @log_time
    def _fun_get_last_ps_df(statsDate,stocks,cnt=48):
        df = None
        
        for i in range(cnt):
            df1 = PeLib.fun_get_ps(statsDate, i,stocks)
            if i == 0:
                df = df1
            
            if i > 0:
                df = df.merge(df1, on='code')
                
        df.index = list(df['code'])
        df = df.drop(['code'], axis=1)

        df = df.fillna(value=0, axis=0)
        
        return df
    
    @staticmethod
    @log_time
    def get_one_stock_nstd(stock,df):
        idx = df.index.get_loc(stock)
        s = df.iloc[idx,:]
        if s.min() <= 0:
            return None

        mean = s.mean()
        std = s.std()
        dict_nstd = {'code':stock,'idx':idx,'mean':mean,'std':std,'nstd':(s[0]-mean)/std}
        return dict_nstd
    
    @staticmethod
    def get_sorted_nstd(current_dt,stocks):
        df = PeLib._fun_get_last_ps_df(statsDate=current_dt,stocks=stocks)
        
        list_nstd = []
        for code in df.index:
            dict_nstd = PeLib.get_one_stock_nstd(code,df)
            if dict_nstd is None:
                continue
                
            list_nstd.append(dict_nstd)

        dict_score = sorted(list_nstd, key=lambda d:d['nstd'])
        return dict_score


# 用于缓存查询的ps数据。
class CacheDataFramePs:
    def __init__(self):
        self.df = None

    def __fun_get_ps(self,startDate):
        __df = get_fundamentals(query(valuation.code, valuation.ps_ratio), date = startDate)
        __df.rename(columns={'ps_ratio':str(DateHelper.to_date(startDate))}, inplace=True)
        return __df
    
    def append_cache_ps(self, current_dt,df=None):
        df1 = self.__fun_get_ps(current_dt)
        if df is not None:
            df = df.merge(df1, on='code')

        if df is None:
            df =df1

        return df

    def get_his_mon_ps(self, current_dt, df=None,num=48):
        for i in range(num):
            last_mon = current_dt - dt.timedelta(30*(num-i))
            df = self.append_cache_ps(last_mon,df)
        
        return df

    @log_time
    def get_curr_mon_ps(self, current_dt, df=None):
        df = self.append_cache_ps(current_dt,df)
        return df
    
    def init_last_48_ps(self, current_dt):
        self.df = self.get_his_mon_ps(current_dt)
        return self.df
    
    def has_curr_mon(self,current_dt):
        if self.df is None:
            return False
        
        last_mon_str = self.df.columns[-1]
        next_mon = DateHelper.add_ndays(last_mon_str,30)
        has_curr = DateHelper.date_is_after(next_mon, current_dt)
        log.info('current[%s] is already in curr mon[end:%s]? %s.'%(str(current_dt),str(next_mon),str(has_curr)))
        return has_curr
    
    def too_more(self, max_cols=49):
        if self.df is None:
            return False
        
        return len(self.df.columns) > max_cols
    
    def drop_first(self):
        # 0 code列 1 最早一列，前面初始化时是按时间序列排序的
        self.df.drop([self.df.columns[1]],axis=1,inplace=True) 
    
    @log_time
    def try_get_current_copy(self, current_dt):
        if self.df is None:
            self.df = self.init_last_48_ps(current_dt)
            self.df = self.get_curr_mon_ps(current_dt,self.df)
            return self.df.copy()
        
        if self.has_curr_mon(current_dt):
            return self.df.copy()
        
        self.df = self.get_curr_mon_ps(current_dt,self.df)

        if self.too_more():
            self.drop_first()
        
        return self.df.copy()

   
class QuantileWraper:
    def __init__(self):
        self.pe_pb_df = None
        self.quantile = None
        self.index_code = '000300.XSHG'

    def pretty_print(self,current_dt,ndays=2,years=7.5):
        if self.quantile is None:
            log.info('没有指数PE分位数据。')
            return
        
        import prettytable as pt
        
        tdy = DateHelper.to_date(current_dt)
    
        tb = pt.PrettyTable(["日期", "pe", "pb", "近" + str(years) + "年pe百分位高度"])
        for i in range(1, ndays+1):
            one_day = DateHelper.add_ndays(tdy,-i)
            one_day = self._get_before_quantile_day(one_day)
            one_quantile = None
            try:
                one_quantile = self.quantile.loc[one_day]
            except:
                log.info('未能取到日期[%s]数据'%(one_day))
            
            if one_quantile is None:
                continue
            
            tb.add_row([str(one_day), 
                        str(round(one_quantile['pe'],3)),
                        str(round(one_quantile['pb'],3)), 
                        str( round(one_quantile['quantile'],3))])
        index_name = get_security_info(self.index_code).display_name
        log.info('每日报告，' + index_name + '近'+ str(ndays)+'个交易日估值信息：\n' + str(tb))

    def get_one_day_index_pe_pb_media(self,index_code, date):
        stocks = get_index_stocks(index_code, date)
        q = query(valuation.pe_ratio, 
                valuation.pb_ratio
                ).filter(valuation.pe_ratio != None,
                        valuation.pb_ratio != None,
                        valuation.code.in_(stocks))
        df = get_fundamentals(q, date)
        quantile = df.quantile([0.1, 0.9])
        df_pe = df.pe_ratio[(df.pe_ratio > quantile.pe_ratio.values[0]) & (df.pe_ratio < quantile.pe_ratio.values[1])]
        df_pb = df.pb_ratio[(df.pb_ratio > quantile.pb_ratio.values[0]) & (df.pb_ratio < quantile.pb_ratio.values[1])]
        return date, df_pe.median(), df_pb.median()
    
    # 定义一个函数，计算每天的成份股的平均pe/pb
    @log_time
    def iter_pe_pb(self, index_code, start_date, end_date):
        from jqdata import get_trade_days
        print('iter_pe_pb index ',index_code,' start_date:',str(start_date),' end_date:',end_date)
        # 一个获取PE/PB的生成器
        trade_date = get_trade_days(start_date=start_date, end_date=end_date)   
        for date in trade_date:
            yield self.get_one_day_index_pe_pb_media(index_code, date)

    @log_time    
    def get_pe_pb(self, index_code, end_date,start_date=None, old_pe_pb=None):
        if start_date is None and old_pe_pb is not None:
            start_date = old_pe_pb.index[-1]
        
        info = get_security_info(index_code)
        if start_date is None or DateHelper.date_is_after(info.start_date,start_date):
            start_date = info.start_date
        
        if old_pe_pb is not None:
            last_day = old_pe_pb.index[-1]
            if DateHelper.date_is_after(last_day,start_date):
                start_date = last_day
            
        print('get_pe_pb:start:',start_date,' end:',end_date)
        if DateHelper.date_is_after(start_date,end_date):
            log.info('开始日期在结束日期之后，不需要取数据')
            return old_pe_pb
            
        dict_result = [{'date': str(value[0]), 'pe': value[1], 'pb':value[2]} for value in self.iter_pe_pb(index_code, start_date, end_date)]
        if len(dict_result) == 0:
            log.info('取得的数据为空。')
            return old_pe_pb
        
        df_result = pd.DataFrame(dict_result)
        df_result.set_index('date', inplace=True)

        if old_pe_pb is None:
            old_pe_pb = df_result
        else:
            old_pe_pb = pd.concat([old_pe_pb, df_result])

        return old_pe_pb

    ## pe近7年百分位位置计算
    @log_time
    def get_quantile(self, pe_pb_data, p='pe', n=7.5):
        """pe百分位计算。
        Args:
            p: 可以是 pe，也可以是 pb。
            n: 指用于计算指数估值百分位的区间，如果是5指近5年数据。
            pe_pb_data: 包含有 pe/pb 的 DataFrame。
        Returns:
            计算后的DataFrame。
        """
        _df = pe_pb_data.copy()
        windows = self._year_to_days(n)  # 将时间取整数
        if sys.version_info < (3,0):
            _df['quantile'] = pd.rolling_apply( _df[p],windows,lambda x: pd.Series(x).rank().iloc[-1] / 
                                                    pd.Series(x).shape[0])
        else:
            _df['quantile'] = _df[p].rolling(windows).apply(lambda x: pd.Series(x).rank().iloc[-1] / 
                                                    pd.Series(x).shape[0], raw=True)

        _df.dropna(inplace=True)
        _df = _df[~_df.index.duplicated()]
        
#         return _df.sort_index(inplace=True)
        return _df.sort_index()
    
    def _year_to_days(self, years):
        # 这里的计算按一年244个交易日计算
        return int(years * 244)
    
    @log_time
    def load_or_get_pe_pb_df(self,current_dt,start=None):
        if self.pe_pb_df is None:
            log.info('pe_pb_df数据为None，从文件导入。')
            self.pe_pb_df = self.load_from_cvs()
            
        self.pe_pb_df = self.get_pe_pb(index_code=self.index_code,end_date=current_dt,start_date=start, old_pe_pb=self.pe_pb_df)
        self.to_cvs()
        
        return self.pe_pb_df
    
    @log_time
    def init_last_years(self, current_dt, years=7.5, index_code='000300.XSHG'):
        start_date = DateHelper.add_ndays(current_dt,-2*self._year_to_days(years))
        self.pe_pb_df = self.load_or_get_pe_pb_df(current_dt,start_date)
        self.quantile = self.get_quantile(self.pe_pb_df,'pe',years)
        self.index_code = index_code
        return self.quantile
    
    def _get_before_quantile_day(self,one_day):
        def find(one_day,before_or_after=True,ndays=100):
            the_day = DateHelper.to_date(one_day)
            min_day = self.quantile.index.min()
            if DateHelper.date_is_after(min_day,the_day):
                # print('最小日期在指定日期之后，取最小日期')
                the_day = min_day
                return the_day

            # 一直往前找100天
            is_found = False
            for i in range(1,100):
                flag = -1 if before_or_after else 1
                the_day = DateHelper.add_ndays(the_day, flag*i)
                if type(min_day) == str:
                    the_day = str(the_day)

                if the_day in self.quantile.index:
                    log.info('指定日期[',the_day,']在索引中')
                    # log.info(self.quantile.loc[the_day])
                    is_found = True
                    break
            
            if not is_found:
                log.info('指定日期[%s]不在索引中'%(str(the_day)))
        
            return the_day if is_found else None
            
        
        the_day = find(one_day)
        if the_day is None:
            the_day = find(one_day, False)
        
        if the_day is None:
            the_day = self.quantile.index.min()
        
        log.info('find the day:',the_day)

        return the_day

    @log_time
    def try_get_today_quantile(self, current_dt, years=7.5, index_code='000300.XSHG'):
        if self.quantile is None:
            self.quantile = self.init_last_years(DateHelper.add_ndays(current_dt,-1),years,index_code)

        last_day = self.quantile.index[-1]

        if DateHelper.date_is_after(current_dt, last_day):
            self.pe_pb_df = self.load_or_get_pe_pb_df(current_dt)
            
            self.quantile = self.get_quantile(self.pe_pb_df,'pe',years)

        the_day = self._get_before_quantile_day(current_dt)
        return self.quantile.loc[the_day]['quantile']
    
    def to_cvs(self,file_name='df_pe_pb.cvs'):
        if self.pe_pb_df is not None:
            write_file(file_name, self.pe_pb_df.to_csv())
            
    @log_time
    def load_from_cvs(self,file_name='df_pe_pb.cvs'):
        from six import StringIO
        data = None
        try:
            body=read_file(file_name)
            data=pd.read_csv(StringIO(body))
            data.set_index('date', inplace=True)
            data.dropna(inplace=True)
        except:
            log.info('读取文件异常%s'%(str(e)))
            
        if data is None:
            log.info('未能读取文件数据[%s]'%(file_name))
            
        return data
    
    


class RiskLib:
    @staticmethod
    def __get_daily_returns(stock_or_list, freq, lag):
        hStocks = history(lag, freq, 'close', stock_or_list, df=True)
        if sys.version_info < (3,0):
            dailyReturns = hStocks.resample('D','last').pct_change().fillna(value=0, method=None, axis=0).values
        else:
            dailyReturns = hStocks.resample('D').last().pct_change().fillna(value=0, method=None, axis=0).values
    
        return dailyReturns
    
    @staticmethod
    def __level_to_probability(confidencelevel):
        # 正太分布标准差的倍数对应的分布概率
        a = (1 - 0.95)
        if confidencelevel == 1.96:
            a = (1 - 0.95)
        elif confidencelevel == 2.06:
            a = (1 - 0.96)
        elif confidencelevel == 2.18:
            a = (1 - 0.97)
        elif confidencelevel == 2.34:
            a = (1 - 0.98)
        elif confidencelevel == 2.58:
            a = (1 - 0.99)
        elif confidencelevel == 5:
            a = (1 - 0.99999)
        
        return a
    
    @staticmethod
    def calc_stock_ES(stock, a=0.05, freq='1d', lag=120):
        ES = 0
        fac = lag * a
        
        dailyReturns = RiskLib.__get_daily_returns(stock, freq, lag)
        dailyReturns_sort =  sorted(dailyReturns)
        
        count = 0
        sum_value = 0
        for i in range(len(dailyReturns_sort)):
            if i < fac:
                sum_value += dailyReturns_sort[i]
                count += 1
                
        if count > 0:
            ES = -(sum_value / fac)
            
        return ES[0]
    
    @staticmethod
    def calc_stock_VaR(stock,confidentLevel=1.96,freq='1d',lag=120):
        __portfolio_VaR = 0
    
        dailyReturns = RiskLib.__get_daily_returns(stock, freq, lag)
        __portfolio_VaR = 1 * confidentLevel * np.std(dailyReturns)
    
        return __portfolio_VaR
    
    @staticmethod
    def get_portfilo_ratio_ES(stocks,confidentLevel=1.96):
        es_stocks = []
        a = RiskLib.__level_to_probability(confidentLevel)
        for s in stocks:
            es = RiskLib.calc_stock_ES(s,a=a, freq='1d', lag=120)
            es_stocks.append(es)
        
        max_es = max(es_stocks)
        pos_stocks = list(max_es/np.array(es_stocks))
        
        total_positions = sum(pos_stocks)
        __ratio = {}
        
        for i in range(len(stocks)):
            stock = stocks[i]
            if stock not in __ratio:
                __ratio[stock] = 0
                
            ratio =  pos_stocks[i]/total_positions
            __ratio[stock] += ratio
        
        return __ratio
    
    @staticmethod
    def get_portfilo_ratio_Var(stocks,confidentLevel=1.96):
        var_stocks = []
        for s in stocks:
            vaR = RiskLib.calc_stock_VaR(s,confidentLevel=confidentLevel,freq='1d',lag=120)   
            var_stocks.append(vaR)
        
        max_var = max(var_stocks)
        pos_stocks = list(max_var/np.array(var_stocks))
        
        total_positions = sum(pos_stocks)
        __ratio = {}
        
        for i in range(len(stocks)):
            stock = stocks[i]
            if stock not in __ratio:
                __ratio[stock] = 0
                
            ratio =  pos_stocks[i]/total_positions
            __ratio[stock] += ratio
        
        return __ratio
    
    @staticmethod
    def get_portfilo_es(portfolio_ratios,confidentLevel=1.96):
        hStocks = history(1, '1d', 'close', list(portfolio_ratios.keys()), df=False)
        __portfolio_es = 0
        a = RiskLib.__level_to_probability(confidentLevel)
        for stock in portfolio_ratios:
            s_es = RiskLib.calc_stock_ES(stock, a=0.05, freq='1d', lag=120)  # 盈亏比率
            currVaR = hStocks[stock] * s_es # 每股盈亏 = 价格 × 比率
            perAmount = 1 * portfolio_ratios[stock] / hStocks[stock] # 每份钱按比例投到该股能买的股票数量
            __portfolio_es += perAmount * currVaR
        
        return __portfolio_es
    
    @staticmethod
    def get_portfilo_VaR(portfolio_ratios,confidentLevel=1.96):
        hStocks = history(1, '1d', 'close', list(portfolio_ratios.keys()), df=False)
        __portfolio_VaR = 0
        for stock in portfolio_ratios:
            s_vaR = RiskLib.calc_stock_VaR(stock,confidentLevel=confidentLevel,freq='1d',lag=120)  # 盈亏比率
            currVaR = hStocks[stock] * s_vaR # 每股盈亏 = 价格 × 比率
            perAmount = 1 * portfolio_ratios[stock] / hStocks[stock] # 每份前按比例投到该股能买的股票数量
            __portfolio_VaR += perAmount * currVaR
        
        return __portfolio_VaR
    
    @staticmethod
    def calc_portfilo_es_value_by_risk_money(risk_money,portfolio_ratios,confidentLevel=1.96):
        portfolio_es = RiskLib.get_portfilo_es(portfolio_ratios=portfolio_ratios,confidentLevel=confidentLevel)
        return risk_money/portfolio_es
    
    @staticmethod
    def calc_portfilo_var_value_by_risk_money(risk_money,portfolio_ratios,confidentLevel=1.96):
        portfolio_vaR = RiskLib.get_portfilo_VaR(portfolio_ratios=portfolio_ratios,confidentLevel=confidentLevel)
        return risk_money/portfolio_vaR

    @staticmethod
    def get_portfilo_ratio_ES_and_value(portfilo,total_money):
        portfilo_ratio = RiskLib.get_portfilo_ratio_ES(portfilo, g.confidentLevel)
        portfilo_VaR = RiskLib.get_portfilo_VaR(portfolio_ratios=portfilo_ratio,confidentLevel=g.confidentLevel)
        portfilo_es = RiskLib.get_portfilo_es(portfolio_ratios=portfilo_ratio,confidentLevel=g.confidentLevel)

        risk_money = total_money * g.risk

        vaR_value = RiskLib.calc_portfilo_var_value_by_risk_money(risk_money,portfilo_ratio,confidentLevel=g.confidentLevel)
        es_value = RiskLib.calc_portfilo_es_value_by_risk_money(risk_money*1.5,portfilo_ratio,confidentLevel=g.confidentLevel)
        risk_value = min(vaR_value,es_value)

        buy_value = min(risk_value,total_money)

        return portfilo_ratio, buy_value

    @classmethod
    def formula_risk(cls, quantile, rmax=0.08, rmin=0.005):
        # risk 以0为顶点，开口向下的抛物线，quantile>0.85后，取最小值
        q_mid = 0
        q_min = -0.85
        q_max = q_mid + q_mid - q_min
        # print('type of quantile:',type(quantile))
        if quantile > q_max:
            return rmin
    
        b = (rmax-rmin)/(q_max*q_max)
    
        return abs(rmax - b*quantile*quantile)
    
    @classmethod
    def ajust_risk(cls, context):
        # 根据当前PE的分位、当前盈亏，调整risk。
        quantile = g.quantile.try_get_today_quantile(context.current_dt)

        risk = cls.formula_risk(quantile,rmax=g.max_risk,rmin=g.min_risk)
        log.info('quantile[%f] rmax[%f] rmin[%f] new risk[%f]'%(quantile, g.max_risk,g.min_risk,risk))
        return risk
    
    @classmethod
    def risk_formula_by_stop(cls, nday, max_days=20):
        def formula(nday,max_days):
            a,b = 1,1
            if nday == 0:
                a = 2.0/3.0
                b = 1
                
            if nday > 0 and nday < max_days:
                a = 1
                b = 1.06
            
            if nday > max_days:
                a = 1
                b = 1
            
            ry = a * b
            return ry

        rate = formula(0, max_days)
        # log.info('第0天rate[%.3f]'%(rate))
        for i in range(1,nday+1):
            rate = rate * formula(i,max_days)
            # log.info('第[%d]天rate[%.3f]'%(i,rate))
        log.info('第[%d]天rate[%.3f]'%(nday,rate))
        return rate

    @classmethod
    def ajust_by_stop(cls,stopper,current_dt,risk,rmax=0.04,rmin=0.01, max_days=20):
        # 幂等性
        stop_stocks = stopper.get_latest_stopped_stocks(current_dt)
        
        rate = 1
        for s in stop_stocks:
            ndays = stopper.calc_stock_stopped_days(s,current_dt)
            rate = rate * cls.risk_formula_by_stop(ndays, max_days=max_days)
        
        risk = risk * rate
        if risk > rmax:
            risk = rmax
        
        if risk < rmin:
            risk = rmin

        log.info('new risk:%.3f'%(risk))
        return risk



class StopManager():
    # 1 是否止损 
    # 2 止损记录
    # 3 一段时间内不再购买
    # 4 按先后排序
    def __init__(self):
        self.stop_ratio = 0.1 # 跌10%止损
        self.stop_ndays = 20
        self.blacks = {}
        self.sorted_blacks = []
        self.high = {}  # 记录股票的高水线（最高价格）
        self.last_price = {} # 记录上次调仓卖出价格

    def check_stop(self,context):
        self.context = context

        for s in context.portfolio.positions:
            p = context.portfolio.positions[s]
            self.try_close(p)
    
    def try_close(self, p):
        self.record_high(p)
        
        # p:Position对象
        if self.is_stop(p,self.stop_ratio):
            # stop_price = (1-self.stop_ratio) * p.avg_cost
            # high = self.high[p.security]
            
            # # 移动止损
            # delta = high - p.avg_cost
            # if delta < 0: delta = 0
            
            # trail_price = stop_price + delta
            # trail_price = stop_price + (high - stop_price)/4
            trail_price = self._calc_trail(p,self.stop_ratio)
            balance = (p.price-trail_price)*p.total_amount
            log.info('股票[%s]发生止损[%f,%f,%f]。'%(p.security,p.price,trail_price,balance))
            order_target(p.security, 0)
            self.record(p.security,balance)
            self.remove_high(p.security)
            self.remove_last_price(p.security)
            
    
    def remove_high(self, security):
        if security not in self.high:
            return
        
        self.high.pop(security)
            
    def record_high(self, p):
        # 记录高水线-最高价格
        # 考虑到可能的除权等，决定采用价值/数量作为记录的价格
        if p.total_amount <= 0:
            # 应该不存在
            return 
        
        price = p.value / p.total_amount
        if p.security not in self.high:
            self.high[p.security] = price
            return
        
        last_price = self.high[p.security]
        if price > last_price:
            self.high[p.security] = price
        
    def _calc_trail(self,position,ratio):
        stop_price = (1-ratio) * position.avg_cost
        high = self.high[position.security]
        # 移动止损
        delta = high - position.avg_cost
        if delta < 0: delta = 0
        
        # 基本保持不动
        trail_price = stop_price + delta / 8
        
        # cover成本后慢速移动,留足空间
        # if trail_price > position.avg_cost:
        #     trail_price = stop_price + delta / 3
        
        log.info('debug is_stop:sec:%s, high:%.3f,cost:%.3f,trail_price:%.3f,stop:%.3f,curr_price:%.3f,ratio:%.3f'%(position.security,high,position.avg_cost,trail_price,stop_price,position.price,ratio))
        
        return trail_price
    
    def is_stop(self, position,ratio=0.08):
        trail_price = self._calc_trail(position,ratio)
        return position.price <= trail_price
    
    def is_lost(self, position):
        return self.is_stop(position,0)
    
    def record(self,sec,balance):
        # 记录sec,date
        self.blacks[sec] = (self.context.current_dt,balance)
        if sec in self.sorted_blacks:
            self.sorted_blacks.remove(sec)
        
        self.sorted_blacks.append(sec)
    
    def beyond_last_stop(self,stock,current_dt):
        import datetime
        stop_day,_ = self.blacks[stock]

        beyond_day = stop_day + datetime.timedelta(self.stop_ndays)

        log.info('当前日期：'+str(current_dt)+' 逾期日：'+str(beyond_day))
        
        return current_dt > beyond_day
    
    def sort_by_stop_time(self,stocks):
        sorted_stocks = []

        tmp_stocks = stocks[::]

        if len(tmp_stocks) == 0:
            return sorted_stocks

        for s in self.sorted_blacks:
            if s in tmp_stocks:
                sorted_stocks.append(s)
                tmp_stocks.remove(s)
            
            if len(tmp_stocks) == 0:
                break

        return sorted_stocks

    def filter_and_sort(self,stocks,current_dt):
        filted_stocks = []
        need_sort = []
        for s in stocks:
            if s not in self.blacks:
                filted_stocks.append(s)

            if s in self.blacks:
                log.info('股票[%s]发生过止损[%s]。'%(s,str(self.blacks[s])))
                if self.beyond_last_stop(s,current_dt):
                    need_sort.append(s)
                
        sorted_stocks = self.sort_by_stop_time(need_sort)

        return filted_stocks + sorted_stocks

    def get_latest_stopped_stocks(self, current_dt, max_days=20):
        latest_stoped = []
        for s in self.blacks:
            _,bal = self.blacks[s]
            if bal > 0:
                # 没有亏损的平仓不算真正的止损
                continue
            
            if self.calc_stock_stopped_days(s, current_dt) <= max_days:
                latest_stoped.append(s)

        return latest_stoped
    
    def calc_stock_stopped_days(self,stock,current_dt):
        return DateHelper.days_between(current_dt, self.blacks[stock][0])

    def record_last_price(self,sec,price):
        self.last_price[sec] = price

    def get_last_price(self,sec):
        if sec in self.last_price:
            return self.last_price[sec]
        
        return None
    
    def remove_last_price(self,sec):
        if sec in self.last_price:
            self.last_price.pop(sec)
            
    
    def get_last_price_cnt(self):
        return len(self.last_price)
        
    def is_in_last_price(self,sec):
        return sec in self.last_price
            
    
            
            
            

import numpy as np
import scipy.optimize as sco

class PortfolioMng():
    def __init__(self):
        self._tar_ret = 0.2
    
    def __random_weights(self,cnt=9):
        weights = np.random.random(cnt)
        weights /= np.sum(weights)
        return weights
    
    def __get_daily_returns(self,stock_or_list, freq='1d', lag=252):
        hStocks = history(lag, freq, 'close', stock_or_list, df=True)
        if sys.version_info < (3,0):
            dailyReturns = hStocks.resample('D','last').pct_change().fillna(value=0, method=None, axis=0)
        else:
            dailyReturns = hStocks.resample('D').last().pct_change().fillna(value=0, method=None, axis=0)
    
        return dailyReturns
    
    def __calc_expeired_year_rt(self,stocks_ret,weights):
        rt_mean = stocks_ret.mean()
        expeired_year_rt = np.dot(weights, rt_mean)*252
        return expeired_year_rt

    def __calc_exeired_var(self,stocks_ret,weights):
        cov = stocks_ret.cov()
        return np.dot(weights.T, np.dot(cov*252, weights))

    def __calc_expired_sqrt(self,stocks_ret,weights):
        var = self.__calc_exeired_var(stocks_ret,weights)
        return np.sqrt(var)
    
    
    def stats(self,weights):
        weights = np.array(weights)
        port_returns = np.sum(self.__calc_expeired_year_rt(self.__stocks_retn,weights))
        port_variance = self.__calc_expired_sqrt(self.__stocks_retn,weights)
        return np.array([port_returns, port_variance, port_returns/port_variance])

    #最小化夏普指数的负值
    def min_sharpe(self,weights):
        return -self.stats(weights)[2]
    
    def min_variance(self,weights):
        return self.stats(weights)[1]
    
    def _get_minimize_opt(self,cnt,name='sharp'):
        #给定初始权重
        x0 = self.__random_weights(cnt)

        #权重（某股票持仓比例）限制在0和1之间。
        bnds = tuple((0,1) for x in range(cnt))
        # _tar_ret
        # 给定收益率20、权重（股票持仓比例）的总和为1。
        cons = ({'type':'eq','fun':lambda x:self.stats(x)[0]-self._tar_ret},{'type':'eq','fun':lambda x:np.sum(x)-1})
        # cons = ({'type':'eq', 'fun':lambda x: np.sum(x)-1})

        min_func = self.min_sharpe if name=='sharp' else self.min_variance
        #优化函数调用中忽略的唯一输入是起始参数列表(对权重的初始猜测)。我们简单的使用平均分布。
        opts = sco.minimize(min_func,
                            x0,
                            method = 'SLSQP', 
                            bounds = bnds, 
                            constraints = cons)
        return opts

    @log_time
    def get_portfolio_weights(self,stocks,min_name='sharp'):
        cnt = len(stocks)
        
        if not hasattr(self,'__stocks_retn') or self.__stocks_retn is None:
            self.__stocks_retn = self.__get_daily_returns(stocks)
            cov = self.__stocks_retn.cov()
            print('cov:',cov)
            corr = self.__stocks_retn.corr()
            print('corr:',corr)

        
        opt = self._get_minimize_opt(cnt,min_name)
        
        
        return opt['x'].round(4)
    
    def sort_by_corr(self,stocks):
        self.__stocks_retn = self.__get_daily_returns(stocks)
        corr = self.__stocks_retn.corr()

        corr['Col_sum'] = corr.apply(lambda x: x.abs().sum(), axis=1)
        if sys.version_info < (3,0):
            corr = corr.sort('Col_sum',ascending=True)
        else:
            corr = corr.sort_values('Col_sum', ascending=True)


        return corr.index


class TimingFactorLib():
    def __init__(self):
        pass
    
    @classmethod
    def ma_5_bigger_10_filter(cls,stocks):
        final_stocks = [s for s in stocks if cls.is_ma_5_bigger_10(s)]
        return final_stocks
    
    @classmethod
    def is_ma_5_bigger_10(cls,security):
        # 5日均线>10日均线
        close_data = attribute_history(security, 10, '1d', ['close'])
        # 取得过去五天的平均价格
        MA10 = close_data['close'].mean()
        MA5 = close_data['close'][-5:].mean()
        log.info('debug:is_ma_5_bigger_10:security:%s,MA5:%f,MA10:%f'%(security,MA5,MA10))
        return MA5 > MA10

    @classmethod
    def is_ma_bigger_5_10_20_30(cls,security):
        # 5日均线>10日均线
        close_data = attribute_history(security, 30, '1d', ['close'])
        # 取得过去五天的平均价格
        MA30 = close_data['close'].mean()
        MA20 = close_data['close'][-20:].mean()
        MA10 = close_data['close'][-10:].mean()
        MA5 = close_data['close'][-5:].mean()
        log.info('debug:is_ma_bigger_5_10_20_30:security:%s,MA5:%.3f,MA10:%.3f,MA20:%.3f,MA30:%.3f'%(security,MA5,MA10,MA20,MA30))
        if MA5 < MA10:
            log.info('股票[%s]5日均线没在10日均线上'%(security))
            return False
        
        if MA20 < MA30:
            log.info('股票[%s]20日均线没在30日均线上'%(security))
            return False

        return True
    
    @classmethod
    def is_ma_30_grow(cls,security):
        close_data = attribute_history(security, 40, '1d', ['close'])
        MA30 = close_data['close'][-30:].mean()
        MA302 = close_data['close'][-32:-2].mean()
        
        if MA30 <= MA302:
            log.info('股票[%s]30日均线没往上走!'%(security))
            return False

        return True
        
    
    @classmethod
    def filter_by_in_low(cls,stocks):
        #输入股票列表，剔除股票价格不在历史低点
        buy_stocks = []
        data = history(300, '1d', 'close', stocks, df=False)
        for stock in stocks:
            minpr = data[stock].min()
            if(data[stock][-1]<minpr*1.1):
                buy_stocks.append(stock)
        
        return buy_stocks
    
    



# 导入函数库
import statsmodels.api as sm
import random

class RsPair(dict):
    def __init__(self,ans=[],r2s=[],date='2005-01-01'):
            self.ans = ans
            self.r2s = r2s
            self.date = date
    
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'RsPair' object has no attribute '%s'" % key)
    
    def __setattr__(self, key, value):
        import datetime
        if isinstance(value,datetime.date):
            value = str(value)
        self[key] = value

class RSRSLib():
    def __init__(self,buy_ratio=0.7,sell_ratio=-0.7):
        self.rsrses = {}
        self.buy = buy_ratio
        self.sell = sell_ratio

    def to_file(self,path='history_rsrs.json'):
        write_file(path, str(self.rsrses))

    def load_rsrs_from(self,path='history_rsrs.json'):
        self.rsrses = {}
        try:
            data = read_file(path)
            str_data = str(data,'utf-8')
            str_data = str_data.replace("'", '"')
            dict_data= json.loads(str_data)
            rsrses = {}
            for d in dict_data:
                rs = RsPair(**dict_data[d])
                rsrses[d] = rs
            self.rsrses = rsrses
        except Exception as e:
            log.info('加载rsrs文件失败。'+str(e))
        
        
    
    @staticmethod
    def rsrs(prices):
        highs = prices.high
        lows = prices.low
        X = sm.add_constant(lows)
        model = sm.OLS(highs, X)
        fit = model.fit()
        # print('fit params:',fit.params)
        beta = fit.params.low
        #计算r2
        r2=fit.rsquared
        return beta,r2
    
    def calc_rsrs_last(self,prices,N=18):
        ans = []
        r2s = []
        for i in range(len(prices))[N:]:
            parts = prices.iloc[i-N+1:i+1]
            beta,r2 = self.rsrs(parts)
            
            ans.append(beta)
            #计算r2
            r2s.append(r2)
        return ans,r2s
    
    def calc_zscore_rightdev(self,section,beta,r2):
        # 计算均值序列
        mu = np.mean(section)
        # 计算标准化RSRS指标序列
        sigma = np.std(section)
        zscore = (section[-1]-mu)/sigma  
        #计算右偏RSRS标准分
        zscore_rightdev= zscore*beta*r2
        
        return zscore_rightdev
    
    def calc_sec_rsrs_from(self,security,begin='2005-01-05',end=None, N=18):
        log.info('计算'+str(begin)+'日至'+str(end)+'日的RSRS斜率指标')
        if str(begin) >= str(end):
            return None,None
        
        prices = get_price(security, begin, end, '1d', ['high', 'low'])
        size = len(prices.dropna())
        if size > 0:
            return self.calc_rsrs_last(prices.dropna(),N)
        
        return None,None
    
    def init_sec_rsrs(self,sec,end_date):
        log.info('init sec rsrs[%s].'%(sec))
        if sec in self.rsrses:
            rs = RsPair(**self.rsrses[sec])
        else:
            rs = RsPair()
            self.rsrses[sec] = rs
        # 计算2005年1月5日至回测开始日期的RSRS斜率指标
        ans,ans_rightdev = self.calc_sec_rsrs_from(sec, rs['date'], end_date)
        if ans and ans_rightdev:
            self.rsrses[sec] = RsPair(ans=ans,r2s=ans_rightdev,date=end_date)
    
        
    def is_sec_buy_or_sell(self,sec,N=18,M=1100):
        prices = attribute_history(sec, N, '1d', ['high', 'low'])
        if len(prices.dropna()) == 0:
            log.info('no data for sec'+sec)
            return 'n'
            
        beta, r2 = self.rsrs(prices.dropna())
        
        # edited@2022.8.19 清理多余数据,避免占用存储过大
        if len(self.rsrses[sec].ans) > 2*M:
            cp_ans = self.rsrses[sec].ans[-(M+N):]
            cp_r2s = self.rsrses[sec].r2s[-(M+N):]
            self.rsrses[sec].ans = cp_ans
            self.rsrses[sec].r2s = cp_r2s
            
        self.rsrses[sec].ans.append(beta)
        self.rsrses[sec].r2s.append(r2)
        
        section = self.rsrses[sec].ans[-M:]
        zscore_rightdev = self.calc_zscore_rightdev(section,beta,r2)
        
    
        # 如果上一时间点的RSRS斜率大于买入阈值, 则全仓买入
        if zscore_rightdev > self.buy:
            # 记录这次买入
            log.info("标准化RSRS斜率[%f]大于买入阈值, 买入 %s" % (zscore_rightdev,sec))
            # 用所有 cash 买入股票
            return 'b'
        # 如果上一时间点的RSRS斜率小于卖出阈值, 则空仓卖出
        if zscore_rightdev < self.sell:
            # 记录这次卖出
            log.info("标准化RSRS斜率[%f]小于卖出阈值, 卖出 %s" % (zscore_rightdev,sec))
            # 卖出所有股票,使这只股票的最终持有量为0
            return 's'
        
        log.info("股票[%s]标准化RSRS斜率[%f]中性。" % (sec,zscore_rightdev))
        return 'n'   # 不处理
    
    def is_hs300_buy(self):
        return self.is_sec_buy_or_sell('000300.XSHG') == 'b'
    
    def judge_today_buy_or_sell(self,sec,now_date,N=18,M=1100):
        self.init_sec_rsrs(sec,now_date)
        return self.is_sec_buy_or_sell(sec,N,M)
    
    def is_hs300_buy_tdy(self,now_date):
        return self.judge_today_buy_or_sell('000300.XSHG',now_date) == 'b'

    def is_tdy_buy(self,sec,now_date):
        return self.judge_today_buy_or_sell(sec,now_date) == 'b'


class TradeStrategy():
    def __init__(self, context):
        self.context = context
        log.info('初始化执行策略：等权买入')

    def buy(self,buys):
        log.info('执行策略：等权买入')
        # 等权买入
        if len(buys) == 0:
            return

        total = self.context.portfolio.total_value

        cost = total/len(buys)
        for s in buys:
            order_target_value(s, cost)


class TradeStrategyHL():
    ''' 
    每涨50%，减仓10%，向下取整
    每跌50%，加仓一倍，向上取整
    '''
    def __init__(self,context):
        # super(TradeStrategyHL, self).__init__(context)
        self.context = context
        self.max_num = g.stock_num
        self.stopper = g.stopper

        log.info('初始化执行策略：HL')


    
    def buy(self,buys,cnt_need_buys=0):
        log.info('执行策略：HL')
        if len(buys) == 0:return

        total = self.context.portfolio.available_cash
        # edited@2022-10-31 修复bug，cost应该为可用/待买数量（待买数量不含已卖出一半任然持仓的部分）
        cost = total/cnt_need_buys if cnt_need_buys > 0 else 0
        # 每次只建仓3层，等待后续加仓。
        cost = cost/3
        
        holds = list(self.context.portfolio.positions.keys())
        
        def __ajust_holds(holds):
            for h in holds:
                self.__ajust(h)
                
        # 处理持仓
        __ajust_holds(holds)
        
        for sec in buys:
            if sec in holds:
                # self.__ajust(sec)
                continue
            
            # 过滤恒瑞
            # if sec =="600276.XSHG":continue

            if not g.rsrslib.is_tdy_buy(sec,self.context.previous_date):
                log.info('rsrs判断%s均线不是多头，不交易。'%(sec))
                continue

            order_target_value(sec, cost)
            # self.__record_last_price(sec)

    def check_for_sell(self):
        if len(list(self.context.portfolio.positions.keys())) <= 0:
            log.info("没有持仓，无需平仓。")
            return

        # 检查止损
        g.stopper.check_stop(self.context)
        
    def check_for_bad_holds(self):
        holds = list(self.context.portfolio.positions.keys())

        can_hold_stocks = ValueLib.filter_for_sell(holds, self.context.current_dt)

        log.info('can hold stocks:')
        BzUtil.print_with_name(can_hold_stocks)
        
        bad_holds = [s for s in holds if s not in can_hold_stocks]
        log.info('bad_holds:')
        BzUtil.print_with_name(bad_holds)

        if len(bad_holds) > 0:
            log.info('下列股票在不好的股票里面，将清空。')
            BzUtil.print_with_name(bad_holds)
            for s in bad_holds:
                p = self.context.portfolio.positions[s]
                if p.price < p.avg_cost * 0.9:
                    # 亏损超过20%暂时不平仓
                    log.info('亏损超过10点，暂时不平仓：%s,price:%f avg_cost:%f'%(p.security, p.price, p.avg_cost))
                    continue

                order_target(s, 0)
                g.stopper.remove_last_price(s)


    def __ajust(self,sec):
        # 每涨50%，减仓10%;每跌50%，加仓50%;
        # edited@2022.8.19 每涨50，卖出20%
        p = self.context.portfolio.positions[sec]
        total = self.context.portfolio.total_value
        max_cost =  total / self.max_num
        last_price = self.stopper.get_last_price(sec)
        # 第一次不记录，以成本作为上一次的价格
        if last_price is None:
            last_price = p.avg_cost

        log.info('sec:%s,last:%f curr:%.3f'%(sec,last_price,p.price)) 
        if p.price > 2 * last_price:
            # 涨1倍卖50%
            log.info('sec:%s涨幅超一倍，卖出一半(%d)。last:%.3f curr:%.3f avg:%.3f'%(sec,p.closeable_amount/2,last_price,p.price,p.avg_cost)) 
            if p.closeable_amount <= 100:
                order_target_value(sec, 0)
                self.stopper.remove_last_price(sec)
                return
            
            order_target_value(sec, p.value *0.5)
            # self.stopper.record_last_price(sec,p.price)
            self.__record_last_price(sec)
            return
        # edited@2022-11-1 每跌50点，加仓一倍。直到触发止损
        if p.price <= 0.5 * p.avg_cost:
            log.info('sec:%s跌幅超50，买入一倍(%d)。last:%.3f curr:%.3f avg:%.3f'%(sec,p.closeable_amount,last_price,p.price,p.avg_cost)) 
            cost = min(max_cost,p.value * 2)
            order_target_value(sec, cost)
            # self.__record_last_price(sec)
            
        # if p.price > 1.5 * last_price:
        #     if p.closeable_amount <= 100:
        #         order_target(sec, 0)
        #         return
            
        #     order_target_value(sec, p.value *0.8)
        #     self.__record_last_price(sec)
        #     return
        
        
        
    def __record_last_price(self,sec):
        p = self.context.portfolio.positions[sec]
        self.stopper.record_last_price(sec,p.price)
        
            


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
    

    def market_open(self):
        self.strategy.check_for_sell()

        if self.positions_num() >= g.stock_num + g.stopper.get_last_price_cnt():
            log.info('持仓数量大于限仓数量，只调仓不开仓。')
            buys = list(self.context.portfolio.positions.keys())
            self.strategy.buy(buys)  
            return
        
        if DateHelper.to_date(self.context.current_dt).day >= 25:
            log.info('社区神定律，每月25号之后不交易')
            return

        # if not TimingFactorLib.is_ma_bigger_5_10_20_30('000300.XSHG'):
        #     log.info('大盘均线不是多头，不交易。')
        #     return

        if not g.rsrslib.is_tdy_buy('000300.XSHG',self.context.previous_date):
            log.info('rsrs判断大盘均线不是多头，不交易。')
            return
        
        self.check_for_buy()

    
    
    
    def choose_buy_stocks(self, context):
        buys = []

        hold_stock = list(context.portfolio.positions.keys())
        
        for s in hold_stock:
            buys.append(s)  # 持有的仓位继续持有
        
        still_need_buys_num = g.stock_num + g.stopper.get_last_price_cnt() -len(buys)

        log.info('目前持有股票数量[%d],还需再选[%d]。'%(len(buys), still_need_buys_num))

        still_need_buys = []
        if still_need_buys_num > 0:
            g.stocks = self.get_sorted_stocks_for_buy(context)
            # edited@2022.8.22 增加处于历史低点的过滤
            # cnt = len(g.stocks)
            # g.stocks = TimingFactorLib.filter_by_in_low(g.stocks)
            
            # delta = cnt - len(g.stocks)
            # log.info('历史低值条件过滤掉数量[%d],过滤前备选数量[%d]。'%(delta, cnt))
            
            
            for s in g.stocks:
                if len(still_need_buys) >= still_need_buys_num:
                    break

                if s in hold_stock:
                    continue

                # if not TimingFactorLib.is_ma_bigger_5_10_20_30(s):
                #     continue

                # if not TimingFactorLib.is_ma_30_grow(s):
                #     continue
                if not g.rsrslib.is_tdy_buy(s,context.previous_date):
                    log.info('rsrs判断%s均线不是多头，不交易。'%(s))
                    continue

                still_need_buys.append(s)
            
            log.info('额外选出股票：')
            BzUtil.print_with_name(still_need_buys)
            
        return buys + still_need_buys,still_need_buys_num
    
    
    # 策部略选股买卖分    
    def check_for_buy(self):
        if self.positions_num() >= g.stock_num + g.stopper.get_last_price_cnt():
            log.info('持仓数量大于等于最大允许持仓数量，不新增仓位。')
            return
        
        # 买入股票
        buys,cnt_need_buys = self.choose_buy_stocks(self.context)
        log.info('总共选出%s只股票'%len(buys))

        if len(buys) <= 0:
            return
        
        self.strategy.buy(buys,cnt_need_buys)

    
    def get_sorted_stocks_for_buy(self,context):
        temp_list = ValueLib.filter_stocks_for_buy(context.current_dt)
        log.info('满足条件的股票有%s只' % len(temp_list))
        
        g.stocks = g.stopper.filter_and_sort(temp_list, context.current_dt)
        # pm = PortfolioMng()
        # g.stocks = pm.sort_by_corr(g.stocks)

        return g.stocks

    
    def run_year(self):
        # 每年9月份，半年报基本发布完成，清理一次不好的股票
        current_day = DateHelper.to_date(self.context.current_dt)
        if  current_day.month == 9:
            self.strategy.check_for_bad_holds()


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
    check_out_lists = prepare_stock_list(context)
    
    # check_out_lists = get_recent_limit_up_stock(context, check_out_lists, 5)
    # # check_out_lists = get_recent_limit_up_lt_stock(context,check_out_lists,1,5)
    # log.info("近5日涨停过滤:%d"%(len(check_out_lists)))
    
    # check_out_lists = filter_limitdown_stock(context, check_out_lists)
    # check_out_lists = get_available_price_stock(context, check_out_lists, 50, 1.2, 1.4, -0.05)
    # check_out_lists = get_available_volume_stock(context, check_out_lists, 5, 1.8)
    # check_out_lists = get_available_auction_stock(context, check_out_lists, 1.05)
    log.info("最终选出股票数量:%d"%(len(check_out_lists)))
    
    # if len(check_out_lists)>g.buy_stock_count:
    #     check_out_lists = check_out_lists[:g.buy_stock_count]
        
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
        # 每年10月调整一次持仓
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

    # 每月第5个交易日进行操作
    # 开盘前运行

    # run_monthly(adjust_risk_before_market_open, 5, time='before_open',
    #             reference_security='000300.XSHG')
    # # 开盘时运行
    # run_monthly(market_open, 5, time='open', reference_security='000300.XSHG')
    
    # run_daily(before_market_open,time='9:00', reference_security='000300.XSHG')
    # run_daily(market_open, time='10:30', reference_security='000300.XSHG')

    # run_daily(check_stop_at_noon, time='14:30', reference_security='000300.XSHG')

    # # run_daily(before_market_open, time='before_open', reference_security='000300.XSHG') 
    #   # 开盘时运行
    # # run_daily(check_sell_when_market_open, time='9:30', reference_security='000300.XSHG')

    # run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')

    # run_monthly(year_run_for_bad, 5, time='open', reference_security='000300.XSHG')
    
    run_daily(market_open, time='10:00', reference_security='000300.XSHG')
    run_monthly(monthly_adjust, 5, time='14:30', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')


# 开盘前运行函数
def before_market_open(context):
    pass
    # 获取要操作的股票列表
    # temp_list = filter_stocks_for_buy(context)

    # 获取满足条件的股票列表
    # temp_list = ValueLib.filter_stocks_for_buy(context.current_dt)
    # log.info('满足条件的股票有%s只' % len(temp_list))
    # # 按市值进行排序
    # g.stocks = get_check_stocks_sort_by_cap(context, temp_list)
    # g.stocks = g.stopper.filter_and_sort(g.stocks, context.current_dt)
    # g.stocks = BzUtil.filter_without(g.buy_list,['600276.XSHG']) # 去掉恒瑞

    # g.risk = RiskLib.ajust_by_stop(g.stopper,context.current_dt,g.risk,rmax=g.max_risk, rmin=g.min_risk,max_days=g.stopper.stop_ndays)

# 开盘时运行函数


# def market_open(context):
#     log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
#     trader = Trader(context,TradeStrategyHL(context))
#     trader.market_open()


# def after_market_close(context):
#     Trader.print_holdings(context)
#     g.panel = None

#     # if hasattr(g,'quantile') and g.quantile is not None:
#     #     g.quantile.pretty_print(context.current_dt,2,g.quantile_long)



def adjust_risk_before_market_open(context):
    pass
#     if not hasattr(g,'quantile') or g.quantile is None:
#         g.quantile = QuantileWraper()
#         g.quantile.init_last_years(context.current_dt, years=g.quantile_long)

#     g.risk = RiskLib.ajust_risk(context)
    

def check_stop_at_noon(context):
    pass
#     g.stopper.check_stop(context)


# def year_run_for_bad(context):
#     trader = Trader(context,TradeStrategyHL(context))
#     trader.run_year()
    
    


@log_time
def after_code_changed(context):
    g.stock_num = 4
    
    # g.weights = [1.0, 1.0, 1.6, 0.8, 2.0]
 
    g.stocks = None
    
    g.stopper = StopManager()
    g.stopper.stop_ratio = 0.80 # 跌8%止损,考虑移动止损，10%差不多对应8%
    g.stopper.stop_ndays = 80

    # 风险敞口的最大最小值
    g.risk = 0.03 # 风险敞口
    g.max_risk, g.min_risk = 0.04,0.01
    g.confidentLevel = 1.96

    g.quantile_long = 7.5 # 检查的pe分位的年数

    g.quantile = None

    log.info('begin to init rsrses...')
    g.rsrslib = RSRSLib()
    g.rsrslib.init_sec_rsrs('000300.XSHG',context.previous_date)
    
    g.trader = NetPositionManager(g.stock_num,get_buy_stocks)