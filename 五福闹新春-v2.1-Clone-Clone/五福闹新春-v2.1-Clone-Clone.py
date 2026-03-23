# 克隆自聚宽文章：https://www.joinquant.com/post/4296
# 标题：股指期货跨期套利策略
# 作者：JoinQuant量化课堂

# 克隆自聚宽文章：https://www.joinquant.com/post/67254
# 标题：【五福闹新春】v2.1-跟许愿机一样把您们需要的功能都加上
# 作者：烟花三月ETF

import numpy as np
import math
import pandas as pd
from jqdata import *

def initialize(context):
    """
    策略初始化函数，在回测或模拟交易开始前运行一次。
    设置基础参数、基准、成本、滑点和日志级别。
    """
    # 设置选项，避免使用未来数据，并使用真实价格交易
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    
    # 设置基金的滑点为万分之一
    set_slippage(PriceRelatedSlippage(0.0001), type="fund")
    
    # 设置基金的交易成本：无印花税，买卖佣金均为万分之一，最低5元
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0001, close_commission=0.0001, close_today_commission=0.0001, min_commission=5,), type="fund")
    
    # 设置日志输出级别，减少订单和系统信息，保留策略信息
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'info')
    
    # 记录初始化完成日志
    log.info("增强版策略初始化完成！")
    
    # 设置策略的业绩基准为沪深300ETF
    set_benchmark("510300.XSHG")

    # 定义用于轮动的核心ETF投资池
    g.etf_pool = [
#大宗商品ETF：
        '518880.XSHG',  # (黄金ETF) [ETF]-成交额：54.60亿元-上市日期：2013-07-29
        '161226.XSHE',  # (国投白银LOF) [LOF]-成交额：21.54亿元-上市日期：2015-08-17
        '159980.XSHE',  # (有色ETF大成) [ETF]-成交额：23.57亿元-上市日期：2019-12-24
        '501018.XSHG',  # (南方原油ETF) [LOF]-成交额：1.34亿元-上市日期：2016-06-28
        '159985.XSHE',  # (豆粕ETF) [ETF]-成交额：0.67亿元

#海外ETF：       
        '513100.XSHG',  # (纳指ETF) [ETF]-成交额：4.24亿元-上市日期：2013-05-15
        '513500.XSHG',  # (标普500) [ETF]-成交额：2.22亿元-上市日期：2014-01-15
        '513400.XSHG',  # (道琼斯) [ETF]-成交额：1.09亿元-上市日期：2024-02-02
        '159509.XSHE',  # (纳指科技ETF景顺) [ETF]-成交额：5.65亿元-上市日期：2023-08-08
        '159518.XSHE',  # (标普油气ETF嘉实) [ETF]-成交额：5.35亿元-上市日期：2023-11-15
        '159529.XSHE',  # (标普消费ETF) [ETF]-成交额：2.25亿元-上市日期：2024-02-02
        '513290.XSHG',  # (纳指生物) [ETF]-成交额：1.28亿元-上市日期：2022-08-29
        '520830.XSHG',  # (沙特ETF) [ETF]-成交额：1.16亿元-上市日期：2024-07-16
        '513520.XSHG',  # (日经ETF) [ETF]-成交额：1.11亿元-上市日期：2019-06-25
        '513030.XSHG',  # (德国ETF) [ETF]-成交额：0.77亿元

#港股ETF：
        '513090.XSHG',  # (香港证券) [ETF]-成交额：68.32亿元-上市日期：2020-03-26
        '513180.XSHG',  # (恒指科技) [ETF]-成交额：61.72亿元-上市日期：2021-05-25
        '513120.XSHG',  # (HK创新药) [ETF]-成交额：48.95亿元-上市日期：2022-07-12
        '513330.XSHG',  # (恒生互联) [ETF]-成交额：37.01亿元-上市日期：2021-02-08
        '513750.XSHG',  # (港股非银) [ETF]-成交额：23.06亿元-上市日期：2023-11-27
        '159892.XSHE',  # (恒生医药ETF) [ETF]-成交额：12.25亿元-上市日期：2021-10-19
        '159605.XSHE',  # (中概互联ETF) [ETF]-成交额：5.14亿元-上市日期：2021-12-02
        '513190.XSHG',  # (H股金融) [ETF]-成交额：5.07亿元-上市日期：2023-10-11
        '159502.XSHE',  # (标普生物科技ETF嘉实) [ETF]-成交额：4.00亿元-上市日期：2024-01-10
        '510900.XSHG',  # (恒生中国) [ETF]-成交额：3.73亿元-上市日期：2012-10-22
        '513630.XSHG',  # (香港红利) [ETF]-成交额：3.69亿元-上市日期：2023-12-08
        '159323.XSHE',  # (港股通汽车ETF) [ETF]-成交额：2.02亿元-上市日期：2025-01-08
        '513970.XSHG',  # (恒生消费) [ETF]-成交额：1.25亿元-上市日期：2023-04-21
        
#行业ETF：
        '513310.XSHG',  # (中韩芯片) [ETF]-成交额：38.68亿元-上市日期：2022-12-22
        '588200.XSHG',  # (科创芯片) [ETF]-成交额：37.94亿元-上市日期：2022-10-26
        '159852.XSHE',  # (软件ETF) [ETF]-成交额：36.26亿元-上市日期：2021-02-09
        '512880.XSHG',  # (证券ETF) [ETF]-成交额：34.01亿元-上市日期：2016-08-08
        '159206.XSHE',  # (卫星ETF) [ETF]-成交额：32.60亿元-上市日期：2025-03-14
        '512400.XSHG',  # (有色金属ETF) [ETF]-成交额：31.27亿元-上市日期：2017-09-01
        '512980.XSHG',  # (传媒ETF) [ETF]-成交额：30.96亿元-上市日期：2018-01-19
        '159516.XSHE',  # (半导体设备ETF) [ETF]-成交额：28.21亿元-上市日期：2023-07-27
        '512480.XSHG',  # (半导体) [ETF]-成交额：16.29亿元-上市日期：2019-06-12
        '515880.XSHG',  # (通信ETF) [ETF]-成交额：13.46亿元-上市日期：2019-09-06
        '562500.XSHG',  # (机器人) [ETF]-成交额：12.92亿元-上市日期：2021-12-29
        '159218.XSHE',  # (卫星产业ETF) [ETF]-成交额：12.74亿元-上市日期：2025-05-22
        '159869.XSHE',  # (游戏ETF) [ETF]-成交额：12.42亿元-上市日期：2021-03-05
        '159870.XSHE',  # (化工ETF) [ETF]-成交额：12.30亿元-上市日期：2021-03-03
        '159326.XSHE',  # (电网设备ETF) [ETF]-成交额：12.02亿元-上市日期：2024-09-09
        '159851.XSHE',  # (金融科技ETF) [ETF]-成交额：11.79亿元-上市日期：2021-03-19
        '560860.XSHG',  # (工业有色) [ETF]-成交额：11.71亿元-上市日期：2023-03-13
        '159363.XSHE',  # (创业板人工智能ETF华宝) [ETF]-成交额：10.63亿元-上市日期：2024-12-16
        '588170.XSHG',  # (科创半导) [ETF]-成交额：10.28亿元-上市日期：2025-04-08
        '159755.XSHE',  # (电池ETF) [ETF]-成交额：10.02亿元-上市日期：2021-06-24
        '512170.XSHG',  # (医疗ETF) [ETF]-成交额：9.54亿元-上市日期：2019-06-17
        '512800.XSHG',  # (银行ETF) [ETF]-成交额：9.48亿元-上市日期：2017-08-03
        '159819.XSHE',  # (人工智能ETF易方达) [ETF]-成交额：9.40亿元-上市日期：2020-09-23
        '512710.XSHG',  # (军工龙头) [ETF]-成交额：9.39亿元-上市日期：2019-08-26
        '159638.XSHE',  # (高端装备ETF嘉实) [ETF]-成交额：8.92亿元-上市日期：2022-08-12
        '517520.XSHG',  # (黄金股) [ETF]-成交额：8.73亿元-上市日期：2023-11-01
        '515980.XSHG',  # (人工智能) [ETF]-成交额：8.73亿元-上市日期：2020-02-10
        '159995.XSHE',  # (芯片ETF) [ETF]-成交额：8.45亿元-上市日期：2020-02-10
        '159227.XSHE',  # (航空航天ETF) [ETF]-成交额：8.42亿元-上市日期：2025-05-16
        '512660.XSHG',  # (军工ETF) [ETF]-成交额：7.78亿元-上市日期：2016-08-08
        '512690.XSHG',  # (酒ETF) [ETF]-成交额：6.74亿元-上市日期：2019-05-06
        '516150.XSHG',  # (稀土基金) [ETF]-成交额：6.41亿元-上市日期：2021-03-17
        '512890.XSHG',  # (红利低波) [ETF]-成交额：6.03亿元-上市日期：2019-01-18
        '588790.XSHG',  # (科创智能) [ETF]-成交额：5.92亿元-上市日期：2025-01-09
        '159992.XSHE',  # (创新药ETF) [ETF]-成交额：5.63亿元-上市日期：2020-04-10
        '512070.XSHG',  # (证券保险) [ETF]-成交额：5.50亿元-上市日期：2014-07-18
        '562800.XSHG',  # (稀有金属) [ETF]-成交额：5.49亿元-上市日期：2021-09-27
        '512010.XSHG',  # (医药ETF) [ETF]-成交额：5.22亿元-上市日期：2013-10-28
        '516010.XSHG',  # (游戏ETF) [ETF]-成交额：5.11亿元-上市日期：2021-03-05
        '515790.XSHG',  # (光伏ETF) [ETF]-成交额：4.95亿元-上市日期：2020-12-18
        '510880.XSHG',  # (红利ETF) [ETF]-成交额：4.90亿元-上市日期：2007-01-18
        '159928.XSHE',  # (消费ETF) [ETF]-成交额：4.71亿元-上市日期：2013-09-16
        '159883.XSHE',  # (医疗器械ETF) [ETF]-成交额：4.44亿元-上市日期：2021-04-30
        '159998.XSHE',  # (计算机ETF) [ETF]-成交额：3.93亿元-上市日期：2020-04-13
        '515220.XSHG',  # (煤炭ETF) [ETF]-成交额：3.92亿元-上市日期：2020-03-02
        '561980.XSHG',  # (芯片设备) [ETF]-成交额：3.89亿元-上市日期：2023-09-01
        '515400.XSHG',  # (大数据) [ETF]-成交额：3.54亿元-上市日期：2021-01-20
        '515120.XSHG',  # (创新药) [ETF]-成交额：3.54亿元-上市日期：2021-01-04
        '159967.XSHE',  # (创业板成长ETF) [ETF]-成交额：3.27亿元-上市日期：2019-07-15
        '159566.XSHE',  # (储能电池ETF易方达) [ETF]-成交额：3.05亿元-上市日期：2024-02-08
        '515050.XSHG',  # (5GETF) [ETF]-成交额：3.04亿元-上市日期：2019-10-16
        '516510.XSHG',  # (云计算ETF) [ETF]-成交额：2.95亿元-上市日期：2021-04-07
        '159256.XSHE',  # (创业板软件ETF华夏) [ETF]-成交额：2.89亿元-上市日期：2025-08-04
        '159766.XSHE',  # (旅游ETF) [ETF]-成交额：2.57亿元-上市日期：2021-07-23
        '512200.XSHG',  # (地产ETF) [ETF]-成交额：2.53亿元-上市日期：2017-09-25
        '513350.XSHG',  # (油气ETF) [ETF]-成交额：2.48亿元-上市日期：2023-11-28
        '159583.XSHE',  # (通信设备ETF) [ETF]-成交额：2.47亿元-上市日期：2024-07-08
        '159732.XSHE',  # (消费电子ETF) [ETF]-成交额：2.39亿元-上市日期：2021-08-23
        '516160.XSHG',  # (新能源) [ETF]-成交额：2.26亿元-上市日期：2021-02-04
        '516520.XSHG',  # (智能驾驶) [ETF]-成交额：2.22亿元-上市日期：2021-03-01
        '562590.XSHG',  # (半导材料) [ETF]-成交额：1.94亿元-上市日期：2023-10-18
        '515030.XSHG',  # (新汽车) [ETF]-成交额：1.93亿元-上市日期：2020-03-04
        '512670.XSHG',  # (国防ETF) [ETF]-成交额：1.84亿元-上市日期：2019-08-01
        '561330.XSHG',  # (矿业ETF) [ETF]-成交额：1.81亿元-上市日期：2022-11-01
        '516190.XSHG',  # (文娱ETF) [ETF]-成交额：1.67亿元-上市日期：2021-09-17
        '159840.XSHE',  # (锂电池ETF工银) [ETF]-成交额：1.61亿元-上市日期：2021-08-20
        '159611.XSHE',  # (电力ETF) [ETF]-成交额：1.52亿元-上市日期：2022-01-07
        '159981.XSHE',  # (能源化工ETF) [ETF]-成交额：1.48亿元-上市日期：2020-01-17
        '159865.XSHE',  # (养殖ETF) [ETF]-成交额：1.40亿元-上市日期：2021-03-08
        '561360.XSHG',  # (石油ETF) [ETF]-成交额：1.36亿元-上市日期：2023-10-31
        '159667.XSHE',  # (工业母机ETF) [ETF]-成交额：1.32亿元-上市日期：2022-10-26
        '515170.XSHG',  # (食品饮料ETF) [ETF]-成交额：1.30亿元-上市日期：2021-01-13
        '513360.XSHG',  # (教育ETF) [ETF]-成交额：1.09亿元-上市日期：2021-06-17
        '159825.XSHE',  # (农业ETF) [ETF]-成交额：1.05亿元-上市日期：2020-12-29
        '515210.XSHG',  # (钢铁ETF) [ETF]-成交额：1.03亿元-上市日期：2020-03-02
        
#指数ETF：        
        '510500.XSHG',  # (中证500ETF) [ETF]-成交额：263.30亿元-上市日期：2013-03-15
        '510300.XSHG',  # (沪深300ETF) [ETF]-成交额：253.91亿元-上市日期：2012-05-28
        '511380.XSHG',  # (可转债ETF) [ETF]-成交额：165.76亿元-上市日期：2020-04-07
        '159915.XSHE',  # (创业板ETF易方达) [ETF]-成交额：129.05亿元-上市日期：2011-12-09
        '588080.XSHG',  # (科创板50) [ETF]-成交额：123.46亿元-上市日期：2020-11-16
        '512100.XSHG',  # (中证1000ETF) [ETF]-成交额：32.30亿元-上市日期：2016-11-04
        '563300.XSHG',  # (中证2000) [ETF]-成交额：3.34亿元-上市日期：2023-09-14
        '510760.XSHG',  # (上证ETF) [ETF]-成交额：1.10亿元-上市日期：2020-09-09
    ]

    # 核心参数设置
    g.holdings_num = 1  # 同时持有的ETF数量
    g.defensive_etf = "511880.XSHG"  # 防御性ETF，当没有符合动量条件的ETF时买入
    g.safe_haven_etf = '511660.XSHG'  # 分钟级止损触发后，买入避险ETF
    g.min_money = 5000  # 最小交易金额

    # 动量得分相关参数
    g.lookback_days = 25  # 计算动量的回看天数
    g.min_score_threshold = 0  # 动量得分下限
    g.max_score_threshold = 5  # 动量得分上限

    # 短期动量过滤器开关与参数
    g.use_short_momentum_filter = True  # 是否启用短期动量过滤
    g.short_lookback_days = 10  # 短期动量回看天数
    g.short_momentum_threshold = 0.0  # 短期动量阈值

    # R² (决定系数) 过滤器开关与参数
    g.enable_r2_filter = True  # 是否启用R²过滤
    g.r2_threshold = 0.4  # R²阈值，衡量价格走势的稳定性

    # 年化收益率过滤器开关与参数
    g.enable_annualized_return_filter = True  # 是否启用年化收益率过滤
    g.min_annualized_return = 1.0  # 最低年化收益率阈值

    # 均线过滤器开关与参数
    g.enable_ma_filter = True  # 是否启用均线过滤
    g.ma_filter_days = 20  # 均线周期，当前价格需高于此均线

    # 成交量过滤器开关与参数
    g.enable_volume_check = True  # 是否启用成交量过滤
    g.volume_lookback = 5  # 计算平均成交量的回看天数
    g.volume_threshold = 1.0  # 当前成交量与平均成交量的比值阈值

    # 短期风控（日内最大跌幅）开关与参数
    g.enable_loss_filter = True  # 是否启用短期风控过滤
    g.loss = 0.97  # 近三日任意一日跌幅不能低于该比例（即跌幅不超过3%）

    # RSI技术指标过滤器开关与参数
    g.use_rsi_filter = True  # 是否启用RSI过滤
    g.rsi_period = 6  # RSI计算周期
    g.rsi_lookback_days = 1  # 回看最近几天的RSI值
    g.rsi_threshold = 98  # RSI阈值，超过此值可能代表超买

    # 止损机制开关与参数
    g.use_fixed_stop_loss = True  # 是否启用固定比例止损
    g.fixed_stop_loss_threshold = 0.95  # 固定止损比例，跌破成本价的95%时卖出
    g.use_pct_stop_loss = False  # 是否启用当日跌幅止损
    g.pct_stop_loss_threshold = 0.95  # 当日跌幅止损比例，跌破开盘价的95%时卖出
    g.use_atr_stop_loss = False  # 是否启用ATR动态止损
    g.atr_period = 14  # ATR计算周期
    g.atr_multiplier = 2  # ATR倍数，用于计算止损价
    g.atr_trailing_stop = True  # ATR是否为追踪止损
    g.atr_exclude_defensive = True  # ATR止损是否排除防御性ETF

    # 交易冷却期机制开关与参数
    g.sell_cooldown_enabled = False  # 是否启用卖出后冷却期
    g.sell_cooldown_days = 3  # 冷却期天数
    g.cooldown_end_date = None  # 冷却期结束日期

    # 全局状态变量，用于存储持仓相关信息
    g.positions = {}  # 存储持仓数量
    g.position_highs = {}  # 用于追踪ATR追踪止损的最高价
    g.position_stop_prices = {}  # 存储每个持仓的ATR止损价
    g.target_etfs_list = []  # 存储每日筛选出的目标ETF列表

    # 注册每日定时运行的函数
    run_daily(check_positions, time='09:10')   # 盘前检查
    run_daily(etf_sell_trade, time='14:05')    # 14:05 卖出
    run_daily(etf_buy_trade, time='14:06')     # 14:06 买入

    # 注册分钟级别的止损函数，使其在交易时间内每分钟都运行
    for hour in range(9, 15):
        for minute in range(0, 60):
            current_time = "%02d:%02d" % (hour, minute)
            # 在正常的A股交易时间段内注册止损函数
            if ('09:27' < current_time < '11:30') or ('13:00' < current_time < '14:57'):
                run_daily(minute_level_stop_loss, time=current_time)
                run_daily(minute_level_pct_stop_loss, time=current_time)
                run_daily(minute_level_atr_stop_loss, time=current_time)

    # 打印策略初始化完成的详细参数摘要
    log.info(f"""策略参数初始化完成:
=== 过滤条件 ===
- 动量得分过滤: {'启用' if (g.min_score_threshold > -1e9 or g.max_score_threshold < 1e9) else '禁用'} (阈值范围: [{g.min_score_threshold}, {g.max_score_threshold}])
- 短期动量过滤: {'启用' if g.use_short_momentum_filter else '禁用'} (周期: {g.short_lookback_days}天, 阈值 ≥ {g.short_momentum_threshold:.2f})
- R²过滤: {'启用' if g.enable_r2_filter else '禁用'} (阈值 > {g.r2_threshold:.3f})
- 年化收益率过滤: {'启用' if g.enable_annualized_return_filter else '禁用'} (阈值 ≥ {g.min_annualized_return:.2%})
- 均线过滤: {'启用' if g.enable_ma_filter else '禁用'} ({g.ma_filter_days}日均线)
- 成交量过滤: {'启用' if g.enable_volume_check else '禁用'} (近{g.volume_lookback}日均量比 < {g.volume_threshold:.2f})
- 短期风控过滤: {'启用' if g.enable_loss_filter else '禁用'} (近3日单日跌幅 < {1 - g.loss:.1%})
- RSI过滤: {'启用' if g.use_rsi_filter else '禁用'} (周期: {g.rsi_period}, 回看{g.rsi_lookback_days}日, 触发阈值 > {g.rsi_threshold})

=== 止损机制 ===
- 分钟级固定比例止损: {'启用' if g.use_fixed_stop_loss else '禁用'} (成本价 × {g.fixed_stop_loss_threshold:.2%})
- 分钟级当日跌幅止损: {'启用' if g.use_pct_stop_loss else '禁用'} (开盘价 × {g.pct_stop_loss_threshold:.2%})
- 分钟级ATR动态止损: {'启用' if g.use_atr_stop_loss else '禁用'} (ATR周期: {g.atr_period}, 倍数: {g.atr_multiplier}, 跟踪止损: {'是' if g.atr_trailing_stop else '否'})

=== 其他配置 ===
- ETF池大小: {len(g.etf_pool)} 只ETF
- 动量计算周期: {g.lookback_days} 天
- 持仓数量: {g.holdings_num}
- 防御ETF: {g.defensive_etf}
- 冷却期避险ETF: {g.safe_haven_etf}
- 冷却期机制: {'启用' if g.sell_cooldown_enabled else '禁用'} (持续{g.sell_cooldown_days}个交易日)
""")

