# author:linbirg
# 2019-09-04
# 本身存在的问题：
# 1 fisher财务因子
# 2 roe选股
# 3 行业过滤


import pandas as pd
import datetime as dt
from jqdata import get_trade_days

def log_time(f):
    import time
    def decorater(*args,**kw):
        now = time.time() * 1000
        ret = f(*args,**kw)
        delta = time.time() * 1000 - now
        log.info('函数[%s]用时[%d]'%(f.__name__,delta))
        return ret
    
    return decorater
    

class FileHelper:
    @staticmethod
    def dict_to_file(dict_data,path='history_rsrs.json'):
        write_file(path, str(dict_data))

    @staticmethod
    def load_dict_from(path='history_rsrs.json'):
        import json
        try:
            data = read_file(path)
            str_data = str(data,'utf-8')
            str_data = str_data.replace("'", '"')
            dict_data= json.loads(str_data)
            return dict_data
        except Exception as e:
            log.info('加载文件失败。'+str(e))

class DateHelper:
    @classmethod
    def to_date(cls,one):
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
        # print('one[%s] after other[%s]? [%s]'%(str(one_date),str(other_date),str(is_after)))
        return is_after

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
        elif type == 3: #Boxplot 去极值
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
    
    @staticmethod
    def unpaused(stock_list):
        current_data = get_current_data()
        tmpList = []
        for stock in stock_list:
            if not current_data[stock].paused:
#             or stock in positions_list:
                tmpList.append(stock)
        return tmpList

    @staticmethod
    def remove_st(stock_list, statsDate):
        current_data = get_current_data()
        return [s for s in stock_list if not current_data[s].is_st]

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
        q = query(indicator.code)
        df = get_fundamentals(q, date=startDate)
        return list(df['code'])

    @classmethod
    def print_with_name(cls, stocks):
        for s in stocks:
            info = get_security_info(s)
            log.info(info.code,info.display_name)
        

