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
    # 设定基准，选用沪深300指数
    set_benchmark('000300.XSHG')
    # 开启避免未来数据的模式
    set_option("avoid_future_data", True)
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 设置滑点
    set_slippage(FixedSlippage(0.005))
    # 调试时必须注释下面语句；调试完成后，开启下面语句，减少日志内容
    log.set_level('order', 'error')
    # 设置成交比例，即每日或每分钟内的成交量的20%【比较合理】
    set_option('order_volume_ratio', 0.20)
    # 设置交易费用
    set_order_cost(OrderCost(close_tax=0, open_commission=0.00025, close_commission=0.00025, min_commission=0), type='fund')
    # ETF 300指数基金池（原9只 + 新增15只）
    g.etf_pool = [
        # 原有9只
        '510300.XSHG',  # 上市2012-05-28，基金规模2067.00亿元(2026-4-14) 沪深300ETF华泰柏瑞
        '510310.XSHG',  # 上市2013-03-25，基金规模1427.00亿元(2026-4-14) 沪深300ETF易方达
        '159919.XSHE',  # 上市2012-05-28，基金规模 962.30亿元(2026-4-14) 沪深300ETF嘉实
        '510330.XSHG',  # 上市2013-01-16，基金规模 944.40亿元(2026-4-14) 沪深300ETF华夏
        '515330.XSHG',  # 上市2019-12-26，基金规模  88.34亿元(2026-4-14) 沪深300ETF天弘
        '515380.XSHG',  # 上市2020-03-23，基金规模  35.85亿元(2026-4-14) 沪深300ETF泰康
        '510350.XSHG',  # 上市2019-08-16，基金规模  34.39亿元(2026-4-14) 沪深300ETF工银
        '510360.XSHG',  # 上市2015-09-09，基金规模  30.22亿元(2026-4-14) 沪深300ETF广发
        '159925.XSHE',  # 上市2013-04-11，基金规模  26.22亿元(2026-4-14) 沪深300ETF南方
        # 新增15只
        '515390.XSHG',  # 上市2020-01-10，基金规模  9.30亿元(2026-4-14) 沪深300ETF华安
        '515130.XSHG',  # 上市2020-05-11，基金规模  1.16亿元(2026-4-14) 沪深300ETF博时
        '159673.XSHE',  # 上市2023-06-21，基金规模  18.06亿元(2026-4-14) 沪深300ETF鹏华
        '159300.XSHE',  # 上市2024-05-23，基金规模  11.98亿元(2026-4-14) 沪深300ETF富国
        '159330.XSHE',  # 上市2024-08-19，基金规模   5.58亿元(2026-4-14) 沪深300ETF东财
        '561930.XSHG',  # 上市2024-09-20，基金规模   1.84亿元(2026-4-14) 沪深300ETF招商
        '159393.XSHE',  # 上市2025-03-10，基金规模   2.85亿元(2026-4-14) 沪深300ETF万家
        '510320.XSHG',  # 上市2025-04-25，基金规模   6.45亿元(2026-4-14) 沪深300ETF中金
        '510390.XSHG',  # 上市2018-01-10，基金规模   4.86亿元(2026-4-14) 沪深300ETF平安
        '510380.XSHG',  # 上市2020-07-17，基金规模   2.15亿元(2026-4-14) 沪深300ETF国寿
        '515360.XSHG',  # 上市2020-06-12，基金规模   1.52亿元(2026-4-14) 沪深300ETF方正富邦
        '515660.XSHG',  # 上市2021-01-18，基金规模   2.03亿元(2026-4-14) 沪深300ETF国联安
        '515350.XSHG',  # 上市2020-05-28，基金规模   1.38亿元(2026-4-14) 沪深300ETF民生加银
        '510370.XSHG',  # 上市2020-04-28，基金规模   1.92亿元(2026-4-14) 沪深300ETF兴业
        '563520.XSHG',  # 上市2021-04-28，基金规模   3.21亿元(2026-4-14) 沪深300ETF永赢
        ]
    # 过滤上市不到1年的ETF，在before_trading_start计算
    g.etf_list = []
    # 昨日的收盘价，在before_trading_start计算
    g.yest_close_df = pd.DataFrame()
    # 与最佳ETF涨跌幅的差值阈值，取0.7%
    g.ret_threshold = 0.7/100
##
## 开盘前运行
def before_trading_start(context):
    # 1、过滤上市不到1年的ETF
    date_limit = context.current_dt.date() - pd.Timedelta(days=365)
    g.etf_list = [etf for etf in g.etf_pool if get_security_info(etf) is not None and get_security_info(etf).start_date < date_limit]
    # 所有ETF 300昨日收盘价
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
    # 3、检查是否已持有目标ETF（最弱ETF），若已持有且无其他需卖出的仓位，则跳过
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
