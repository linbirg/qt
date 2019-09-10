# author:linbirg
# 2019-09-04
# 本身存在的问题：
# 1 fisher选股因子是长期，适合尽量久拿
# 2.fisher中低估值（估计）存在不稳定性
# 3.rsrs择时存在亏损过大的情况
# 优化点：1 增加止损 2 市场整体有风险时，平掉亏损仓位。
import pandas as pd
import datetime as dt


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
        deltaDate = current_dt.date() - dt.timedelta(deltaday)
    
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


class ValueFactorLib():
    def __init__(self):
        pass
        
    @staticmethod
    def fun_get_stock_list(now_date, hold_number=10, statsDate=None):
        relative_ps = ValueFactorLib.fun_get_relative_ps(statsDate)
        low_ps = ValueFactorLib.fun_get_low_ps(statsDate)
        good_stock_list = BzUtil.filter_intersection(relative_ps,low_ps) 

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

        stock_list = []
        for stock in relative_ps:
            if stock in good_stock_list:
                stock_list.append(stock)

        print((len(good_stock_list)))

        stock_list = BzUtil.fun_delNewShare(now_date, stock_list, 30)

        bad_stock_list = QuantLib.fun_get_bad_stock_list(statsDate)
        stock_list = stock_list[:hold_number*10]
        stock_list = BzUtil.filter_without(stock_list, bad_stock_list)
        stock_list = BzUtil.remove_limit_up(stock_list)
        stock_list = QuantLib.fun_diversity_by_industry(stock_list, int(hold_number*0.4), statsDate)
        return stock_list[:hold_number]

    @staticmethod
    def fun_get_relative_ps(statsDate=None):
        def __fun_get_ps(statsDate, deltamonth):
            __df = get_fundamentals(query(valuation.code, valuation.ps_ratio), date = (statsDate - dt.timedelta(30*deltamonth)))
            __df.rename(columns={'ps_ratio':deltamonth}, inplace=True)
            return __df

        for i in range(48):
            df1 = __fun_get_ps(statsDate, i)
            if i == 0:
                df = df1
            else:
                df = df.merge(df1, on='code')

        df.index = list(df['code'])
        df = df.drop(['code'], axis=1)

        df = df.fillna(value=0, axis=0)
        # 1. 计算相对市收率，相对市收率等于个股市收率除以全市场的市收率，这样处理的目的是为了剔除市场估值变化的影响
        for i in range(len(df.columns)):
            s = df.iloc[:,i]
            median = s.median()
            df.iloc[:,i] = s / median

        length, stock_list, stock_dict = len(df), list(df.index), {}
        # 2. 计算相对市收率N个月的移动平均值的N个月的标准差，并据此计算布林带上下轨（N个月的移动平均值+/-N个月移动平均的标准差）。N = 24
        for i in range(length):
            s = df.iloc[i,:]
            if s.min() < 0:
                pass
            else:
                # tmp_list 是24个月的相对市收率均值
                tmp_list = []
                for j in range(24):
                    tmp_list.append(s[j:j+24].mean())
                # mean_value 是最近 24个月的相对市收率均值
                mean_value = tmp_list[0]
                # std_value 是相对市收率24个月的移动平均值的24个月的标准差
                std_value = np.std(tmp_list)
                tmp_dict = {}
                # (mean_value - std_value)，是布林线下轨（此处定义和一般布林线不一样，一般是 均线 - 2 倍标准差）
                '''
                研报原始的策略，选择 s[0] < mean_value - std_value 的标的，但因为 ps_ratio十分不稳定，跳跃很大，此区间里的测试结果非常不稳定
                本策略退而求其次，选择均线-1倍标准差 和 均线 - 2 倍标准差之间的标的
                大致反映策略的有效性
                '''
                if s[0] > (mean_value - 2.0*std_value) and s[0] < mean_value:
                    # 记录 相对市收率均值 / 当期相对市收率
                    stock_dict[stock_list[i]] = (1.0*mean_value/s[0])

        stock_list = []
        dict_score = stock_dict
        dict_score = sorted(list(dict_score.items()), key=lambda d:d[1], reverse=True)
        for idx in dict_score:
            stock = idx[0]
            stock_list.append(stock)

        return stock_list

    @staticmethod
    def fun_get_low_ps(statsDate=None):
        df = get_fundamentals(
            query(valuation.code, valuation.ps_ratio),
            date = statsDate
        )

        # 根据 sp 去极值、中性化、标准化后，跨行业选最佳的标的
        industry_list = BzUtil.fun_get_industry(cycle=None)

        df = df.fillna(value = 0)
        sp_ratio = {}
        df['SP'] = 1.0/df['ps_ratio']

        df = df.drop(['ps_ratio'], axis=1)

        for industry in industry_list:
            tmpDict = QuantLib.fun_get_factor(df, 'SP', industry, 2, statsDate).to_dict()
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

        return stock_list[:int(len(stock_list)*0.5)]
    