def calculate_all_metrics_for_etf(context, etf):
    """
    为单个ETF计算所有所需的指标和过滤判断结果。
    这是一个核心计算函数，整合了价格、动量、均线、成交量、风控、RSI等。
    """
    try:
        # 获取ETF名称
        etf_name = get_security_name(etf)
        
        # 计算所需的历史数据长度，确保满足所有指标的最大回看需求
        lookback = max(
            g.lookback_days,
            g.short_lookback_days,
            g.rsi_period + g.rsi_lookback_days,
            g.ma_filter_days,
            g.volume_lookback
        ) + 20
        
        # 获取历史收盘价、最高价、最低价数据
        prices = attribute_history(etf, lookback, '1d', ['close', 'high', 'low'])
        # 获取当前实时数据
        current_data = get_current_data()
        
        # 检查数据是否足够
        if len(prices) < max(g.lookback_days, g.ma_filter_days):
            return None
            
        # 获取当前最新价格
        current_price = current_data[etf].last_price
        # 将当前价格加入历史价格序列，用于后续计算
        price_series = np.append(prices["close"].values, current_price)

        # --- 1. 计算动量得分（包含年化收益率和R²） ---
        recent_price_series = price_series[-(g.lookback_days + 1):]
        y = np.log(recent_price_series)  # 对数价格
        x = np.arange(len(y))  # 时间序列
        weights = np.linspace(1, 2, len(y))  # 加权，近期数据权重更高
        slope, intercept = np.polyfit(x, y, 1, w=weights)  # 线性回归
        annualized_returns = math.exp(slope * 250) - 1  # 年化收益率
        # 计算R² (决定系数)
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot else 0
        momentum_score = annualized_returns * r_squared  # 动量得分为年化收益率与R²的乘积

        # --- 2. 计算短期动量 ---
        if len(price_series) >= g.short_lookback_days + 1:
            short_return = price_series[-1] / price_series[-(g.short_lookback_days + 1)] - 1
            short_annualized = (1 + short_return) ** (250 / g.short_lookback_days) - 1
        else:
            short_annualized = -np.inf

        # --- 3. 计算均线 ---
        ma_price = np.mean(price_series[-g.ma_filter_days:])
        current_above_ma = current_price >= ma_price

        # --- 4. 计算成交量比值 ---
        volume_ratio = get_volume_ratio(context, etf, show_detail_log=False)

        # --- 5. 短期风控（检查近3日是否有单日跌幅过大） ---
        day_ratios = []
        passed_loss_filter = True
        if len(price_series) >= 4:
            day1 = price_series[-1] / price_series[-2]
            day2 = price_series[-2] / price_series[-3]
            day3 = price_series[-3] / price_series[-4]
            day_ratios = [day1, day2, day3]
            if min(day_ratios) < g.loss:
                passed_loss_filter = False

        # --- 6. 计算RSI ---
        current_rsi = 0
        max_recent_rsi = 0
        passed_rsi_filter = True
        if g.use_rsi_filter and len(price_series) >= g.rsi_period + g.rsi_lookback_days:
            rsi_values = calculate_rsi(price_series, g.rsi_period)
            if len(rsi_values) >= g.rsi_lookback_days:
                recent_rsi = rsi_values[-g.rsi_lookback_days:]
                max_recent_rsi = np.max(recent_rsi)
                current_rsi = recent_rsi[-1]
                # 如果近期RSI超过阈值，则需要当前价格不低于5日均线才继续持有
                if np.any(recent_rsi > g.rsi_threshold):
                    ma5 = np.mean(price_series[-5:]) if len(price_series) >= 5 else current_price
                    if current_price < ma5:
                        passed_rsi_filter = False

        # 返回一个包含所有计算结果和判断标志的字典
        return {
            'etf': etf,
            'etf_name': etf_name,
            'momentum_score': momentum_score,
            'annualized_returns': annualized_returns,
            'r_squared': r_squared,
            'short_annualized': short_annualized,
            'current_price': current_price,
            'ma_price': ma_price,
            'volume_ratio': volume_ratio,
            'day_ratios': day_ratios,
            'current_rsi': current_rsi,
            'max_recent_rsi': max_recent_rsi,

            # 以下为各过滤器的判断结果（True为通过，False为未通过）
            'passed_momentum': g.min_score_threshold <= momentum_score <= g.max_score_threshold,
            'passed_short_mom': short_annualized >= g.short_momentum_threshold,
            'passed_r2': r_squared > g.r2_threshold,
            'passed_annual_ret': annualized_returns >= g.min_annualized_return,
            'passed_ma': current_above_ma,
            'passed_volume': volume_ratio is not None and volume_ratio < g.volume_threshold,
            'passed_loss': passed_loss_filter,
            'passed_rsi': passed_rsi_filter,
        }
    except Exception as e:
        # 如果计算过程中出现错误，记录警告并返回None
        log.warning(f"计算 {etf} 指标出错: {e}")
        return None


