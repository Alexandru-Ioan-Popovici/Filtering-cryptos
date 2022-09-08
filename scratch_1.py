import crypto_filter
import pandas as pd
import datetime as dt


x = 23
reporting_date = dt.date(2022, 8, x)
trade_type = 'long'
ma_threshold = 50
check_new_symbols, update_db = 0, 0
critical_rank = 80
minimum_coin_price = 0.01
critical_date = dt.date(2022, 8, 2)
returns = crypto_filter.backend(reporting_date, trade_type, ma_threshold, check_new_symbols, update_db, critical_rank,
                                minimum_coin_price)
results, mega_df = returns[2], returns[-1]


chart_range = 50
chart_end_date = mega_df.date.iloc[-1]
chart_start_date = chart_end_date - dt.timedelta(chart_range-1)
for symbol in results:
    df = mega_df[mega_df['symbols'] == symbol].reset_index()
    del df['index'], df['symbols']
    df['dma10'] = df.close.rolling(10).mean()
    df['dma20'] = df.close.rolling(20).mean()
    df['dma50'] = df.close.rolling(50).mean()
    df['vol30dma'] = df.volume.rolling(30).mean()
    crypto_filter.atr(df, -1)
    crypto_filter.chart_symbol(symbol, df[df.date >= chart_start_date])





