# 聚宽分钟回测；同指数ETF相对价差轮动，不是无风险申赎套利。
# 参考 ETF300/etf300-v4.py 和 ETF创业板/etf创业板.py。
from jqdata import *
import numpy as np
import datetime as dt


def initialize(context):
    set_benchmark('159941.XSHE')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_option('order_volume_ratio', 0.05)
    # 聚宽FixedSlippage是双边总价差：0.004对应买卖各2个最小价位。
    set_slippage(FixedSlippage(0.004))
    set_order_cost(OrderCost(open_tax=0, close_tax=0,
                   open_commission=0.00025, close_commission=0.00025,
                   min_commission=5), type='fund')
    log.set_level('order', 'error')
    g.pool = ['513100.XSHG', '513300.XSHG', '513110.XSHG',
              '513390.XSHG', '513870.XSHG', '159941.XSHE',
              '159632.XSHE', '159659.XSHE', '159696.XSHE',
              '159501.XSHE', '159513.XSHE']
    g.threshold = 0.01
    g.signal_mode = 'rolling'  # 2024训练期选择；2025、2026留出期锁定参数
    g.trend_filter = False  # 只使用历史价格；独立对照，不以留出期调参
    g.max_switches = 6
    g.min_hold_minutes = 15
    g.participation = 0.05
    g.cash_reserve = 0.01
    g.min_ticket_value = 10000  # 避免大量碎单触发最低佣金
    g.active = []
    g.base = {}
    g.target = None
    g.pending_since = None
    g.last_switch = None
    g.switches = 0
    g.order_count = 0
    g.fill_count = 0
    g.total_switches = 0
    run_daily(prepare, time='before_open')
    run_daily(report, time='after_close')


def prepare(context):
    g.switches = 0
    g.target = None
    g.pending_since = None
    # 按回测时点过滤上市时间，不把未上市基金加入历史样本。
    cutoff = context.current_dt.date() - dt.timedelta(days=60)
    candidates = []
    for s in g.pool:
        info = get_security_info(s)
        if info is not None and info.start_date <= cutoff:
            candidates.append(s)
    if not candidates:
        g.active = []
        return
    closes = history(220, '1d', 'close', candidates, df=True)
    money = history(20, '1d', 'money', candidates, df=True)
    g.active = [s for s in candidates if s in closes and
                closes[s].dropna().shape[0] >= 20 and
                money[s].tail(20).mean() >= 10000000 and
                np.isfinite(closes[s].iloc[-1]) and closes[s].iloc[-1] > 0]
    g.base = {}
    if not g.active:
        return
    # 所有数据截至前一交易日。rolling模式用共同市场涨跌扣除后的历史中位数。
    daily = closes[g.active].tail(20)
    relative = np.log(daily).sub(np.log(daily).median(axis=1), axis=0)
    for s in g.active:
        g.base[s] = (float(closes[s].iloc[-1]) if g.signal_mode == 'daily'
                     else float(np.exp(relative[s].median())))
    if g.signal_mode == 'nav':
        # 保守滞后至少5个A股交易日；不能把尚未公布的昨日QDII净值当成已知。
        # 比较共同净值日期上的P/NAV，只是相对估值，不能作为实时绝对溢价。
        safe_days = get_trade_days(end_date=context.previous_date, count=6)
        nav_end = safe_days[0]
        nav = get_extras('unit_net_value', g.active,
                         start_date=nav_end-dt.timedelta(days=30), end_date=nav_end, df=True)
        valid = [s for s in g.active if s in nav and nav[s].dropna().shape[0] > 0]
        common = nav[valid].replace([np.inf, -np.inf], np.nan).dropna() if valid else nav.iloc[0:0]
        if common.empty:
            g.active, g.base = [], {}
            return
        nav_row = common.iloc[-1]
        g.active = [s for s in valid if nav_row[s] > 0 and
                    0.6 < float(closes[s].iloc[-1])/float(nav_row[s]) < 1.5]
        g.base = {s: float(nav_row[s]) for s in g.active}
        if context.current_dt.day <= 3:
            log.info('NAV_ASOF %s safe_end=%s' % (common.index[-1], nav_end))
    anchor = closes['159941.XSHE'].dropna() if '159941.XSHE' in closes else closes[g.active[0]].dropna()
    g.risk_on = (not g.trend_filter or
                 (len(anchor) >= 200 and anchor.iloc[-1] > anchor.tail(200).mean()))
    if context.current_dt.day <= 3:
        log.info('UNIVERSE %s %s risk_on=%s' % (context.current_dt.date(), g.active, g.risk_on))


def market_snapshot():
    current = get_current_data()
    if not g.active:
        return {}, {}, current
    # history不包含当前分钟，使用已完成的分钟价格/成交量。
    prices = history(1, '1m', 'close', g.active, df=False)
    volumes = history(3, '1m', 'volume', g.active, df=False)
    quotes, caps = {}, {}
    for s in g.active:
        c = current[s]
        p = float(prices[s][-1])
        v = np.asarray(volumes[s], dtype=float)
        if c.paused or not np.isfinite(p) or p <= 0 or len(v) < 3:
            continue
        # 避免零成交、过期价格和涨跌停附近的不可成交价差。
        if v[-1] <= 0 or p >= c.high_limit - 0.003 or p <= c.low_limit + 0.003:
            continue
        cap = int(min(v[-1], np.mean(v)) * g.participation / 100) * 100
        if cap < 100 or cap * p < g.min_ticket_value:
            continue
        quotes[s], caps[s] = p, cap
    return quotes, caps, current