def apply_filters(metrics_list):
    """
    对传入的ETF指标列表应用一系列过滤条件。
    每个过滤器都会筛掉一部分ETF，最终返回通过所有过滤器的ETF。
    """
    # 定义过滤步骤，按顺序执行。每个步骤包含名称、条件函数和对应的开关
    steps = [
        ('动量得分', lambda m: m['passed_momentum'], True), # 动量得分始终启用，或根据具体开关
        ('短期动量', lambda m: m['passed_short_mom'], g.use_short_momentum_filter),
        ('R²', lambda m: m['passed_r2'], g.enable_r2_filter),
        ('年化收益率', lambda m: m['passed_annual_ret'], g.enable_annualized_return_filter), 
        ('均线', lambda m: m['passed_ma'], g.enable_ma_filter),
        ('成交量', lambda m: m['passed_volume'], g.enable_volume_check),
        ('短期风控', lambda m: m['passed_loss'], g.enable_loss_filter),
        ('RSI', lambda m: m['passed_rsi'], g.use_rsi_filter),
    ]
    
    # 从原始列表开始，依次应用每个**启用**的过滤器
    filtered = metrics_list[:]
    for name, condition, is_enabled in steps:
        if is_enabled: # 只有当开关为True时，才应用此过滤器
            filtered = [m for m in filtered if condition(m)]
            # log.debug(f"应用'{name}'过滤器后，剩余ETF数量: {len(filtered)}") # 可选调试日志
    return filtered