class QuantLib():
    @classmethod
    def get_fundamentals_sum(cls, table_name=indicator, search=indicator.adjusted_profit, statsDate=None):
        # 取最近的五个季度财报的日期
        def __get_quarter(table_name, statsDate):
            '''
            返回最近 n 个财报的日期
            返回每个股票最近一个财报的日期
            '''
            # 取最新一季度的统计日期
            if table_name == 'indicator':
                q = query(indicator.code, indicator.statDate)
            elif table_name == 'income':
                q = query(income.code, income.statDate)
            elif table_name == 'cash_flow':
                q = query(cash_flow.code, cash_flow.statDate)
            elif table_name == 'balance':
                q = query(balance.code, balance.statDate)

            df = get_fundamentals(q, date = statsDate)
            stock_last_statDate = {}
            tmpDict = df.to_dict()
            for i in range(len(list(tmpDict['statDate'].keys()))):
                # 取得每个股票的代码，以及最新的财报发布日
                stock_last_statDate[tmpDict['code'][i]] = tmpDict['statDate'][i]

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
        def __get_fundamentals_value(table_name, search, myDate):
            '''
            输入查询日期
            返回指定的财务数据，格式 dict
            '''
            if table_name == 'indicator':
                q = query(indicator.code, search, indicator.statDate) 
            elif table_name == 'income':
                q = query(income.code, search, income.statDate)
            elif table_name == 'cash_flow':
                q = query(cash_flow.code, search, cash_flow.statDate)
            elif table_name == 'balance':
                q = query(balance.code, search, balance.statDate)

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
    
        last_quarter_dict       = __get_fundamentals_value(table_name, search, last_quarter)
        last_two_quarter_dict   = __get_fundamentals_value(table_name, search, last_two_quarter)
        last_three_quarter_dict = __get_fundamentals_value(table_name, search, last_three_quarter)
        last_four_quarter_dict  = __get_fundamentals_value(table_name, search, last_four_quarter)
        last_five_quarter_dict  = __get_fundamentals_value(table_name, search, last_five_quarter)

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
    def fun_get_factor(cls, df, factor_name, industry, level, statsDate):
        stock_list = BzUtil.fun_get_industry_stocks(industry, level, statsDate)
        rs = BzUtil.fun_neutralize(stock_list, df, module=factor_name, industry_type=industry, level=level, statsDate=statsDate)
        rs = BzUtil.fun_standardize(rs, 2)

        return rs

    @classmethod
    def fun_diversity_by_industry(cls, stock_list, max_num, statsDate):
        if stock_list is None:
            return None

        industry_list = BzUtil.fun_get_industry(cycle=None)
        tmpList = []
        for industry in industry_list:
            i = 0
            stocks = BzUtil.fun_get_industry_stocks(industry, 2, statsDate)
            for stock in stock_list:
                if stock in stocks: #by 行业选入 top max_num 的标的（如有）
                    i += 1
                    if i <= max_num:
                        tmpList.append(stock) #可能一个股票横跨多个行业，会导致多次入选，但不影响后面计算
        final_stocks = []
        for stock in stock_list:
            if stock in tmpList:
                final_stocks.append(stock)
        return final_stocks

    @classmethod
    def fun_get_bad_stock_list(cls, statsDate):
        #0、剔除商誉占比 > 30% 的股票
        df = get_fundamentals(
            query(valuation.code, balance.good_will, balance.equities_parent_company_owners),
            date = statsDate
        )

        df = df.fillna(value = 0)
        df['good_will_ratio'] = 1.0*df['good_will'] / df['equities_parent_company_owners']
        list_good_will = list(df[df.good_will_ratio > 0.3].code)

        bad_stocks = list_good_will
        bad_stocks = list(set(bad_stocks))
        return bad_stocks

    @staticmethod
    def get_inc_net_profile(statsDate):
        # 取净利润增长率为正的
        df = QuantLib.get_fundamentals_sum('income', income.net_profit, statsDate)
        df = df.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df.rename(columns={'sum_value':'ttm_1y'}, inplace=True)
        df1 = QuantLib.get_fundamentals_sum('income', income.net_profit, (statsDate - dt.timedelta(365)))
        df1 = df1.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df1.rename(columns={'sum_value':'ttm_2y'}, inplace=True)

        df = df.merge(df1, on='code')
        df = df.fillna(value=0)
        df['inc_net_profit'] = 1.0*(df['ttm_1y'] - df['ttm_2y'])
        df = df[df.inc_net_profit > 0]
        inc_net_profit_list = list(df.code)
        return inc_net_profit_list

    @staticmethod
    def get_inc_operating_revenue_list(statsDate):
        # 按行业取营业收入增长率前 1/3
        df = QuantLib.get_fundamentals_sum('income', income.operating_revenue, statsDate)
        df = df.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df.rename(columns={'sum_value':'ttm_1y'}, inplace=True)
        df1 = QuantLib.get_fundamentals_sum('income', income.operating_revenue, (statsDate - dt.timedelta(365)))
        df1 = df1.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df1.rename(columns={'sum_value':'ttm_2y'}, inplace=True)

        df = df.merge(df1, on='code')
        df = df.fillna(value=0)
        df['inc_operating_revenue'] = 1.0*(df['ttm_1y'] - df['ttm_2y']) / abs(df['ttm_2y'])

        df = df.fillna(value = 0)
        industry_list = BzUtil.fun_get_industry(cycle=None)
        

        inc_operating_revenue_list = []
        for industry in industry_list:
            stock_list = BzUtil.fun_get_industry_stocks(industry, 2, statsDate)
            df_inc_operating_revenue = df[df.code.isin(stock_list)]
            df_inc_operating_revenue = df_inc_operating_revenue.sort_values("inc_operating_revenue",ascending= False)
            inc_operating_revenue_list = inc_operating_revenue_list + list(df_inc_operating_revenue[:int(len(df_inc_operating_revenue)*0.33)].code)
        
        return inc_operating_revenue_list
    
    @staticmethod
    def get_low_liability_ratio(statsDate):
        # 指标剔除资产负债率相对行业最高的1/3的股票
        df = get_fundamentals(query(balance.code, balance.total_liability, balance.total_assets), date = statsDate)
        df = df.fillna(value=0)
        df['liability_ratio'] = 1.0*(df['total_liability'] / df['total_assets'])

        industry_list = BzUtil.fun_get_industry(cycle=None)
        

        liability_ratio_list = []
        for industry in industry_list:
            stock_list = BzUtil.fun_get_industry_stocks(industry, 2, statsDate)
            df_liability_ratio = df[df.code.isin(stock_list)]
            df_liability_ratio = df_liability_ratio.sort_values('liability_ratio', ascending=True)
            liability_ratio_list = liability_ratio_list + list(df_liability_ratio[:int(len(df_liability_ratio)*0.66)].code)
        
        return liability_ratio_list
    
    @staticmethod
    def get_high_profit_ratio(statsDate):
        # 剔除净利润率相对行业最低的1/3的股票；
        df = get_fundamentals(query(indicator.code, indicator.net_profit_to_total_revenue), date = statsDate)
        df = df.fillna(value=0)

        industry_list = BzUtil.fun_get_industry(cycle=None)
        

        profit_ratio_list = []
        for industry in industry_list:
            stock_list = BzUtil.fun_get_industry_stocks(industry, 2, statsDate)
            df_profit_ratio = df[df.code.isin(stock_list)]
            df_profit_ratio = df_profit_ratio.sort_values('net_profit_to_total_revenue', ascending=False)
            profit_ratio_list = profit_ratio_list + list(df_profit_ratio[:int(len(df_profit_ratio)*0.66)].code)
        
        return profit_ratio_list
    
    @classmethod
    @log_time
    def get_high_grow_stocks(cls,startDate=None):
        # 根据增长率和roe（暂时去掉）选取的高增长股票
        all_stocks = BzUtil.get_all_stocks(startDate)
        all_stocks = BzUtil.financial_data_filter_bigger(all_stocks,indicator.gross_profit_margin,40,startDate)
        all_stocks = BzUtil.filter_financial_data_area(all_stocks, factor=valuation.pe_ratio, area=(5,35),startDate=startDate)
        all_stocks = BzUtil.financial_data_filter_bigger(all_stocks,indicator.roe,0)
        return all_stocks