class Fisher():
    def __init__(self):
        self.factorlib = ValueFactorLib()
    
    def fun_get_tdy_stock_list(self, current_dt):
        now_date = current_dt
        statsDate = now_date - datetime.timedelta(1)
        stocks = ValueFactorLib.fun_get_stock_list(now_date=now_date,statsDate=statsDate)
        return stocks


# 导入函数库
import statsmodels.api as sm
import random

class RSRSLib():
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
                rs = self.RsPair(**dict_data[d])
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
            rs = self.RsPair(**self.rsrses[sec])
        else:
            rs = self.RsPair()
            self.rsrses[sec] = rs
        # 计算2005年1月5日至回测开始日期的RSRS斜率指标
        ans,ans_rightdev = self.calc_sec_rsrs_from(sec, rs['date'], end_date)
        if ans and ans_rightdev:
            self.rsrses[sec] = self.RsPair(ans=ans,r2s=ans_rightdev,date=end_date)
    
        
    def is_sec_buy_or_sell(self,sec,N=18,M=1100):
        prices = attribute_history(sec, N, '1d', ['high', 'low'])
        if len(prices.dropna()) == 0:
            log.info('no data for sec'+sec)
            return 'n'
            
        beta, r2 = self.rsrs(prices.dropna())
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
        return self.is_sec_buy_or_sell('000300.XSHG')
    
    def judge_today_buy_or_sell(self,sec,now_date,N=18,M=1100):
        self.init_sec_rsrs(sec,now_date)
        return self.is_sec_buy_or_sell(sec,N,M)
    
    def is_hs300_buy_tdy(self,now_date):
        return self.judge_today_buy_or_sell('000300.XSHG',now_date)

class StopManager():
    # 1 是否止损 
    # 2 止损记录
    # 3 一段时间内不再购买
    # 4 按先后排序
    def __init__(self):
        self.stop_ratio = 0.9 # 跌10%止损
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
        if self.is_stop(p):
            log.info('股票[%s]发生止损[%f,%f]。'%(p.security,p.price,p.avg_cost))
            order_target(p.security, 0)
            self.record(p.security)
    
    def is_stop(self, position):
        # position:Position对象
        return position.price <= self.stop_ratio * position.avg_cost
    
    def is_lost(self, position):
        return position.price <= position.avg_cost
    
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
                if self.beyond_last_stop(s,current_dt):
                    need_sort.append(s)
                
        sorted_stocks = self.sort_by_stop_time(need_sort)

        return filted_stocks + sorted_stocks

class Trader():
    # 买入卖出
    pass

# 初始化函数，设定基准等等
def initialize(context):
    # 设定上证指数作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    # log.set_level('order', 'error')
    
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

    # 设置RSRS指标中N, M的值
    g.N = 18
    g.M = 1100
    g.init = True
    g.stock_num = 5
    
    g.security = '000300.XSHG'
 
    # 买入阈值
    g.buy = 0.7
    g.sell = -0.7
    g.ans = []
    g.ans_rightdev= []
    # g.buys = []
    # g.max_buys = 10
    
    # targs = [g.security]
    g.rsrses = {}
    
    g.last_update_dt = None
    g.stocks = None
    
    log.info('begin to init rsrses...')
    g.rsrslib = RSRSLib()
    g.rsrslib.init_sec_rsrs(g.security,context.previous_date)
    
    g.fisher = Fisher()
    g.stopper = StopManager()
    