def get_final_ranked_etfs(context):
    """
    主要的ETF筛选和排名函数。
    遍历ETF池，计算指标，应用过滤器，并返回最终排名靠前的ETF列表。
    同时，严格按照两步输出日志：1. 所有ETF按动量排序; 2. 符合条件的ETF按动量排序。
    """
    all_metrics = []
    etf_set = set() # 用于去重

    # 遍历ETF池，为每个未停牌的ETF计算指标
    for etf in g.etf_pool:
        current_data = get_current_data()
        if current_data[etf].paused:
            continue
        metrics = calculate_all_metrics_for_etf(context, etf)
        if metrics:
            # 检查是否已经存在，防止重复添加
            if metrics['etf'] in etf_set:
                log.warning(f"发现重复ETF数据: {metrics['etf']}，跳过。")
                continue
            etf_set.add(metrics['etf'])
            all_metrics.append(metrics)

    # 在排序前，将所有 nan 的 momentum_score 替换为负无穷 ---
    for item in all_metrics:
        score = item.get('momentum_score')
        if pd.isna(score) or np.isnan(score): # 检查 pandas 和 numpy 的 nan
            item['momentum_score'] = float('-inf')

    # --- 第一步：对所有ETF按动量得分进行降序排序 ---
    # 现在所有值都是数字，排序将严格按数值大小进行。
    all_metrics.sort(key=lambda x: x.get('momentum_score', float('-inf')), reverse=True)

    # --- 构建第一步的日志：罗列所有ETF (按动量得分从大到小排序) ---
    log_lines_step1 = ["", ">>> 第一步：所有ETF按动量得分从大到小排序 <<<"]
    for m in all_metrics:
        def fmt_status(value_str, passed):
            return f"{value_str} {'✅' if passed else '❌'}"

        # 为了日志显示，对 nan 值进行特殊格式化
        original_score = m.get('momentum_score')
        if original_score == float('-inf'):
            mom_score_str = "nan"
            mom_passed = False # 原始得分为 nan，应标记为 ❌
        else:
            mom_score_str = f"{original_score:.4f}" if not pd.isna(original_score) else "nan"
            mom_passed = m['passed_momentum']

        mom = fmt_status(f"动量得分: {mom_score_str}", mom_passed)
        short_str = f"{m['short_annualized']:.4f}" if not pd.isna(m['short_annualized']) else "nan"
        short = fmt_status(f"短期动量: {short_str}", m['passed_short_mom'])
        r2_str = f"{m['r_squared']:.3f}" if not pd.isna(m['r_squared']) else "nan"
        r2 = fmt_status(f"R²: {r2_str}", m['passed_r2'])
        ann_str = f"{m['annualized_returns']:.2%}" if not pd.isna(m['annualized_returns']) else "nan%"
        ann = fmt_status(f"年化收益率: {ann_str}", m['passed_annual_ret'])
        ma_price_str = f"{m['ma_price']:.2f}" if not pd.isna(m['ma_price']) else "nan"
        ma = fmt_status(f"均线: 当前价{m['current_price']:.2f} vs 均线{ma_price_str}", m['passed_ma'])
        vol_val = f"{m['volume_ratio']:.2f}" if m['volume_ratio'] is not None else "N/A"
        vol = fmt_status(f"成交量比值: {vol_val}", m['passed_volume'])
        min_ratio = min(m['day_ratios']) if m['day_ratios'] else 'N/A'
        loss_val = f"{min_ratio:.4f}" if isinstance(min_ratio, float) and not pd.isna(min_ratio) else str(min_ratio)
        loss = fmt_status(f"短期风控（近3日最低比值）: {loss_val}", m['passed_loss'])
        rsi_str = f"{m['current_rsi']:.1f}" if not pd.isna(m['current_rsi']) else "nan"
        max_rsi_str = f"{m['max_recent_rsi']:.1f}" if not pd.isna(m['max_recent_rsi']) else "nan"
        rsi = fmt_status(f"RSI: 当前{rsi_str} (峰值{max_rsi_str})", m['passed_rsi'])

        line = (
            f"{m['etf']} {m['etf_name']}: "
            f"{mom} ，"
            f"{short} ，"
            f"{r2}，"
            f"{ann}，"
            f"{ma}，"
            f"{vol}，"
            f"{loss}，"
            f"{rsi}"
        )
        log_lines_step1.append(line)

    # --- 第二步：应用过滤器，获取最终候选列表 ---
    final_list = apply_filters(all_metrics)
    # 再次确保符合条件的列表也按动量得分降序排序 (同样处理 nan)，并取前10
    # 注意：这里也需要重新处理 nan，因为 apply_filters 可能会修改或传递原始数据
    for item in final_list:
        score = item.get('momentum_score')
        if pd.isna(score) or np.isnan(score):
            item['momentum_score'] = float('-inf')
    final_list.sort(key=lambda x: x.get('momentum_score', float('-inf')), reverse=True)
    top_10_final = final_list[:10]

    # --- 构建第二步的日志：罗列符合全部过滤条件的ETF (按动量得分从大到小排序，取前10) ---
    log_lines_step2 = ["", ">>> 第二步：符合全部过滤条件的ETF按动量得分从大到小排序 (前10名) <<<"]

    if top_10_final:
        for m in top_10_final:
            def fmt_status(value_str, passed):
                return f"{value_str} {'✅' if passed else '❌'}"

            original_score = m.get('momentum_score')
            if original_score == float('-inf'):
                mom_score_str = "nan"
                mom_passed = False
            else:
                mom_score_str = f"{original_score:.4f}" if not pd.isna(original_score) else "nan"
                mom_passed = m['passed_momentum']
            
            mom = fmt_status(f"动量得分: {mom_score_str}", mom_passed)
            short_str = f"{m['short_annualized']:.4f}" if not pd.isna(m['short_annualized']) else "nan"
            short = fmt_status(f"短期动量: {short_str}", m['passed_short_mom'])
            r2_str = f"{m['r_squared']:.3f}" if not pd.isna(m['r_squared']) else "nan"
            r2 = fmt_status(f"R²: {r2_str}", m['passed_r2'])
            ann_str = f"{m['annualized_returns']:.2%}" if not pd.isna(m['annualized_returns']) else "nan%"
            ann = fmt_status(f"年化收益率: {ann_str}", m['passed_annual_ret'])
            ma_price_str = f"{m['ma_price']:.2f}" if not pd.isna(m['ma_price']) else "nan"
            ma = fmt_status(f"均线: 当前价{m['current_price']:.2f} vs 均线{ma_price_str}", m['passed_ma'])
            vol_val = f"{m['volume_ratio']:.2f}" if m['volume_ratio'] is not None else "N/A"
            vol = fmt_status(f"成交量比值: {vol_val}", m['passed_volume'])
            min_ratio = min(m['day_ratios']) if m['day_ratios'] else 'N/A'
            loss_val = f"{min_ratio:.4f}" if isinstance(min_ratio, float) and not pd.isna(min_ratio) else str(min_ratio)
            loss = fmt_status(f"短期风控（近3日最低比值）: {loss_val}", m['passed_loss'])
            rsi_str = f"{m['current_rsi']:.1f}" if not pd.isna(m['current_rsi']) else "nan"
            max_rsi_str = f"{m['max_recent_rsi']:.1f}" if not pd.isna(m['max_recent_rsi']) else "nan"
            rsi = fmt_status(f"RSI: 当前{rsi_str} (峰值{max_rsi_str})", m['passed_rsi'])

            line = (
                f"{m['etf']} {m['etf_name']}: "
                f"{mom} ，"
                f"{short} ，"
                f"{r2}，"
                f"{ann}，"
                f"{ma}，"
                f"{vol}，"
                f"{loss}，"
                f"{rsi}"
            )
            log_lines_step2.append(line)
    else:
        log_lines_step2.append("（无符合条件的ETF）")

    log_lines_step2.append("==================================================")

    # --- 合并并输出完整的日志 ---
    full_log = "\n".join(log_lines_step1 + log_lines_step2)
    log.info(full_log)

    # 返回最终符合条件的ETF列表（已按动量排序），供后续逻辑使用
    return final_list 