# 用于缓存查询的ps数据。
class CacheDataFramePs:
    def __init__(self):
        self.df = None
        self.means = {}

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
            last_mon = DateHelper.to_date(current_dt) - dt.timedelta(30*(num-i))
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
#         log.info('current[%s] is already in curr mon[end:%s]? %s.'%(str(current_dt),str(next_mon),str(has_curr)))
        return has_curr
    
    def too_more(self, max_cols=49):
        if self.df is None:
            return False
        
        return len(self.df.columns) > max_cols
    
    def drop_column(self,index=1):
        # 0 code列 1 最早一列，前面初始化时是按时间序列排序的
        self.df.drop([self.df.columns[index]],axis=1,inplace=True)
        
    def is_last_same_mon(self,current_dt):
        if self.df is None:
            return False
        
        last_mon_str = self.df.columns[-1]
        return DateHelper.to_date(last_mon_str).month == DateHelper.to_date(current_dt).month

    def last_day_same(self,current_dt):
        if self.df is None:
            return False
        
        last_mon_str = self.df.columns[-1]
        return DateHelper.to_date(last_mon_str) == DateHelper.to_date(current_dt)
    
    def replace_last(self, current_dt):
        if self.df is None:
            return
        
        self.drop_column(-1)
        self.df = self.get_curr_mon_ps(current_dt,self.df)
    
    def refresh_tdy(self):
        if self.df is None:
            return
        
        df = self.df.copy()
        s = df.iloc[:,-1]
        median = s.median()
        df.iloc[:,-1] = s / median
        
        df.index = list(df['code'])
        
        for stock in list(df.index):
            cur,mean,std,score = self.means[stock]
            cur = df.loc[stock][-1]
            if score <=0:
                score = -1
            
            elif cur <=0:
                score = -1
            else:
                score = mean/score
            
            self.means[stock] = cur,mean,std,score 
            
        
    
    def try_get_current_copy(self, current_dt):
        if self.df is None:
            self.df = self.init_last_48_ps(current_dt)
            self.df = self.get_curr_mon_ps(current_dt,self.df)
            self.re_calc_mean()
            return self.df.copy()
        
        if self.last_day_same(current_dt):
            return self.df.copy()
        
        if self.is_last_same_mon(current_dt):
            self.replace_last(current_dt)
            self.refresh_tdy()
            return self.df.copy()
        
        self.df = self.get_curr_mon_ps(current_dt,self.df)

        if self.too_more():
            self.drop_column()
            
        self.re_calc_mean()
        
        return self.df.copy()
    
    @log_time
    def re_calc_mean(self):
        if self.df is None:
            return
        
        def pre_handle_df(df):
            df.index = list(df['code'])
            df = df.drop(['code'], axis=1)
        
            df = df.fillna(value=0, axis=0)
            # 1. 计算相对市收率，相对市收率等于个股市收率除以全市场的市收率，这样处理的目的是为了剔除市场估值变化的影响
            for i in range(len(df.columns)):
                s = df.iloc[:,i]
                median = s.median()
                df.iloc[:,i] = s / median
        
            return df
            
        @log_time
        def get_relative_stocks_dict(df):
            length, stock_list, stock_dict = len(df), list(df.index), {}
            # 2. 计算相对市收率N个月的移动平均值的N个月的标准差，并据此计算布林带上下轨（N个月的移动平均值+/-N个月移动平均的标准差）。N = 24
            col_num = len(df.columns)        
            for i in range(length):
                s = df.iloc[i,:]
                
                if s.min() <= 0:
                    stock_dict[stock_list[i]] = s[-1], 0, 0, -1
                    continue
                
                # tmp_list 是24个月的相对市收率均值
                tmp_list = []
                for j in range(24):
                    tmp_list.append(s[col_num-j-24:col_num-j].mean())
                # mean_value 是最近 24个月的相对市收率均值
                mean_value = tmp_list[0]
                # std_value 是相对市收率24个月的移动平均值的24个月的标准差
                std_value = np.std(tmp_list)
