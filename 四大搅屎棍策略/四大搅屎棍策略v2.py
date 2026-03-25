# 克隆自聚宽文章：https://www.joinquant.com/post/49085
# 标题：四大搅屎棍策略 v2.0
# 作者：MarioC
# v2.0 改动：
#   1. 滑点从 FixedSlippage(0) 改为 PriceRelatedSlippage(0.003)，模拟实盘买卖价差
#   2. 修复 filter_kcbj_stock 遍历时修改列表的 bug

from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
import pickle
from six import StringIO,BytesIO
import talib

# 初始化函数
def initialize(context):
    # 设定基准
    set_benchmark('000985.XSHG')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 打开防未来函数
    set_option("avoid_future_data", True)
    # v2: 按成交价的 0.3% 设置滑点，更贴近小市值股票实盘情况
    set_slippage(PriceRelatedSlippage(0.003))
    # 设置交易成本万分之三
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003,
                             close_today_commission=0, min_commission=5), type='stock')
    # 过滤order中低于error级别的日志
    log.set_level('order', 'error')
    # 初始化全局变量
    g.stock_num = 10
    g.hold_list = []
    g.yesterday_HL_list = []
    g.num = 1
    # 设置交易运行时间
    run_daily(prepare_stock_list, '9:05')
    run_weekly(weekly_adjustment, 1, '9:30')
    run_daily(check_limit_up, '14:00')


SW1 = {
    '801010': '农林牧渔I', '801020': '采掘I', '801030': '化工I', '801040': '钢铁I',
    '801050': '有色金属I', '801060': '建筑建材I', '801070': '机械设备I', '801080': '电子I',
    '801090': '交运设备I', '801100': '信息设备I', '801110': '家用电器I', '801120': '食品饮料I',
    '801130': '纺织服装I', '801140': '轻工制造I', '801150': '医药生物I', '801160': '公用事业I',
    '801170': '交通运输I', '801180': '房地产I', '801190': '金融服务I', '801200': '商业贸易I',
    '801210': '休闲服务I', '801220': '信息服务I', '801230': '综合I', '801710': '建筑材料I',
    '801720': '建筑装饰I', '801730': '电气设备I', '801740': '国防军工I', '801750': '计算机I',
    '801760': '传媒I', '801770': '通信I', '801780': '银行I', '801790': '非银金融I',
    '801880': '汽车I', '801890': '机械设备I', '801950': '煤炭I', '801960': '石油石化I',
    '801970': '环保I', '801980': '美容护理I'
}