def minute_level_stop_loss(context):
    """分钟级固定比例止损函数"""
    if not g.use_fixed_stop_loss: return
    if is_in_cooldown(context): return
    
    for security in list(context.portfolio.positions.keys()):
        if security not in g.etf_pool: continue
        position = context.portfolio.positions[security]
        if position.total_amount <= 0: continue
        
        current_data = get_current_data()
        current_price = current_data[security].last_price
        cost_price = position.avg_cost
        
        # 检查是否触发止损
        if current_price <= cost_price * g.fixed_stop_loss_threshold:
            security_name = get_security_name(security)
            loss_percent = (current_price / cost_price - 1) * 100
            log.info(f"🚨 [分钟级] 固定百分比止损卖出: {security} {security_name}，当前价: {current_price:.3f}, 成本: {cost_price:.3f}, 预设阈值: {g.fixed_stop_loss_threshold}, 预估亏损: {loss_percent:.2f}%")
            
            success = smart_order_target_value(security, 0, context)
            if success:
                log.info(f"✅ [分钟级] 已成功止损卖出: {security} {security_name}，实际亏损: {loss_percent:.2f}%")
                # 清除该仓位的止损相关记录
                g.position_highs.pop(security, None); g.position_stop_prices.pop(security, None)
                # 触发冷却期和避险ETF
                enter_safe_haven_and_set_cooldown(context, trigger_reason="分钟级固定止损")
            else:
                log.info(f"❌ [分钟级] 止损卖出失败: {security} {security_name}")


