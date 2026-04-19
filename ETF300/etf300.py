# 克隆自聚宽文章：https://www.joinquant.com/post/70394
# 标题：ETF 300轮动（年化60%）：从原理到实战的全面解析
# 作者：大山深处

# 标题：ETF 300轮动模型
# 作者：王巨明
# 思路：
#       1、假定ETF 300指数基金每一分钟的价值应相等，如果因市场原因产生偏差，就有机会获利 
#       2、优选的9只ETF 300指数基金(初始账户为空）
#       3、每分钟计算这9只ETF 300指数基金的涨跌幅
#       4、如果持仓ETF的涨幅 - 最弱ETF的涨幅 > 0.3%，则卖出该ETF，并买入最弱ETF
#       5、解决部分成交的问题：每分钟取消所有未完成订单，重新判断与下单
#
# 回测：【时间段】2021-1-1至2026-3-31【63月】
#    （1）资金200W，成交比例20%
#         策略收益:616.47%； 年化收益:47.44%；最大回撤:12.40%；卡玛比:3.83
#    （2）资金500W，成交比例20%
#          策略收益:397.65%； 年化收益:37.22%；最大回撤:13.25%；卡玛比:2.81
#
# 日期：2026-4-16
##
## 导入函数库
import numpy as np
import pandas as pd
import time
##
## 初始化函数，设定基准等等
def initialize(context):
    # 设定基准，选用沪深300指数
    set_benchmark('000300.XSHG')
    # 开启避免未来数据的模式
    set_option("avoid_future_data", True)
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 设置滑点
    set_slippage(FixedSlippage(0.002))
    # 调试时必须注释下面语句；调试完成后，开启下面语句，减少日志内容
    log.set_level('order', 'error')
    # 设置成交比例，即每日或每分钟内的成交量的20%【比较合理】
    set_option('order_volume_ratio', 0.20)
    # 设置交易费用
    set_order_cost(OrderCost(close_tax=0, open_commission=0.00005, close_commission=0.00005, min_commission=0), type='fund')
    # 优选的9只ETF 300指数基金
    g.etf_pool = [
        '510300.XSHG',  # 上市2012-05-28，基金规模2067.00亿元(2026-4-14)
        '510310.XSHG',  # 上市2013-03-25，基金规模1427.00亿元(2026-4-14)
        '159919.XSHE',  # 上市2012-05-28，基金规模 962.30亿元(2026-4-14)
        '510330.XSHG',  # 上市2013-01-16，基金规模 944.40亿元(2026-4-14)
        '515330.XSHG',  # 上市2019-12-26，基金规模  88.34亿元(2026-4-14)
        '515380.XSHG',  # 上市2020-03-23，基金规模  35.85亿元(2026-4-14) 
        '510350.XSHG',  # 上市2019-08-16，基金规模  34.39亿元(2026-4-14) 
        '510360.XSHG',  # 上市2015-09-09，基金规模  30.22亿元(2026-4-14)
        '159925.XSHE',  # 上市2013-04-11，基金规模  26.22亿元(2026-4-14)
        ]
    # 过滤上市不到1年的ETF，在before_trading_start计算
    g.etf_list = []
    # 昨日的收盘价，在before_trading_start计算
    g.yest_close_df = pd.DataFrame()
    # 与最佳ETF涨跌幅的差值阈值，取0.3%
    g.ret_threshold = 0.3/100
    # 每天修改运行标志
    g.is_traded = False
##
## 开盘前运行
def before_trading_start(context):
    # 1、过滤上市不到1年的ETF
    date_limit = context.current_dt.date() - pd.Timedelta(days=365)
    g.etf_list = [etf for etf in g.etf_pool if get_security_info(etf).start_date < date_limit]
    # 所有ETF 300昨日收盘价
    g.yest_close_df = history(1, '1d', 'close', g.etf_list)
    # 每天修改运行标志
    g.is_traded = False
##
## 本策略在回测时，应按分钟回测
def handle_data(context, data):
    # 如果当日已交易，直接返回
    if g.is_traded:
        return
    # 检查是否可以交易（自动取消未完成订单）
    if not is_tradeable(context):
        g.is_traded = True
        return
    # 如果没有符合条件的ETF, 则跳过
    if len(g.etf_list) == 0:
        return
    # 1、计算当前各ETF的涨跌幅度
    current_data = get_current_data()
    ret_dict = {}
    for etf in g.etf_list:
        last_price = current_data[etf].last_price
        yesterday_close = g.yest_close_df[etf][0]
        ret_dict[etf] = (last_price - yesterday_close) / yesterday_close if yesterday_close > 0 else 0
    # 2、找出涨幅最小（最弱）的ETF
    sorted_list = sorted(ret_dict.items(), key=lambda x: x[1])
    etf_worst = sorted_list[0][0]
    ret_worst = sorted_list[0][1]
    # 3、卖出符合条件的ETF
    has_sold = False
    for etf in g.etf_list:
        if etf == etf_worst:
            continue
        if etf in context.portfolio.positions:
            pos = context.portfolio.positions[etf]
            if pos.closeable_amount > 0:
                # 卖出逻辑
                ret_hold = ret_dict[etf]
                delta = ret_hold - ret_worst
                if delta > g.ret_threshold:
                    print(f" === 【符合条件】卖出持有的{etf}，涨幅:{ret_hold:.2%}，买入收益最弱的{etf_worst}:{ret_worst:.2%}，差值={delta:.2%}>{g.ret_threshold:.2%}")
                    o = order_target_value(etf, 0)
                    if o and o.filled >0:
                        name = get_security_info(etf).display_name
                        print(f"{name}【{etf[:6]}】，已下单{o.amount}股，已卖出{o.filled}股，平均价格：{o.price}")  
                    has_sold = True
    # 4、卖出完成后，实盘环境等待6秒，让资金到账
    if has_sold and context.run_params == 'sim_trade':
        time.sleep(6)
    if context.portfolio.available_cash > 1000:
        cash = context.portfolio.available_cash
        last_price = current_data[etf_worst].last_price
        num = cash / last_price if last_price > 0 else 0
        if num >= 100:
            print(f" === 【符合条件】买入收益最弱的{etf_worst}，涨幅:{ret_worst:.2%}")
            o = order_value(etf_worst, cash)
            if o and o.filled >0:
                name = get_security_info(etf_worst).display_name
                print(f"{name}【{etf_worst[:6]}】，已下单{o.amount}股，已卖出{o.filled}股，平均价格：{o.price}") 
##
## 检查是否可以交易
def is_tradeable(context):
    """
    取消所有未完成订单，并检查是否可以继续交易
    返回 True: 可以交易, False: 无法交易
    """
    # 1. 取消所有未完成订单
    orders = get_open_orders()
    for order in orders:
        cancel_order(order)
    # 2. 检查现金（大于1000元）
    if context.portfolio.available_cash > 1000:
        return True
    # 3. 检查是否有可交易的ETF持仓（closeable_amount > 0）
    for etf in g.etf_list:
        if etf in context.portfolio.positions:
            pos = context.portfolio.positions[etf]
            if pos.closeable_amount > 0:
                return True
    # 4. 无法交易
    return False
# end