# 1-1 准备股票池
def prepare_stock_list(context):
    g.hold_list = []
    for position in list(context.portfolio.positions.values()):
        g.hold_list.append(position.security)
    if g.hold_list:
        df = get_price(g.hold_list, end_date=context.previous_date, frequency='daily',
                       fields=['close', 'high_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.yesterday_HL_list = list(df.code)
    else:
        g.yesterday_HL_list = []

industry_code = [
    '801010','801020','801030','801040','801050','801080','801110','801120','801130','801140','801150',
    '801160','801170','801180','801200','801210','801230','801710','801720','801730','801740','801750',
    '801760','801770','801780','801790','801880','801890'
]

def getStockIndustry(p_stocks, p_industries_type, p_day):
    dict_stk_2_ind = {}
    stocks_industry_dict = get_industry(p_stocks, date=p_day)
    for stock in stocks_industry_dict:
        if p_industries_type in stocks_industry_dict[stock]:
            dict_stk_2_ind[stock] = stocks_industry_dict[stock][p_industries_type]['industry_code']
    return pd.Series(dict_stk_2_ind)

# 1-2 选股模块
def get_stock_list(context):
    yesterday = context.previous_date
    today = context.current_dt
    initial_list = get_index_stocks('000985.XSHG', today)
    p_count = 1
    p_industries_type = 'sw_l1'
    h = get_price(initial_list, end_date=yesterday, frequency='1d', fields=['close'], count=p_count + 20, panel=False)
    h['date'] = pd.DatetimeIndex(h.time).date
    df_close = h.pivot(index='code', columns='date', values='close').dropna(axis=0)
    df_ma20 = df_close.rolling(window=20, axis=1).mean().iloc[:, -p_count:]
    df_bias = (df_close.iloc[:, -p_count:] > df_ma20)
    s_stk_2_ind = getStockIndustry(p_stocks=initial_list, p_industries_type=p_industries_type, p_day=yesterday)
    df_bias['industry_code'] = s_stk_2_ind
    df_ratio = ((df_bias.groupby('industry_code').sum() * 100.0) / df_bias.groupby('industry_code').count()).round()
    top_values = df_ratio[datetime.date(yesterday.year, yesterday.month, yesterday.day)].nlargest(g.num)
    I = top_values.index.tolist()
    name_list = [SW1[code] for code in I]
    print(name_list)
    print('全市场宽度：', np.array(df_ratio.sum(axis=0).mean()))
    if '801780' not in I and '801050' not in I and '801950' not in I and '801040' not in I:
        S_stocks = get_index_stocks('399101.XSHE', today)
        stocks = filter_kcbj_stock(S_stocks)
        choice = filter_st_stock(stocks)
        choice = filter_new_stock(context, choice)
        BIG_stock_list = get_fundamentals(query(
            valuation.code,
        ).filter(
            valuation.code.in_(choice),
            indicator.roe > 0.15,
            indicator.roa > 0.10,
        ).order_by(
            valuation.market_cap.asc()
        ).limit(g.stock_num)).set_index('code').index.tolist()
        BIG_stock_list = filter_paused_stock(BIG_stock_list)
        BIG_stock_list = filter_limitup_stock(context, BIG_stock_list)
        L = filter_limitdown_stock(context, BIG_stock_list)
    else:
        print('跑')
        L = []
    return L

# 1-3 整体调整持仓
def weekly_adjustment(context):
    target_B = get_stock_list(context)
    for stock in g.hold_list:
        if (stock not in target_B) and (stock not in g.yesterday_HL_list):
            close_position(context.portfolio.positions[stock])
    position_count = len(context.portfolio.positions)
    target_num = len(target_B)
    if target_num > position_count:
        buy_num = min(len(target_B), g.stock_num * g.num - position_count)
        value = context.portfolio.cash / buy_num
        for stock in target_B:
            if stock not in list(context.portfolio.positions.keys()):
                if open_position(stock, value):
                    if len(context.portfolio.positions) == target_num:
                        break

def check_limit_up(context):
    now_time = context.current_dt
    if g.yesterday_HL_list:
        for stock in g.yesterday_HL_list:
            current_data = get_price(stock, end_date=now_time, frequency='1m', fields=['close', 'high_limit'],
                                     skip_paused=False, fq='pre', count=1, panel=False, fill_paused=True)
            if current_data.iloc[0, 0] < current_data.iloc[0, 1]:
                log.info("[%s]涨停打开，卖出" % stock)
                close_position(context.portfolio.positions[stock])
            else:
                log.info("[%s]涨停，继续持有" % stock)

# 3-1 交易模块
def order_target_value_(security, value):
    if value == 0:
        log.debug("Selling out %s" % security)
    else:
        log.debug("Order %s to value %f" % (security, value))
    return order_target_value(security, value)

def open_position(security, value):
    order = order_target_value_(security, value)
    if order != None and order.filled > 0:
        return True
    return False

def close_position(position):
    security = position.security
    order = order_target_value_(security, 0)
    if order != None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            return True
    return False

# 2-1 过滤停牌股票
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

# 2-2 过滤ST及退市股票
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]

# 2-3 过滤科创北交股票（v2: 修复遍历时修改列表的 bug）
def filter_kcbj_stock(stock_list):
    return [stock for stock in stock_list
            if stock[0] not in ('4', '8', '3') and stock[:2] != '68']

# 2-4 过滤涨停股票
def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] < current_data[stock].high_limit]

# 2-5 过滤跌停股票
def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] > current_data[stock].low_limit]

# 2-6 过滤次新股
def filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if
            not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]