def minute_level_pct_stop_loss(context):
    """分钟级当日跌幅止损函数"""
    if not g.use_pct_stop_loss: return
    if is_in_cooldown(context): return
    
    current_data = get_current_data()
    for security in list(context.portfolio.positions.keys()):
        if security not in g.etf_pool: continue
        position = context.portfolio.positions[security]
        if position.total_amount <= 0: continue
        
        today_open = current_data[security].day_open
        if not today_open or today_open <= 0: continue
        
        current_price = current_data[security].last_price
        stop_price = today_open * g.pct_stop_loss_threshold
        
        if current_price <= stop_price:
            security_name = get_security_name(security)
            daily_loss = (current_price / today_open - 1) * 100
            log.info(f"🚨 [分钟级] 当日跌幅止损卖出: {security} {security_name}，当前价: {current_price:.3f}, 开盘价: {today_open:.3f}, 触发价: {stop_price:.3f}, 当日预估跌幅: {daily_loss:.2f}%")
            
            success = smart_order_target_value(security, 0, context)
            if success:
                log.info(f"✅ [分钟级] 已成功按当日跌幅止损卖出: {security} {security_name}，实际当日跌幅: {daily_loss:.2f}%")
                g.position_highs.pop(security, None); g.position_stop_prices.pop(security, None)
                enter_safe_haven_and_set_cooldown(context, trigger_reason="分钟级当日跌幅止损")
            else:
                log.info(f"❌ [分钟级] 当日跌幅止损卖出失败: {security} {security_name}")


def minute_level_atr_stop_loss(context):
    """分钟级ATR动态止损函数"""
    if not g.use_atr_stop_loss: return
    if is_in_cooldown(context): return
    
    current_data = get_current_data()
    for security in list(context.portfolio.positions.keys()):
        if security not in g.etf_pool: continue
        position = context.portfolio.positions[security]
        if position.total_amount <= 0: continue
        # 如果设置了排除防御性ETF，则跳过
        if g.atr_exclude_defensive and security == g.defensive_etf: continue
        
        try:
            security_name = get_security_name(security)
            current_price = current_data[security].last_price
            if current_price <= 0: continue
            
            cost_price = position.avg_cost
            
            # 计算当前ATR
            current_atr, _, success, _ = calculate_atr(security, g.atr_period)
            if not success or current_atr <= 0: continue
            
            # 更新或初始化该仓位的历史最高价
            if security not in g.position_highs:
                g.position_highs[security] = current_price
            else:
                g.position_highs[security] = max(g.position_highs[security], current_price)
            
            # 计算ATR止损价
            if g.atr_trailing_stop:
                atr_stop_price = g.position_highs[security] - g.atr_multiplier * current_atr
            else:
                atr_stop_price = cost_price - g.atr_multiplier * current_atr
            
            # 更新止损价记录
            g.position_stop_prices[security] = atr_stop_price
            
            # 检查是否触发止损
            if current_price <= atr_stop_price:
                loss_percent = (current_price / cost_price - 1) * 100
                atr_type = "跟踪" if g.atr_trailing_stop else "固定"
                log.info(f"🚨 [分钟级] ATR动态止损({atr_type})卖出: {security} {security_name}，当前价: {current_price:.3f}, 止损价: {atr_stop_price:.3f}, 亏损: {loss_percent:.2f}%")
                
                success = smart_order_target_value(security, 0, context)
                if success:
                    log.info(f"✅ [分钟级] ATR止损成功: {security} {security_name}")
                    g.position_highs.pop(security, None); g.position_stop_prices.pop(security, None)
                    enter_safe_haven_and_set_cooldown(context, trigger_reason="分钟级ATR动态止损")
                else:
                    log.info(f"❌ [分钟级] ATR止损失败: {security} {security_name}")
        except Exception as e:
            security_name = get_security_name(security)
            log.warning(f"[分钟级] ATR止损检查异常 {security} {security_name}: {e}")


def etf_sell_trade(context):
    """
    ETF卖出/轮动逻辑函数。
    根据新的评分结果，卖出不符合条件的持仓，为买入新标的做准备。
    """
    log.info("========== 卖出操作开始 (轮动逻辑) ==========")
    
    if is_in_cooldown(context):
        log.info("🔒 当前处于冷却期，跳过轮动逻辑中的卖出操作")
        log.info("========== 卖出操作完成 (轮动逻辑) ==========")
        return

    # 获取今日筛选出的最终目标ETF列表
    ranked_etfs = get_final_ranked_etfs(context)
    target_etfs = []
    if ranked_etfs:
        # 选取排名靠前的N只ETF作为目标
        for metrics in ranked_etfs[:g.holdings_num]:
            target_etfs.append(metrics['etf'])
            log.info(f"确定最终目标: {metrics['etf']} {metrics['etf_name']}，得分: {metrics['momentum_score']:.4f}")
    else:
        # 如果没有符合条件的，则切换到防御模式
        if check_defensive_etf_available(context):
            target_etfs = [g.defensive_etf]
            etf_name = get_security_name(g.defensive_etf)
            log.info(f"🛡️ 确定最终目标(防御模式): {g.defensive_etf} {etf_name}，得分: N/A")
        else:
            # 如果连防御性ETF也无法交易，则清仓
            log.info("💤 无最终目标(空仓模式)")
            target_etfs = []

    # 将目标列表存入全局变量，供买入函数使用
    g.target_etfs_list = target_etfs

    # 获取当前持仓
    current_positions = list(context.portfolio.positions.keys())
    target_set = set(target_etfs)
    
    # 遍历当前持仓，卖出不在新目标列表里的ETF
    for security in current_positions:
        if (security in g.etf_pool or security == g.defensive_etf) and security not in target_set:
            position = context.portfolio.positions[security]
            if position.total_amount > 0:
                security_name = get_security_name(security)
                log.info(f"📤 准备卖出不在目标列表的持仓: {security} {security_name}")
                
                success = smart_order_target_value(security, 0, context)
                if success:
                    log.info(f"✅ 已成功卖出: {security} {security_name}")
                else:
                    log.info(f"❌ 卖出失败: {security} {security_name}")
                
                # 清除该仓位的止损相关记录
                g.position_highs.pop(security, None)
                g.position_stop_prices.pop(security, None)

    log.info("========== 卖出操作完成 (轮动逻辑) ==========")


