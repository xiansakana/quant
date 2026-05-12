# 克隆自聚宽文章：https://www.joinquant.com/post/70394
# 标题：ETF 300轮动（年化60%）：从原理到实战的全面解析
# 作者：大山深处

# 标题：ETF 300轮动模型
# 作者：王巨明
# 思路：
#       1、假定ETF 300指数基金每一分钟的价值应相等，如果因市场原因产生偏差，就有机会获利 
#       2、优选的ETF 300指数基金(初始账户为空）
#       3、每分钟计算这些ETF 300指数基金的涨跌幅
#       4、如果持仓ETF的涨幅 - 最弱ETF的涨幅 > 0.7%，则卖出该ETF，并买入最弱ETF
#       5、解决部分成交的问题：每分钟取消所有未完成订单，重新判断与下单
#
# 日期：2026-4-29
# v2 修复：
#       1、移除 g.is_traded 每日限制，保持分钟级持续轮动（原设计意图有误）
#       2、context.run_params == 'sim_trade' 改为 context.run_params.type == 'sim_trade'
#       3、买入日志"已卖出"改为"已买入"
# v3 新增：
#       1、扩充ETF池，新增15只沪深300ETF
#       2、过滤时增加 None 判断，避免代码错误或未上市的ETF导致崩溃
# v4 优化：
#       1、先确定目标ETF，若已持有且无需卖出其他仓位，直接跳过，节省手续费
#       2、过滤停牌和价格异常的ETF，避免计算错误
#       3、买入逻辑优化，显示可用资金、预计买入股数，价格保留3位小数
#       4、增加资金不足提示，日志更详细清晰
#       5、修正阈值注释与实际值一致（0.7%）
##
## 导入函数库
import numpy as np
import pandas as pd
import time
##
## 初始化函数，设定基准等等
def initialize(context):
    # 设定基准，选用创业板指数
    set_benchmark('399006.XSHE')
    # 开启避免未来数据的模式
    set_option("avoid_future_data", True)
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 设置滑点
    set_slippage(FixedSlippage(0.01))
    # 调试时必须注释下面语句；调试完成后，开启下面语句，减少日志内容
    log.set_level('order', 'error')
    # 设置成交比例，即每日或每分钟内的成交量的20%【比较合理】
    set_option('order_volume_ratio', 1.00)
    # 设置交易费用
    set_order_cost(OrderCost(close_tax=0, open_commission=0.00025, close_commission=0.00025, min_commission=0), type='fund')
    # ETF 300指数基金池（原9只 + 新增15只）
    g.etf_pool = [
        '159908.XSHE',  # 上市2011-06-01，基金规模  45.62亿元(2026-4-14) 创业板ETF博时
        '159915.XSHE',  # 上市2011-09-20，基金规模 896.75亿元(2026-4-14) 创业板ETF易方达
        '159810.XSHE',  # 上市2021-01-18，基金规模   8.96亿元(2026-4-14) 创业板ETF浦银安盛
        '159247.XSHE',  # 上市2022-06-06，基金规模   5.23亿元(2026-4-14) 创业板ETF汇添富
        '159948.XSHE',  # 上市2015-02-02，基金规模 126.37亿元(2026-4-14) 创业板ETF南方
        '159952.XSHE',  # 上市2015-04-22，基金规模  72.19亿元(2026-4-14) 创业板ETF广发
        '159957.XSHE',  # 上市2015-06-16，基金规模  68.44亿元(2026-4-14) 创业板ETF华夏
        '159958.XSHE',  # 上市2015-06-16，基金规模  43.51亿元(2026-4-14) 创业板ETF工银瑞信
        '159956.XSHE',  # 上市2015-06-08，基金规模  29.76亿元(2026-4-14) 创业板ETF建信
        '159964.XSHE',  # 上市2016-01-08，基金规模  16.82亿元(2026-4-14) 创业板ETF平安
        '159971.XSHE',  # 上市2017-01-23，基金规模  25.38亿元(2026-4-14) 创业板ETF富国
        '159977.XSHE',  # 上市2018-01-16，基金规模  32.69亿元(2026-4-14) 创业板ETF天弘
        '159821.XSHE',  # 上市2021-03-12，基金规模   6.75亿元(2026-4-14) 创业板ETF中银证券
        '159205.XSHE',  # 上市2021-06-28，基金规模 192.48亿元(2026-4-14) 创业板ETF东财
        ]
    # ETF列表（直接使用池，不过滤上市时间）
    g.etf_list = g.etf_pool
    # 昨日的收盘价，在before_trading_start计算
    g.yest_close_df = pd.DataFrame()
    # 动态阈值参数
    g.bull_threshold = 1.0/100   # 牛市阈值：1.0%
    g.bear_threshold = 1.8/100   # 熊市阈值：1.8%
    g.ret_threshold = g.bull_threshold  # 初始使用牛市阈值
    g.ma200 = None  # MA200值，用于判断牛熊市