#                 tmp_dict = {}
                # (mean_value - std_value)，是布林线下轨（此处定义和一般布林线不一样，一般是 均线 - 2 倍标准差）
                '''
                研报原始的策略，选择 s[0] < mean_value - std_value 的标的，但因为 ps_ratio十分不稳定，跳跃很大，此区间里的测试结果非常不稳定
                本策略退而求其次，选择均线-1倍标准差 和 均线 - 2 倍标准差之间的标的
                大致反映策略的有效性
                '''
                # if s[-1] > (mean_value - 2.0*std_value) and s[-1] < mean_value:
                    # 记录 相对市收率均值 / 当期相对市收率
                stock_dict[stock_list[i]] = s[-1], mean_value, std_value, (1.0*mean_value/s[-1])
        
            return stock_dict
        
        dfc = self.df.copy()
        dfc = pre_handle_df(dfc)
        
        self.means = get_relative_stocks_dict(dfc)
        
    # 
    def sort_by_score(self,stocks):
        score_dict = {}
        stock_list = []
        
        for s in stocks:
            cur,mean,std,score = self.means[s]
            score_dict[s] = score
        
        dict_score = sorted(list(score_dict.items()), key=lambda d:d[1], reverse=True)
        for idx in dict_score:
            stock = idx[0]
            stock_list.append(stock)
    
        return stock_list
        
    
    def get_mean_std(self,stock):
        return self.means[stock]
        
    
    def get_stock_state(self, stock, current_dt):
        self.try_get_current_copy(current_dt)
        
        cur_ps,mean,std,score = self.get_mean_std(stock)
        
        if cur_ps > 0 and cur_ps > mean + 2*std and score > 0:
            return 'H'
            
        if score > 0 and cur_ps > 0 and cur_ps > mean - 2 * std and cur_ps < mean:
            return 'M'
            
        if cur_ps < 0:
            return '-'
        
        if cur_ps < mean - 2 * std:
            return 'L'
        
        return 'L'
    
    def is_too_high(self, stock, current_dt):
        return self.get_stock_state(stock,current_dt) == 'H'
        
        
    def is_too_low(self, stock, current_dt):
        s = self.get_stock_state(stock,current_dt)
        return s == '-' or s == 'L'
    
    def is_in_low_area(self,stock, current_dt):
        s = self.get_stock_state(stock,current_dt)
        return s == 'M'
    
    def get_all_stocks(self):
        if self.df is None:
            return None
        
        return list(self.df['code'])
    
    def get_tdy_all_stocks(self,current_dt):
        self.try_get_current_copy(current_dt)
        
        return self.get_all_stocks()



