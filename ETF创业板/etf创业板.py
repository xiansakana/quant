# 标题：ETF 创业板轮动模型
# 作者：王巨明
# 思路：
#       1、假定ETF 创业板指数基金每一分钟的价值应相等，如果因市场原因产生偏差，就有机会获利
#       2、优选的创业板ETF指数基金(初始账户为空）
#       3、每分钟计算这些ETF的涨跌幅
#       4、如果持仓ETF的涨幅 - 最弱ETF的涨幅 > 0.3%，则卖出该ETF，并买入最弱ETF
#       5、解决部分成交的问题：每分钟取消所有未完成订单，重新判断与下单
#
# 日期：2026-4-19
##
## 导入函数库
import numpy as np
import pandas as pd
import time
##
## 初始化函数，设定基准等等
def initialize(context):
    # 设定基准，选用创业板指
    set_benchmark('399006.XSHE')
    # 开启避免未来数据的模式
    set_option("avoid_future_data", True)
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 设置滑点
    set_slippage(FixedSlippage(0.002))
    # 调试时必须注释下面语句；调试完成后，开启下面语句，减少日志内容
    log.set_level('order', 'error')
    # 设置成交比例，即每日或每分钟内的成交量的20%
    set_option('order_volume_ratio', 0.20)
    # 设置交易费用
    set_order_cost(OrderCost(close_tax=0, open_commission=0.00005, close_commission=0.00005, min_commission=0), type='fund')
    # 创业板ETF池
    g.etf_pool = [
        '159908.XSHE',
        '159915.XSHE',
        '159810.XSHE',
        '159247.XSHE',
        '159948.XSHE',
        '159952.XSHE',
        '159957.XSHE',
        '159958.XSHE',
        '159956.XSHE',
        '159964.XSHE',
        '159971.XSHE',
        '159977.XSHE',
        '159821.XSHE',
        '159205.XSHE',
        ]
    # 过滤上市不到1年的ETF，在before_trading_start计算
    g.etf_list = []
    # 昨日的收盘价，在before_trading_start计算
    g.yest_close_df = pd.DataFrame()
    # 与最佳ETF涨跌幅的差值阈值，取0.3%
    g.ret_threshold = 0.3/100
##
## 开盘前运行
def before_trading_start(context):
    # 过滤上市不到1年或代码无效的ETF
    date_limit = context.current_dt.date() - pd.Timedelta(days=365)
    g.etf_list = [etf for etf in g.etf_pool if get_security_info(etf) is not None and get_security_info(etf).start_date < date_limit]
    # 所有ETF昨日收盘价
    g.yest_close_df = history(1, '1d', 'close', g.etf_list)
##
## 本策略在回测时，应按分钟回测
def handle_data(context, data):
    # 检查是否可以交易（自动取消未完成订单）
    if not is_tradeable(context):
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
                ret_hold = ret_dict[etf]
                delta = ret_hold - ret_worst
                if delta > g.ret_threshold:
                    print(f" === 【符合条件】卖出持有的{etf}，涨幅:{ret_hold:.2%}，买入收益最弱的{etf_worst}:{ret_worst:.2%}，差值={delta:.2%}>{g.ret_threshold:.2%}")
                    o = order_target_value(etf, 0)
                    if o and o.filled > 0:
                        name = get_security_info(etf).display_name
                        print(f"{name}【{etf[:6]}】，已下单{o.amount}股，已卖出{o.filled}股，平均价格：{o.price}")
                    has_sold = True
    # 4、卖出完成后，实盘环境等待6秒，让资金到账
    if has_sold and context.run_params.type == 'sim_trade':
        time.sleep(6)
    if context.portfolio.available_cash > 1000:
        cash = context.portfolio.available_cash
        last_price = current_data[etf_worst].last_price
        num = cash / last_price if last_price > 0 else 0
        if num >= 100:
            print(f" === 【符合条件】买入收益最弱的{etf_worst}，涨幅:{ret_worst:.2%}")
            o = order_value(etf_worst, cash)
            if o and o.filled > 0:
                name = get_security_info(etf_worst).display_name
                print(f"{name}【{etf_worst[:6]}】，已下单{o.amount}股，已买入{o.filled}股，平均价格：{o.price}")
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