def etf_buy_trade(context):
    """
    ETF买入逻辑函数。
    根据昨日确定的目标列表，买入或调仓到目标ETF。
    """
    log.info("========== 买入操作开始 ==========")
    
    # 如果冷却期结束，先卖出避险ETF
    exit_safe_haven_if_cooldown_ends(context)
    
    if is_in_cooldown(context):
        log.info("🔒 当前处于冷却期，跳过正常买入操作")
        log.info("========== 买入操作完成 ==========")
        return

    target_etfs = g.target_etfs_list
    if not target_etfs:
        log.info("根据昨日计算，今日无目标ETF，保持空仓")
        log.info("========== 买入操作完成 ==========")
        return

    # 获取当前所有持仓
    current_positions = list(context.portfolio.positions.keys())
    # 筛选出属于ETF池或防御性ETF的持仓
    current_etf_positions = [pos for pos in current_positions if pos in g.etf_pool or pos == g.defensive_etf]
    # 找出需要卖出的持仓（在当前持仓但不在目标列表里）
    positions_to_sell = [pos for pos in current_etf_positions if pos not in target_etfs]
    
    if positions_to_sell:
        # 如果还有持仓需要先卖出，本次不执行买入，等待卖出完成
        log.info(f"尚有持仓需要卖出: {[get_security_name(p) for p in positions_to_sell]}，等待卖出完成后再买入新标的")
        log.info("========== 买入操作完成 ==========")
        return

    # 计算总资金和每只ETF应分配的资金
    total_value = context.portfolio.total_value
    target_value_per_etf = total_value / len(target_etfs)
    
    for etf in target_etfs:
        # 计算当前已持有该ETF的价值
        current_value = 0
        if etf in context.portfolio.positions:
            position = context.portfolio.positions[etf]
            if position.total_amount > 0:
                current_value = position.total_amount * position.price
        
        # 如果当前价值与目标价值差异较大，或尚未持有，则执行买入/调仓
        if abs(current_value - target_value_per_etf) > target_value_per_etf * 0.05 or current_value == 0:
            success = smart_order_target_value(etf, target_value_per_etf, context)
            if success:
                etf_name = get_security_name(etf)
                action = "买入" if current_value < target_value_per_etf else "调仓"
                log.info(f"📦 {action}: {etf} {etf_name}，目标金额: {target_value_per_etf:.2f}")

    log.info("========== 买入操作完成 ==========")


def check_positions(context):
    """盘中持仓检查函数，用于监控当前持仓情况"""
    current_data = get_current_data()
    for security in context.portfolio.positions:
        position = context.portfolio.positions[security]
        if position.total_amount > 0:
            security_name = get_security_name(security)
            log.info(f"📊 持仓检查: {security} {security_name}, 数量: {position.total_amount}, 成本: {position.avg_cost:.3f}, 当前价: {position.price:.3f}")
            if current_data[security].paused:
                log.info(f"⚠️ {security} {security_name} 今日停牌")