class ValueFactorLib():
    def __init__(self):
        pass
        
    @staticmethod
    @log_time
    def fun_get_stock_list(now_date, hold_number=10, statsDate=None):
        # relative_ps = ValueFactorLib.fun_get_relative_ps(statsDate)
        # low_ps = ValueFactorLib.fun_get_low_ps(statsDate)
        # good_stock_list = BzUtil.filter_intersection(relative_ps,low_ps) 
        good_stock_list = QuantLib.get_high_grow_stocks(startDate=statsDate)
        log.info('选取的高增长股数%d'%(len(good_stock_list)))
        # 取净利润增长率为正的
        inc_net_profit_list = QuantLib.get_inc_net_profile(statsDate)
        good_stock_list = BzUtil.filter_intersection(good_stock_list,inc_net_profit_list)
        print((len(good_stock_list)))

        # 按行业取营业收入增长率前 1/3
        inc_operating_revenue_list = QuantLib.get_inc_operating_revenue_list(statsDate)
        good_stock_list = list(set(good_stock_list) & set(inc_operating_revenue_list))
        print((len(good_stock_list)))

        # 指标剔除资产负债率相对行业最高的1/3的股票
        liability_ratio_list = QuantLib.get_low_liability_ratio(statsDate)
        good_stock_list =  BzUtil.filter_intersection(good_stock_list,liability_ratio_list)

        # 剔除净利润率相对行业最低的1/3的股票；
        profit_ratio_list = QuantLib.get_high_profit_ratio(statsDate)
        good_stock_list = BzUtil.filter_intersection(good_stock_list,profit_ratio_list) 

        # stock_list = []
        # for stock in relative_ps:
        #     if stock in good_stock_list:
        #         stock_list.append(stock)

        low_ps = ValueFactorLib.fun_get_low_ps(statsDate)
        good_stock_list = BzUtil.filter_intersection(good_stock_list,low_ps)
        print((len(good_stock_list)))

        stock_list = BzUtil.fun_delNewShare(now_date, good_stock_list, 30)

        bad_stock_list = QuantLib.fun_get_bad_stock_list(statsDate)
        stock_list = stock_list[:hold_number*10]
        stock_list = BzUtil.filter_without(stock_list, bad_stock_list)
        stock_list = BzUtil.remove_limit_up(stock_list)
        stock_list = QuantLib.fun_diversity_by_industry(stock_list, int(hold_number*0.4), statsDate)
        return stock_list[:hold_number]

    @staticmethod
    def fun_get_copy_ps_from_cache(startDate=None):
        return g.cacher.try_get_current_copy(startDate)
    
    @staticmethod
    def fun_get_cacher_from_g():
        return g.cacher

    @staticmethod
    @log_time
    def fun_get_relative_ps(statsDate=None):
        cacher = ValueFactorLib.fun_get_cacher_from_g()
        stocks = cacher.get_tdy_all_stocks(statsDate)
        ok_stocks = []
        for s in stocks:
            if cacher.is_in_low_area(s,statsDate):
               ok_stocks.append(s)
               
        sorted_stock_list = cacher.sort_by_score(ok_stocks)

        return sorted_stock_list

    
    @staticmethod
    @log_time
    def fun_get_not_relative_ps(stocks,statsDate=None):
        cacher = ValueFactorLib.fun_get_cacher_from_g()
        
        not_relative_stocks = []
        # 2. 计算相对市收率N个月的移动平均值的N个月的标准差，并据此计算布林带上下轨（N个月的移动平均值+/-N个月移动平均的标准差）。N = 24
        for stock in stocks:
            if cacher.is_too_high(stock,statsDate) or cacher.is_too_low(stock,statsDate):
                not_relative_stocks.append(stock)
        
        return not_relative_stocks

    
    @staticmethod
    @log_time
    def get_sorted_ps(startDate):
        df = get_fundamentals(
            query(valuation.code, valuation.ps_ratio),
            date = startDate
        )

        # 根据 sp 去极值、中性化、标准化后，跨行业选最佳的标的
        industry_list = BzUtil.fun_get_industry(cycle=None)

        df = df.fillna(value = 0)
        sp_ratio = {}
        df['SP'] = 1.0/df['ps_ratio']

        df = df.drop(['ps_ratio'], axis=1)

        for industry in industry_list:
            tmpDict = QuantLib.fun_get_factor(df, 'SP', industry, 2, startDate).to_dict()
            for stock in tmpDict:
                if stock in sp_ratio:
                    sp_ratio[stock] = max(sp_ratio[stock],tmpDict[stock])
                else:
                    sp_ratio[stock] = tmpDict[stock]

        dict_score = sorted(list(sp_ratio.items()), key=lambda d:d[1], reverse=True)
        stock_list = []

        for idx in dict_score:
            stock = idx[0]
            stock_list.append(stock)

        return stock_list 

    @staticmethod
    def fun_get_low_ps(startDate=None):
        stock_list = ValueFactorLib.get_sorted_ps(startDate=startDate)
        return stock_list[:int(len(stock_list)*0.4)]
    
    @staticmethod
    def fun_get_high_ps(startDate=None):
        stock_list = ValueFactorLib.get_sorted_ps(startDate=startDate)
        return stock_list[int(len(stock_list)*0.6):]
    
    @staticmethod
    def fun_get_tdy_stock_list(current_dt):
        now_date = current_dt
        statsDate = now_date - datetime.timedelta(1)
        stocks = ValueFactorLib.fun_get_stock_list(now_date=now_date,statsDate=statsDate)
        return stocks
    




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

    def check_stop(self,context):
        self.context = context

        for s in context.portfolio.positions:
            p = context.portfolio.positions[s]
            self.try_close(p)
    
    def try_close(self, p):
        # p:Position对象
        if self.is_stop(p,self.stop_ratio):
            log.info('股票[%s]发生止损[%f,%f,%f]。'%(p.security,p.price,p.avg_cost,(p.price-p.avg_cost)*p.total_amount))
            order_target(p.security, 0)
            self.record(p.security)
    
    def is_stop(self, position,ratio=0.08):
        # position:Position对象
        return position.price <= (1-ratio) * position.avg_cost
    
    def is_lost(self, position):
        return self.is_stop(position,0)
    
    def record(self,sec):
        # 记录sec,date
        self.blacks[sec] = self.context.current_dt
        if sec in self.sorted_blacks:
            self.sorted_blacks.remove(sec)
        
        self.sorted_blacks.append(sec)
    
    def beyond_last_stop(self,stock,current_dt):
        import datetime
        stop_day = self.blacks[stock]

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