def send_order(context, security, amount, price, cap):
    # 买入100份一手；卖出全部可卖余额时允许处理拆分后的零股。
    # 限价只允许偏离已完成分钟报价最多3个价位。
    amount = (int(amount) if amount < 0 and abs(amount) <= cap else
              int(min(abs(amount), cap) / 100) * 100 * (1 if amount > 0 else -1))
    if not amount:
        return
    limit = round(price + (0.003 if amount > 0 else -0.003), 3)
    o = order(security, amount, style=LimitOrderStyle(limit))
    if o is not None:
        g.order_count += 1


def execute_target(context, quotes, caps):
    # 先逐笔卖出；后续分钟确认旧仓已清空，才使用实际可用资金买新ETF。
    old = [(s, p) for s, p in context.portfolio.positions.items()
           if p.total_amount > 0 and s != g.target]
    if old:
        for s, p in old:
            if s in quotes and p.closeable_amount > 0:
                send_order(context, s, -p.closeable_amount, quotes[s], caps[s])
        return
    if g.target is None or g.target not in quotes:
        return
    price = quotes[g.target]
    cash = max(0, context.portfolio.available_cash -
               context.portfolio.total_value * g.cash_reserve - 10)
    amount = int(cash / (price + 0.003) / 1.00025 / 100) * 100
    if amount >= 100:
        send_order(context, g.target, amount, price, caps[g.target])


def handle_data(context, data):
    hm = context.current_dt.strftime('%H:%M')
    if hm < '09:40' or hm > '14:50' or '11:30' <= hm < '13:05':
        return
    # 保持一分钟订单寿命；撤单后仍以实际持仓/可用金额驱动，避免把委托当成交。
    orders = get_open_orders()
    if orders:
        for o in orders.values():
            cancel_order(o)
        return
    if g.pending_since is None and context.current_dt.minute % 5 != 0:
        return
    quotes, caps, current = market_snapshot()
    held = [s for s, p in context.portfolio.positions.items() if p.total_amount > 0]
    if not getattr(g, 'risk_on', True):
        g.target = None
        execute_target(context, quotes, caps)
        return
    # 有转换任务时只执行既定目标；最长30分钟，失败后回到实际剩余仓位。
    if g.pending_since is not None:
        if (context.current_dt - g.pending_since).total_seconds() > 1800:
            g.pending_since = None
            g.target = held[0] if held else None
        else:
            execute_target(context, quotes, caps)
            if held == [g.target] and context.portfolio.available_cash < context.portfolio.total_value * 0.03:
                g.pending_since = None
            return
    if context.current_dt.minute % 5 != 0 or len(quotes) < 2:
        return
    score = {s: np.log(p / g.base[s]) for s, p in quotes.items()}
    target = min(score, key=score.get)
    if not held:
        g.target = target
        g.pending_since = context.current_dt
        execute_target(context, quotes, caps)
        return
    if len(held) != 1 or held[0] not in score:
        return
    security = held[0]
    if target == security:
        g.target = target
        execute_target(context, quotes, caps)
        return
    if g.switches >= g.max_switches:
        return
    if g.last_switch is not None and (context.current_dt - g.last_switch).total_seconds() < 60*g.min_hold_minutes:
        return
    # 卖出+买入的佣金、最小费用、双边滑点及额外3bp安全边际。
    value = max(1, context.portfolio.positions[security].value)
    sell_slices = np.ceil(value / (caps[security] * quotes[security]))
    buy_slices = np.ceil(value / (caps[target] * quotes[target]))
    commission = max(0.0005, 5.0 * (sell_slices + buy_slices) / value)
    costs = commission + 0.002/quotes[security] + 0.002/quotes[target] + 0.0003
    gap = score[security] - score[target]
    if gap < max(g.threshold, costs * 1.5):
        return
    g.target = target
    g.pending_since = context.current_dt
    g.last_switch = context.current_dt
    g.switches += 1
    g.total_switches += 1
    log.info('SWITCH %s -> %s gap=%.4f costs=%.4f' % (security, target, gap, costs))
    execute_target(context, quotes, caps)


def report(context):
    for o in get_open_orders().values():
        cancel_order(o)
    g.fill_count += len(get_trades())
    record(switches=g.total_switches, orders=g.order_count,
           fills=g.fill_count, exposure=1-context.portfolio.available_cash/context.portfolio.total_value)
    if context.current_dt.day <= 3:
        log.info('AUDIT date=%s value=%.2f switches=%s orders=%s fills=%s' %
                 (context.current_dt.date(), context.portfolio.total_value,
                  g.total_switches, g.order_count, g.fill_count))