def smart_order_target_value(security, target_value, context):
    """
    智能下单函数，根据目标价值下单，并处理各种交易限制和异常情况。
    """
    current_data = get_current_data()
    security_name = get_security_name(security)
    
    # 检查交易状态
    if current_data[security].paused:
        log.info(f"{security} {security_name}: 今日停牌，跳过交易")
        return False
    if current_data[security].last_price >= current_data[security].high_limit:
        log.info(f"{security} {security_name}: 当前涨停，跳过买入")
        return False
    if current_data[security].last_price <= current_data[security].low_limit:
        log.info(f"{security} {security_name}: 当前跌停，跳过卖出")
        return False
    
    current_price = current_data[security].last_price
    if current_price == 0:
        log.info(f"{security} {security_name}: 当前价格为0，跳过交易")
        return False

    # 计算目标数量
    target_amount = int(target_value / current_price)
    # ETF必须是100的整数倍
    target_amount = (target_amount // 100) * 100
    if target_amount <= 0 and target_value > 0:
        target_amount = 100 # 至少买一手

    # 获取当前持仓
    current_position = context.portfolio.positions.get(security, None)
    current_amount = current_position.total_amount if current_position else 0
    
    # 计算需要买卖的数量差
    amount_diff = target_amount - current_amount
    trade_value = abs(amount_diff) * current_price
    
    # 检查交易金额是否达到最小要求
    if 0 < trade_value < g.min_money:
        log.info(f"{security} {security_name}: 交易金额{trade_value:.2f}小于最小交易额{g.min_money}，跳过交易")
        return False

    # 处理卖出逻辑（T+1规则）
    if amount_diff < 0:
        closeable_amount = current_position.closeable_amount if current_position else 0
        if closeable_amount == 0:
            log.info(f"{security} {security_name}: 当天买入不可卖出(T+1)")
            return False
        # 确保卖出数量不超过可卖数量
        amount_diff = -min(abs(amount_diff), closeable_amount)

    # 执行下单
    if amount_diff != 0:
        order_result = order(security, amount_diff)
        if order_result:
            # 下单成功，更新状态
            g.positions[security] = target_amount
            # 如果是买入新持仓，初始化其最高价和止损价
            if amount_diff > 0 and security in g.etf_pool:
                g.position_highs[security] = current_price
            if g.use_atr_stop_loss and not (g.atr_exclude_defensive and security == g.defensive_etf):
                current_atr, _, success, _ = calculate_atr(security, g.atr_period)
                if success:
                    if g.atr_trailing_stop:
                        g.position_stop_prices[security] = current_price - g.atr_multiplier * current_atr
                    else:
                        g.position_stop_prices[security] = current_price - g.atr_multiplier * current_atr
            
            if amount_diff > 0:
                log.info(f"📥 买入 {security} {security_name}，数量: {amount_diff}，价格: {current_price:.3f}")
            else:
                log.info(f"📤 卖出 {security} {security_name}，数量: {abs(amount_diff)}，价格: {current_price:.3f}")
            return True
        else:
            log.warning(f"下单失败: {security} {security_name}，数量: {amount_diff}")
            return False
    return False


def get_security_name(security):
    """安全地获取证券名称"""
    try:
        current_data = get_current_data()
        return current_data[security].name
    except Exception as e:
        log.warning(f"获取{security}名称失败: {e}")
        return "未知名称"


def check_defensive_etf_available(context):
    """检查防御性ETF是否可以交易"""
    current_data = get_current_data()
    defensive_etf = g.defensive_etf
    if current_data[defensive_etf].paused:
        defensive_etf_name = get_security_name(defensive_etf)
        log.info(f"防御性ETF {defensive_etf} {defensive_etf_name} 今日停牌")
        return False
    if current_data[defensive_etf].last_price >= current_data[defensive_etf].high_limit:
        defensive_etf_name = get_security_name(defensive_etf)
        log.info(f"防御性ETF {defensive_etf} {defensive_etf_name} 当前涨停")
        return False
    if current_data[defensive_etf].last_price <= current_data[defensive_etf].low_limit:
        defensive_etf_name = get_security_name(defensive_etf)
        log.info(f"防御性ETF {defensive_etf} {defensive_etf_name} 当前跌停")
        return False
    return True


def get_volume_ratio(context, security, lookback_days=None, threshold=None, show_detail_log=True):
    """计算当前成交量与过去平均成交量的比值"""
    if lookback_days is None:
        lookback_days = g.volume_lookback
    if threshold is None:
        threshold = g.volume_threshold
        
    try:
        security_name = get_security_name(security)
        hist_data = attribute_history(security, lookback_days, '1d', ['volume'])
        
        if hist_data.empty or len(hist_data) < lookback_days:
            return None
            
        past_n_days_vol = hist_data['volume']
        if past_n_days_vol.isnull().any() or past_n_days_vol.eq(0).any():
            return None
            
        avg_volume = past_n_days_vol.mean()
        if avg_volume == 0:
            return None
            
        # 获取当日累计成交量
        today = context.current_dt.date()
        df_vol = get_price(security, start_date=today, end_date=context.current_dt, frequency='1m', fields=['volume'], skip_paused=False, fq='pre', panel=True, fill_paused=False)
        current_volume = df_vol['volume'].sum()
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        return volume_ratio
    except Exception as e:
        return None


def calculate_rsi(prices, period=6):
    """计算RSI指标"""
    if len(prices) < period + 1:
        return []
        
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gains = np.zeros_like(prices)
    avg_losses = np.zeros_like(prices)
    
    avg_gains[period] = np.mean(gains[:period])
    avg_losses[period] = np.mean(losses[:period])
    
    rsi_values = np.zeros(len(prices))
    rsi_values[:period] = 50
    
    for i in range(period + 1, len(prices)):
        avg_gains[i] = (avg_gains[i-1] * (period - 1) + gains[i-1]) / period
        avg_losses[i] = (avg_losses[i-1] * (period - 1) + losses[i-1]) / period
        
        if avg_losses[i] == 0:
            rsi_values[i] = 100
        else:
            rs = avg_gains[i] / avg_losses[i]
            rsi_values[i] = 100 - (100 / (1 + rs))
            
    return rsi_values[period:]


def calculate_atr(security, period=14):
    """计算ATR指标"""
    try:
        needed_days = period + 20
        hist_data = attribute_history(security, needed_days, '1d', ['high', 'low', 'close'])
        
        if len(hist_data) < period + 1:
            return 0, [], False, f"数据不足{period+1}天"
            
        high_prices = hist_data['high'].values
        low_prices = hist_data['low'].values
        close_prices = hist_data['close'].values
        
        tr_values = np.zeros(len(high_prices))
        for i in range(1, len(high_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            tr_values[i] = max(tr1, tr2, tr3)
        
        atr_values = np.zeros(len(tr_values))
        for i in range(period, len(tr_values)):
            atr_values[i] = np.mean(tr_values[i-period+1:i+1])
        
        current_atr = atr_values[-1] if len(atr_values) > 0 else 0
        valid_atr = atr_values[period:] if len(atr_values) > period else atr_values
        return current_atr, valid_atr, True, "计算成功"
    except Exception as e:
        return 0, [], False, f"计算出错:{str(e)}"


def is_in_cooldown(context):
    """检查当前是否处于冷却期内"""
    if not g.sell_cooldown_enabled or g.cooldown_end_date is None:
        return False
    return context.current_dt.date() <= g.cooldown_end_date


def set_cooldown(context):
    """设置冷却期结束日期"""
    if g.sell_cooldown_enabled:
        g.cooldown_end_date = context.current_dt.date() + pd.Timedelta(days=g.sell_cooldown_days)
        log.info(f"🔒 触发冷却期，结束日期: {g.cooldown_end_date.strftime('%Y-%m-%d')}")


def enter_safe_haven_and_set_cooldown(context, trigger_reason=""):
    """
    当触发风控时，清空所有持仓，买入避险ETF，并启动冷却期。
    """
    if not g.sell_cooldown_enabled:
        return
    
    # 卖出所有非避险ETF的持仓
    for security in list(context.portfolio.positions.keys()):
        if security in g.etf_pool or security == g.defensive_etf:
            position = context.portfolio.positions[security]
            if position.total_amount > 0:
                security_name = get_security_name(security)
                success = smart_order_target_value(security, 0, context)
                if success:
                    log.info(f"✅ [冷却期] 卖出持仓: {security} {security_name}")
                else:
                    log.info(f"❌ [冷却期] 卖出持仓失败: {security} {security_name}")
                g.position_highs.pop(security, None)
                g.position_stop_prices.pop(security, None)
    
    # 计算可用资金并买入避险ETF
    total_value = context.portfolio.total_value
    if total_value > g.min_money:
        success = smart_order_target_value(g.safe_haven_etf, total_value * 0.99, context)
        if success:
            safe_name = get_security_name(g.safe_haven_etf)
            log.info(f"🛡️ [冷却期] 买入避险ETF: {g.safe_haven_etf} {safe_name}，金额: {total_value * 0.99:.2f}")
        else:
            log.info(f"❌ [冷却期] 买入避险ETF: {g.safe_haven_etf} ")
    else:
        log.info(f"💡 [冷却期] 资金不足，无法买入避险ETF。总资产: {total_value:.2f}")
    
    # 设置冷却期
    set_cooldown(context)
    log.info(f"🔒 [冷却期] 已进入冷却期，由 [{trigger_reason}] 触发。")


def exit_safe_haven_if_cooldown_ends(context):
    """
    检查冷却期是否结束，如果结束则卖出避险ETF，使策略恢复正常运行。
    """
    if not g.sell_cooldown_enabled or g.cooldown_end_date is None:
        return
        
    current_date = context.current_dt.date()
    if current_date > g.cooldown_end_date:
        log.info(f"🔓 冷却期结束，当前日期: {current_date.strftime('%Y-%m-%d')}")
        
        # 卖出避险ETF
        if g.safe_haven_etf in context.portfolio.positions:
            position = context.portfolio.positions[g.safe_haven_etf]
            if position.total_amount > 0:
                security_name = get_security_name(g.safe_haven_etf)
                success = smart_order_target_value(g.safe_haven_etf, 0, context)
                if success:
                    log.info(f"✅ [冷却期结束] 卖出避险ETF: {g.safe_haven_etf} {security_name}")
                else:
                    log.info(f"❌ [冷却期结束] 卖出避险ETF失败: {g.safe_haven_etf} {security_name}")
                g.position_highs.pop(g.safe_haven_etf, None)
                g.position_stop_prices.pop(g.safe_haven_etf, None)
        
        # 重置冷却期状态
        g.cooldown_end_date = None
        log.info(f"🔄 策略恢复正常运行")


def trade(context):
    pass