class QuantileWraper:
    def __init__(self):
        self.pe_pb_df = None
        self.quantile = None
        self.index_code = '000300.XSHG'

    def pretty_print(self,ndays=2):
        if self.quantile is None:
            log.info('没有指数PE分位数据。')
            return
        
        import prettytable as pt

        tb = pt.PrettyTable(["日期", "pe", "pb", "近" + str(g.quantile_long) + "年pe百分位高度"])
        for i in range(1, ndays+1):
            tb.add_row([str(self.pe_pb_df.index[-i]), 
                        str(round(self.pe_pb_df['pe'].iat[-i],3)),
                        str(round(self.pe_pb_df['pb'].iat[-i],3)), 
                        str( round(self.quantile['quantile'].iat[-i],3))])
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
        quantile = df.quantile([0.25, 0.75])
        df_pe = df.pe_ratio[(df.pe_ratio > quantile.pe_ratio.values[0]) & (df.pe_ratio < quantile.pe_ratio.values[1])]
        df_pb = df.pb_ratio[(df.pb_ratio > quantile.pb_ratio.values[0]) & (df.pb_ratio < quantile.pb_ratio.values[1])]
        return date, df_pe.median(), df_pb.median()
    
    # 定义一个函数，计算每天的成份股的平均pe/pb
    def iter_pe_pb(self, index_code, start_date, end_date):
        # 一个获取PE/PB的生成器
        trade_date = get_trade_days(start_date=start_date, end_date=end_date)   
        for date in trade_date:
            yield self.get_one_day_index_pe_pb_media(index_code, date)

    @log_time    
    def get_pe_pb(self, index_code, end_date, old_pe_pb=None):
        if old_pe_pb is not None:
            start_date = old_pe_pb.index[-1]
        else:
            info = get_security_info(index_code)
            start_date = info.start_date

        dict_result = [{'date': value[0], 'pe': value[1], 'pb':value[2]} for value in self.iter_pe_pb(index_code, start_date, end_date)]

        df_result = pd.DataFrame(dict_result)
        df_result.set_index('date', inplace=True)

        if old_pe_pb is None:
            old_pe_pb = df_result
        else:
            old_pe_pb = pd.concat([old_pe_pb, df_result],sort=True)

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

        _df['quantile'] = _df[p].rolling(windows).apply(lambda x: pd.Series(x).rank().iloc[-1] / 
                                                    pd.Series(x).shape[0], raw=True)
        _df.dropna(inplace=True)
        return _df
    
    def _year_to_days(self, years):
        # 这里的计算按一年244个交易日计算
        return int(years * 244)
    
    def init_last_years(self, current_dt, years=7.5, index_code='000300.XSHG'):
        start_date = DateHelper.add_ndays(current_dt,-self._year_to_days(years))
        self.pe_pb_df = self.get_pe_pb(index_code,current_dt)
        self.quantile = self.get_quantile(self.pe_pb_df,'pe',years)
        self.index_code = index_code
        return self.quantile
    
    @log_time
    def try_get_today_quantile(self, current_dt, years=7.5, index_code='000300.XSHG'):
        if self.quantile is None:
            self.quantile = self.init_last_years(DateHelper.add_ndays(current_dt,-1),years,index_code)

        last_day = self.quantile.index[-1]

        if DateHelper.date_is_after(current_dt, last_day):
            self.pe_pb_df = self.get_pe_pb(index_code=self.index_code,end_date=current_dt, old_pe_pb=self.pe_pb_df)
            self.quantile = self.get_quantile(self.pe_pb_df,'pe',years)

        return self.quantile['quantile'].iat[-1]

class RiskLib:
    @staticmethod
    def __get_daily_returns(stock_or_list, freq, lag):
        hStocks = history(lag, freq, 'close', stock_or_list, df=True)
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

    @classmethod
    def formula_risk(cls, quantile, rmax=0.08, rmin=0.005):
        # risk 以0为顶点，开口向下的抛物线，quantile>0.85后，取最小值
        q_mid = 0
        q_min = -0.85
        q_max = q_mid + q_mid - q_min
    
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