##
## 开盘前运行
def before_trading_start(context):
    # 所有ETF昨日收盘价
    g.yest_close_df = history(1, '1d', 'close', g.etf_list)
    # 计算基准指数的MA200，用于判断牛熊市
    close_prices = attribute_history('399006.XSHE', 200, '1d', 'close')
    if len(close_prices) >= 200:
        g.ma200 = close_prices['close'].mean()
    else:
        g.ma200 = None
    
    # 开盘时打印市场状态
    if g.ma200 is not None:
        current_close = get_current_data()['399006.XSHE'].last_price
        if current_close is not None:
            market_status = "牛市" if current_close > g.ma200 else "熊市"
            g.ret_threshold = g.bull_threshold if current_close > g.ma200 else g.bear_threshold
            print(f" === 【市场状态】{market_status}，创业板指数{current_close:.2f}，MA200:{g.ma200:.2f}，阈值:{g.ret_threshold*100:.1f}%")
##
## 本策略在回测时，应按分钟回测
def handle_data(context, data):
    # 检查是否可以交易（自动取消未完成订单）
    if not is_tradeable(context):
        return
    # 如果没有符合条件的ETF, 则跳过
    if len(g.etf_list) == 0:
        return
    # 1、计算当前各ETF的涨跌幅度，过滤停牌或异常数据
    current_data = get_current_data()
    ret_dict = {}
    for etf in g.etf_list:
        last_price = current_data[etf].last_price
        yesterday_close = g.yest_close_df[etf][0]
        # 过滤停牌、异常价格
        if last_price is None or last_price <= 0 or yesterday_close <= 0 or current_data[etf].paused:
            continue
        ret_dict[etf] = (last_price - yesterday_close) / yesterday_close
    # 如果没有可交易的ETF，跳过
    if len(ret_dict) == 0:
        return
    # 2、找出涨幅最小（最弱）的ETF
    sorted_list = sorted(ret_dict.items(), key=lambda x: x[1])
    etf_worst = sorted_list[0][0]
    ret_worst = sorted_list[0][1]
    already_hold_worst = (
        etf_worst in context.portfolio.positions and
        context.portfolio.positions[etf_worst].closeable_amount > 0
    )
    # 4、卖出符合条件的ETF（排除最弱ETF本身）
    has_sold = False
    for etf in g.etf_list:
        if etf == etf_worst:
            continue
        if etf in context.portfolio.positions:
            pos = context.portfolio.positions[etf]
            if pos.closeable_amount > 0:
                ret_hold = ret_dict.get(etf)
                if ret_hold is None:  # 该ETF可能停牌或异常，跳过
                    continue
                delta = ret_hold - ret_worst
                if delta > g.ret_threshold:
                    print(f" === 【符合条件】卖出持有的{etf}，涨幅:{ret_hold:.2%}，买入收益最弱的{etf_worst}:{ret_worst:.2%}，差值={delta:.2%}>{g.ret_threshold:.2%}")
                    o = order_target_value(etf, 0)
                    if o and o.filled > 0:
                        name = get_security_info(etf).display_name
                        print(f"{name}【{etf[:6]}】，已下单{o.amount}股，已卖出{o.filled}股，平均价格：{o.price}")
                    has_sold = True
    # 5、若已持有最弱ETF且本轮没有卖出操作，说明仓位已在最优标的上，无需换仓
    if already_hold_worst and not has_sold:
        pos = context.portfolio.positions[etf_worst]
        name = get_security_info(etf_worst).display_name
        second_worst = sorted_list[1][0] if len(sorted_list) > 1 else None
        second_ret = sorted_list[1][1] if len(sorted_list) > 1 else 0
        gap = second_ret - ret_worst
        print(f" === 【无需换仓】已持有最弱ETF {name}【{etf_worst[:6]}】"
              f"，持仓{pos.closeable_amount}股"
              f"，涨幅:{ret_worst:.2%}"
              f"，次弱:{second_worst[:6] if second_worst else 'N/A'}({second_ret:.2%})"
              f"，差值={gap:.2%} < 阈值{g.ret_threshold:.2%}")
        return
    # 6、卖出完成后，实盘环境等待6秒，让资金到账
    if has_sold and context.run_params.type == 'sim_trade':
        time.sleep(6)
    # 7、买入最弱ETF（使用全部可用资金）
    cash = context.portfolio.available_cash
    if cash > 1000:
        last_price = current_data[etf_worst].last_price
        if last_price is None or last_price <= 0:
            print(f" === 【警告】最弱ETF {etf_worst} 价格异常，无法买入")
            return
        num = int(cash / last_price / 100) * 100  # 向下取整到100股
        if num >= 100:
            print(f" === 【符合条件】买入收益最弱的{etf_worst}，涨幅:{ret_worst:.2%}，可用资金:{cash:.2f}元，预计买入{num}股")
            o = order_value(etf_worst, cash)
            if o and o.filled > 0:
                name = get_security_info(etf_worst).display_name
                print(f"{name}【{etf_worst[:6]}】，已下单{o.amount}股，已买入{o.filled}股，平均价格：{o.price:.3f}元")
        else:
            print(f" === 【资金不足】可用资金{cash:.2f}元，不足100股({last_price * 100:.2f}元)")
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