## 开盘前运行函数     
def before_market_open(context):
    # 输出运行时间
    log.info('函数运行时间(before_market_open)：'+str(context.current_dt.time()))
    # g.rsrslib = RSRSLib()
    # g.rsrslib.load_rsrs_from()
    


def try_close_positions_rsrs(context):
    hold_stock = list(context.portfolio.positions.keys())
    for s in hold_stock:
        bs = g.rsrslib.judge_today_buy_or_sell(s,context.previous_date)
        if bs == 's':
            order_target(s,0)

## 开盘时运行函数
def market_open(context):
    log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
    # 取得当前的现金
    # cash = context.portfolio.available_cash
    g.stopper.check_stop(context)

    bs = g.rsrslib.is_hs300_buy_tdy(context.previous_date)
    if bs == 'b':
        log.info("市场风险在合理范围")
        trade_func(context)
    elif (bs == 's') and (len(list(context.portfolio.positions.keys())) > 0):
        log.info("市场风险过大，清空所有存在风险的个股。")
        for s in context.portfolio.positions:
            if g.stopper.is_lost(context.portfolio.positions[s]):
                order_target(s,0)
 

def print_with_name(stocks):
    for s in stocks:
        info = get_security_info(s)
        log.info(info.code,info.display_name)


#策略选股买卖部分    
def trade_func(context):
    #得到每只股票应该分配的资金
    
    #获取已经持仓列表
    # hold_stock = list(context.portfolio.positions.keys())

    # #卖出不在持仓中的股票
    # intersection = BzUtil.filter_intersection(hold_stock,g.stocks)
    # sells = BzUtil.filter_without(hold_stock,intersection)
    # for s in sells:
    #     log.info('[%s]不再好股票之列，卖出'%(s))
    #     order_target(s,0)

    
    # hold_stock = list(context.portfolio.positions.keys())

    # for s in hold_stock:
    #     bs = g.rsrslib.judge_today_buy_or_sell(s,context.previous_date)
    #     if bs == 's':
    #         order_target(s,0)
    try_close_positions_rsrs(context)

    hold_stock = list(context.portfolio.positions.keys())

    cnt = len(hold_stock)
    if cnt >= g.stock_num:
        log.info('持仓数量大于等于最大允许持仓数量，不新增仓位。')
        return

    if context.portfolio.available_cash <= context.portfolio.total_value*0.05:
        log.info('我们可能资金不足，不开仓[cash:%d total:%d]。'%(context.portfolio.available_cash,context.portfolio.total_value))
        return
    
    g.stocks = g.fisher.fun_get_tdy_stock_list(context.current_dt)

    g.stock = g.stopper.filter_and_sort(g.stocks,context.current_dt)
    
    delta = g.stock_num - cnt
    log.info('需要再选出%d只股票。'%(delta))
    
    #买入股票
    buys = []
    for s in g.stocks:
        # 以持仓的不再买入
        if s in hold_stock:
            continue

        bs = g.rsrslib.judge_today_buy_or_sell(s,context.previous_date)
        if bs == 'b':
            buys.append(s)
        
        if len(buys) >= delta:
            break
        
    log.info('总共选出%s只股票'%len(buys))
    if len(buys) == 0:
        return
    
    print_with_name(buys)

    # cash = context.portfolio.total_value/len(buys)
    cash = context.portfolio.available_cash/len(buys)
    for s in buys:
        order_target_value(s,cash)


## 收盘后运行函数  
def after_market_close(context):
    # g.rsrslib.to_file()
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in list(trades.values()):
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('#'*50)