def print_with_name(stocks):
    for s in stocks:
        info = get_security_info(s)
        log.info(info.code,info.display_name)


class Trader():
    def __init__(self, context):
        self.context = context
    
    def positions_num(self):
        return len(list(self.context.portfolio.positions.keys()))
    
    @classmethod
    def print_holdings(cls, context):
        if len(list(context.portfolio.positions.keys())) <= 0:
            log.info('没有持仓。')
            return
        
        import prettytable as pt

        tb = pt.PrettyTable(["名称","时间", "数量", "价值","盈亏"])
        total_balance = 0
        for p in context.portfolio.positions:
            pos_obj = context.portfolio.positions[p]
            p_balance = (pos_obj.price-pos_obj.avg_cost) * pos_obj.total_amount
            total_balance += p_balance
            tb.add_row([get_security_info(p).display_name + "(" + p + ")", 
                str(DateHelper.to_date(pos_obj.init_time)), 
                pos_obj.total_amount,
                round(pos_obj.value,2),
                round(p_balance,2)])
        
        log.info(str(tb))
        log.info('总权益：', round(context.portfolio.total_value, 2),' 总持仓：',round(context.portfolio.positions_value,2),' 总盈亏:',round(total_balance,2))
            

    def market_open(self):
        # 买入卖出
        #  低估值浮亏加仓，高估减仓测率
        # 思路：大盘在地位时，低估值股票，越跌越加；大盘高估时，越长越减。大盘中间时，看个股估值。
        
        # 简单思路，选取股票，只要在低估中继续持有，高估卖出。

        self.check_for_sell()

        if self.positions_num() >= g.stock_num:
            log.info('持仓数量大于限仓数量，只调仓不开仓。')
            buys = list(self.context.portfolio.positions.keys())
            self.trade_with_risk_ctrl(buys)
            return
        
        self.check_for_buy()

    
    def check_for_sell(self):
        if len(list(self.context.portfolio.positions.keys())) <= 0:
            log.info("没有持仓，无需平仓。")
            return

        # 检查止损
        g.stopper.check_stop(self.context)

        g.stocks = ValueFactorLib.fun_get_tdy_stock_list(self.context.current_dt)

        # 如果高估，卖出；
        for p in self.context.portfolio.positions:
            if p not in g.stocks:
                log.info('股票不在股票池，卖出。')
                BzUtil.print_with_name([p])
                order_target(p, 0)
    
    # def is_stock_too_high(self,stock):
    #     if not hasattr(self,'not_relateive_low_stocks') or self.not_relateive_low_stocks is None:
    #         holds = list(self.context.portfolio.positions.keys())
    #         self.not_relateive_low_stocks = ValueFactorLib.fun_get_not_relative_ps(stocks=holds, statsDate=self.context.previous_date)

    #     if stock in self.not_relateive_low_stocks:
    #         log.info('[%s]在相对高估股票中'%(stock))
    #         return True

    #     if not hasattr(self,'high_ps_stocks') or self.high_ps_stocks is None:
    #         self.high_ps_stocks = ValueFactorLib.fun_get_high_ps(startDate=self.context.previous_date)
        
    #     if stock in self.high_ps_stocks:
    #         log.info('[%s]在高PS股票中'%(stock))
    #         return True
        
    #     return False
    
    # 策部略选股买卖分    
    def check_for_buy(self):
        if self.positions_num() >= g.stock_num:
            log.info('持仓数量大于等于最大允许持仓数量，不新增仓位。')
            return

        if not hasattr(g,'stocks') or g.stocks is None:
            g.stocks = ValueFactorLib.fun_get_tdy_stock_list(self.context.previous_date)

        g.stocks = g.stopper.filter_and_sort(g.stocks, self.context.current_dt)
        
        hold_stock = list(self.context.portfolio.positions.keys())
        # 买入股票
        buys = self.choose_buy_stocks(self.context)
        log.info('总共选出%s只股票'%len(buys))
        # print_with_name(buys)

        if len(buys) <= 0:
            return
        
        self.trade_with_risk_ctrl(buys)

    
    def ajust_hold_positions(self,portfilo_ratio,will_spend):
        need_sells = {}
        need_buys = {}

        for s in self.context.portfolio.positions:
            if s not in portfilo_ratio:
                log.info('持仓[%s]不再组合中，全部清空。'%(s))
                order_target(s,0)
                continue

            ratio = portfilo_ratio[s]
            cost = will_spend * ratio
            p = self.context.portfolio.positions[s]
            if p.value > cost + p.price * 100:
                need_sells[s] = cost
            elif p.value < cost - p.price * 100:
                need_buys[s] = cost
            else:
                log.info('持仓[%s]变动很小，不需要调整。'%(s))
        
        # 先处理卖
        for s in need_sells:
            order_target_value(s,need_sells[s])
        
        for s in need_buys:
            order_target_value(s,need_buys[s])
    
    def buy_stocks_by_ratio(self,buy_stocks,portfilo_ratio,total_cost):
        for s in buy_stocks:
            ratio = portfilo_ratio[s]
            cost = total_cost * ratio
            order_target_value(s,cost)


    def trade_with_risk_ctrl(self,buys):
        portfilo_ratio = RiskLib.get_portfilo_ratio_ES(buys, g.confidentLevel)
        portfilo_VaR = RiskLib.get_portfilo_VaR(portfolio_ratios=portfilo_ratio,confidentLevel=g.confidentLevel)
        portfilo_es = RiskLib.get_portfilo_es(portfolio_ratios=portfilo_ratio,confidentLevel=g.confidentLevel)

        risk_money = self.context.portfolio.total_value * g.risk

        vaR_value = RiskLib.calc_portfilo_var_value_by_risk_money(risk_money,portfilo_ratio,confidentLevel=g.confidentLevel)
        es_value = RiskLib.calc_portfilo_es_value_by_risk_money(risk_money*1.5,portfilo_ratio,confidentLevel=g.confidentLevel)
        risk_value = min(vaR_value,es_value)

        buy_value = min(risk_value,self.context.portfolio.total_value)

        log.info('portfilo_ratio:',portfilo_ratio,' buy_value:', buy_value,' g.risk:', g.risk)
        
        self.ajust_hold_positions(portfilo_ratio,buy_value)

        need_buys = BzUtil.filter_without(list(portfilo_ratio.keys()),list(self.context.portfolio.positions.keys()))

        self.buy_stocks_by_ratio(need_buys,portfilo_ratio,buy_value)

    def choose_buy_stocks(self, context):
        buys = []

        hold_stock = list(context.portfolio.positions.keys())
        
        for s in hold_stock:
            buys.append(s)  # 大盘有利，持有的仓位继续持有，不看个股rs。

        log.info('目前持有股票数量[%d],还需再选[%d]。'%(len(buys), g.stock_num-len(buys)))

        for s in g.stocks:
            if len(buys) >= g.stock_num:
                break

            if s in hold_stock:
                continue
            buys.append(s)
            log.info('额外选出股票[%s]'%(s))
            print_with_name([s])
            
        return buys



# 初始化函数，设定基准等等
def initialize(context):
    # 设定上证指数作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    log.set_level('order', 'error')
    
    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')
    
    ## 运行函数（reference_security为运行时间的参考标的；传入的标的只做种类区分，因此传入'000300.XSHG'或'510300.XSHG'是一样的）
      # 开盘前运行
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG') 
      # 开盘时运行
    run_daily(market_open, time='open', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')

    # g.init = True
    
    
## 开盘前运行函数     
def before_market_open(context):
    # 输出运行时间
    log.info('函数运行时间(before_market_open)：'+str(context.current_dt.time()))

## 开盘时运行函数
def market_open(context):
    log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
    trader = Trader(context)
    trader.market_open()


## 收盘后运行函数  
def after_market_close(context):
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))

    g.risk = RiskLib.ajust_risk(context)
    g.quantile.pretty_print()
    Trader.print_holdings(context)
    #得到当天所有成交记录
    # trades = get_trades()
    # for _trade in list(trades.values()):
    #     log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('#'*50)

def after_code_changed(context):
    log.info('after_code_changed')
    g.stock_num = 5
    
    g.security = '000300.XSHG'
 
    g.stocks = None
    
    g.stopper = StopManager()
    g.stopper.stop_ratio = 0.08 # 跌8%止损
    g.stopper.stop_ndays = 20

    # 风险敞口的最大最小值
    g.risk = 0.03 # 风险敞口
    g.max_risk, g.min_risk = 0.05,0.01
    g.confidentLevel = 1.96

    g.cacher = CacheDataFramePs() # 缓存
    g.cacher.init_last_48_ps(context.current_dt)
  

    g.quantile_long = 7.5 # 检查的pe分位的年数

    g.quantile = QuantileWraper()
    g.quantile.init_last_years(context.current_dt,years=g.quantile_long)

    g.risk = RiskLib.ajust_risk(context)
        


