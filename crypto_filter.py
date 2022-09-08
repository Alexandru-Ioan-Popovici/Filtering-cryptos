import sqlite3
import datetime as dt
import requests
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def moving_average(df, n, day=0):
    if day == 0:
        close_prices = df['close'].iloc[-n:]
    else:
        close_prices = df['close'].iloc[-n - day:-day]

    return round(close_prices.mean(), 4)


def atr(df, i, n=14):
    """ Average true range """
    df['x'] = df['high'] - df['low']
    df['y'] = abs(df['high'] - df['close'].shift())
    df['z'] = abs(df['low'] - df['close'].shift())
    df['TR'] = df[['x', 'y', 'z']].max(axis=1)
    df['ATR'] = round(df['TR'].rolling(n).mean(), 2)

    return df['ATR'].iloc[i]


def backend(reporting_date, trade_type, ma_threshold, check_new_symbols, update_db, critical_rank, minimum_coin_price,
            critical_date=None):
    data_table = 'ohlcv'

    def is_data_for_symbol(symbol):
        cursor.execute(f'select count() from {data_table} where symbols=(?)', (symbol,))

        return cursor.fetchone()[0] != 0

    def all_binance_trading_pairs():
        base_url = 'https://api.binance.com'
        endpoint = '/api/v3/exchangeInfo'
        url = base_url + endpoint
        data = json.loads(requests.get(url).text)
        data = data['symbols']
        pairs = []
        for details in data:
            if details['status'] == 'TRADING':  # symbols with BREAK status are omitted
                pairs.append((details['baseAsset'], details['quoteAsset']))

        return pairs

    def valid_symbols_quoted_in_stablecoin():
        ''' if a coin is quoted both in usdt and busd, usdt quotes will be selected; if only in busd then they will
        be selected; if not quoted in either stablecoin, the symbol is foregone '''

        pairs = all_binance_trading_pairs()
        selected_symbols_dict = {}
        for pair in pairs:
            symbol, quote_asset = pair[0], pair[1]
            if symbol in ['BUSD', 'DAI', 'USDC']:
                continue
            if quote_asset == 'USDT':
                selected_symbols_dict[symbol] = quote_asset
            elif quote_asset == 'BUSD':
                if (symbol, 'USDT') in pairs:
                    continue
                else:
                    selected_symbols_dict[symbol] = quote_asset

        return selected_symbols_dict

    def symbol_df(symbol, stablecoin, start_datetime, end_datetime):
        base_url = 'https://api.binance.com'
        endpoint = '/api/v3/klines'
        url = base_url + endpoint
        interval = '1d'
        start_date = str(int(dt.datetime.timestamp(start_datetime) * 1000))
        end_date = str(int(dt.datetime.timestamp(end_datetime) * 1000))
        par = {'symbol': symbol+stablecoin, 'interval': interval, 'startTime': start_date, 'endTime': end_date}
        df = pd.DataFrame(json.loads(requests.get(url, params=par).text))
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades',
                      'taker_base_vol', 'taker_quote_vol', 'ignore']
        df = df.astype(float)
        df['date'] = df['timestamp'].iloc[:].apply(lambda x: dt.datetime.fromtimestamp(x / 1000))

        return df

    def symbol_data_upload(db_connection, symbol):
        end_datetime = dt.datetime.now() - dt.timedelta(1)

        # determine the start date of the ohlcv data to load into db
        if not is_data_for_symbol(symbol):
            update_series_depth = 400
            start_datetime = end_datetime - dt.timedelta(update_series_depth)
        else:
            cursor.execute(f'select date from {data_table} where symbols=(?)', (symbol,))
            last_date_in_db = cursor.fetchall()[-1][0]
            start_datetime = dt.datetime.strptime(last_date_in_db, '%Y-%m-%d %H:%M:%S') + dt.timedelta(1)

            """ retrieve daily ohlcv data from exchange for the days determined & load them into db 
            if start_date is different from end_date """

        if (end_datetime - start_datetime).days >= 0:
            stablecoin = valid_symbols_quoted_in_stablecoin()[symbol]
            df = symbol_df(symbol, stablecoin, start_datetime, end_datetime)
            symbol_series = []
            for _ in range(len(df)):
                symbol_series.append(symbol)
            df['symbols'] = pd.Series(symbol_series)
            df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'symbols']]
            df.to_sql(data_table, db_connection, if_exists='append', index=False)
            db_connection.commit()

    def insert_new_symbols_binance(db_connection):
        cursor.execute('select * from cryptos')
        db_symbols = cursor.fetchall()
        existing_symbols = []
        for i in db_symbols:
            existing_symbols.append(i[0])

        binance_symbols = tuple(valid_symbols_quoted_in_stablecoin().keys())
        new_symbols = []
        for symbol in binance_symbols:
            if symbol not in existing_symbols:
                new_symbols.append(symbol)
                cursor.execute('insert into cryptos values (?)', (symbol,))
                symbol_data_upload(db_connection, symbol)

        return new_symbols, binance_symbols

    def list_descending_sort(list):  # this is for a list of 2-item tuples: the former str, the latter float
        flag = 1
        while flag:
            flag = 0
            for i in range(len(list)-1):
                if list[i][1] < list[i + 1][1]:
                    list[i], list[i + 1] = list[i + 1], list[i]
                    flag = 1

        return list

    def rankings(mega_df):
        """ creating a dict of all crypto symbols w/ their respective IBD-like rankings """
        symbols = mega_df['symbols'].values.tolist()
        symbols = list(set(symbols))

        changes = []
        len_q1, len_q2, len_q3, len_q4 = 91, 183, 274, 365  # days length of each quarter from the reporting date

        for symbol in symbols:
            df_for_symbol = mega_df[['open', 'high', 'low', 'close', 'volume']][mega_df['symbols'] == symbol]
            last_price = df_for_symbol['close'].iloc[-1]

            price_1Q_ago = df_for_symbol['close'].iloc[-len_q1] if len(df_for_symbol) >= len_q1 else \
                df_for_symbol['close'].iloc[0]
            price_2Q_ago = df_for_symbol['close'].iloc[-len_q2] if len(df_for_symbol) >= len_q2 else \
                df_for_symbol['close'].iloc[0] if len(df_for_symbol) >= len_q1 else 1
            price_3Q_ago = df_for_symbol['close'].iloc[-len_q3] if len(df_for_symbol) >= len_q3 else \
                df_for_symbol['close'].iloc[0] if len(df_for_symbol) >= len_q2 else 1
            price_4Q_ago = df_for_symbol['close'].iloc[-len_q4] if len(df_for_symbol) >= len_q4 else \
                df_for_symbol['close'].iloc[0] if len(df_for_symbol) >= len_q3 else 1

            X = .60  # weight on last quarter's return to compute a weighted annual return, containered in variable "change"
            Y = (1-X)/3  # weight on the returns of the 3 prior quarters
            change = (last_price / price_1Q_ago - 1) * X + (price_1Q_ago / price_2Q_ago - 1) * Y +\
                     (price_2Q_ago / price_3Q_ago - 1) * Y + (price_3Q_ago / price_4Q_ago - 1) * Y
            changes.append((symbol, change))
        changes = list_descending_sort(changes)

        ranks = []
        for i in range(99, 0, -1):
            if i == 1:
                for j in range(len(changes)):
                    ranks.append((changes[j][0], i))
            else:
                fract = round(len(changes) / i)
                for j in range(fract):
                    ranks.append((changes[j][0], i))
                for j in range(fract):
                    del changes[0]

        return dict(ranks)


    def critical_level_touched(df, critical_date, reporting_date, trade_type):
        flag = 0
        range_of_days = [critical_date + dt.timedelta(i+1) for i in range(int((reporting_date - critical_date).days))]
        for day in range_of_days:
            if trade_type == 'long':
                if df['low'][df['date'] == day].iloc[-1] <= df['low'][df['date'] == critical_date].iloc[-1]:
                    flag = 1
                    break
            elif df['high'][df['date'] == day].iloc[-1] >= df['high'][df['date'] == critical_date].iloc[-1]:
                flag = 1
                break

        return flag == 1


    class Filtering:
        def __init__(self, symbol, mega_df, under_avg_volume=0.1):
            self.symbol = symbol
            self.mega_df = mega_df
            self.under_avg_volume = under_avg_volume
            self.df = self.mega_df[['date', 'high', 'low', 'close', 'volume']][self.mega_df['symbols'] == symbol]
            self.last_price = self.df['close'].iloc[-1]

        def shaking(self, dma, days=2):  # shakes 10dma in any of the last <days> days, in the last 2 days by default
            return True in list(self.df['low'].iloc[-days:] <= moving_average(self.df, dma)) and\
                    True in list(moving_average(self.df, dma) <= self.df['high'].iloc[-days:])

        def filtering_long(self):
            """ vol[-1] < 90% vol.ma(30); doji (H-L=90%xATR); ma(50)<=close[-1]; low[-2]<=high[-1]<=high[-2];
             shakes 10dma last 2 days  """

            self.df['vol_mov.avg'] = self.df['volume'].rolling(30).mean()
            if self.df['vol_mov.avg'].iloc[-1] * (1-self.under_avg_volume) <= self.df['volume'].iloc[-1]:
                return False
            if self.df['high'].iloc[-1] - self.df['low'].iloc[-1] > atr(self.df, -1)*0.9:
                return False
            if self.df['low'].iloc[-2] > self.df['high'].iloc[-1] or self.df['high'].iloc[-1] > self.df['high'].iloc[-2]:
                return False
            if not self.shaking(10):
                return False
            if self.last_price < moving_average(self.df, ma_threshold):
                return False
            if critical_date and critical_level_touched(self.df, critical_date, reporting_date, trade_type):
                return False
            else:
                return True

        def filtering_short(self):
            self.df['vol_mov.avg'] = self.df['volume'].rolling(30).mean()
            if self.df['vol_mov.avg'].iloc[-1] * (1 - self.under_avg_volume) <= self.df['volume'].iloc[-1]:
                return False
            if self.df['high'].iloc[-1] - self.df['low'].iloc[-1] > atr(self.df, -1) * 0.9:
                return False
            if self.df['high'].iloc[-2] < self.df['low'].iloc[-1] or self.df['low'].iloc[-1] < self.df['low'].iloc[-2]:
                return False
            if not self.shaking(10):
                return False
            if self.last_price > moving_average(self.df, ma_threshold):
                return False
            if critical_date and critical_level_touched(self.df, critical_date, reporting_date, trade_type):
                return False
            else:
                return True

    def symbol_complies_price_criteria():
        last_price = mega_df['close'][mega_df['symbols'] == symbol].iloc[-1]

        return last_price > minimum_coin_price

    def symbol_complies_rank_criteria():
        if trade_type == 'long':
            return ranks[symbol] >= critical_rank
        if trade_type == 'short':
            return ranks[symbol] <= critical_rank


    connection = sqlite3.connect('cryptodb.db')
    cursor = connection.cursor()
    if check_new_symbols:
        new_symbols, symbols = insert_new_symbols_binance(connection)
        if len(new_symbols) == 0:
            print('There are no new symbols.')
        elif len(new_symbols) == len(symbols):
            print(f'List of crypto symbols has been uploaded for the first time with {len(symbols)} symbols.')
        else:
            print('New symbols are: ', end='')
            for symbol in new_symbols:
                print(symbol+'  ', end='')
    else:
        symbols = []
        cursor.execute('select * from cryptos')
        for row in cursor:
            symbols.append(row[0])
    if update_db:
        for symbol in symbols:
            try:
                symbol_data_upload(connection, symbol)
            except Exception:
                raise Exception('Internet connection is off. Please turn it on and rerun the program.')
    cursor.close()
    all_symbols_number = len(symbols)

    # now that db is updated, all ohlcv data is parsed into a pandas df for filtering
    mega_df = pd.read_sql('select * from ohlcv', connection)
    connection.close()
    mega_df['date'] = mega_df['date'].apply(lambda x: dt.datetime.strptime(x, '%Y-%m-%d %H:%M:%S').date())
    last_db_date = mega_df['date'].iloc[-1]
    if last_db_date < reporting_date:
        raise Exception(f"The OHCLV data must be updated; last ohclv data are as at {last_db_date}.\n "
                        f"Please update the ohlcv data or select a date up to {last_db_date} the latest.")

    reporting_date_index = (reporting_date - last_db_date).days - 1
    all_dates = sorted(list(set(mega_df['date'].values.tolist())))
    if reporting_date_index < -1:  # the user may query at a historical date
        for i in range(reporting_date_index+1, 0):
            mega_df = mega_df[mega_df['date'] != all_dates[i]]

    # list of symbols complying price and rank criteria sorted in descending order of rankings
    ranks = rankings(mega_df)
    for symbol in symbols:
        if not symbol_complies_rank_criteria() or \
                (trade_type == 'long' and not symbol_complies_price_criteria()):
            mega_df = mega_df[mega_df['symbols'] != symbol]
    remaining_symbols = tuple(set(mega_df['symbols'].values.tolist()))  # further filtering is to be done on fewer cryptos
    ranked_symbols = []  # sorting remaining symbols in descending order of their ranks
    for symbol in ranks.keys():
        if symbol in remaining_symbols:
            ranked_symbols.append(symbol)

    # final filter applied
    counter = 0
    results = []
    list_shk20 = []
    list_shk50 = []
    for symbol in ranked_symbols:
        obj = Filtering(symbol, mega_df)
        if trade_type == 'long':
            if obj.filtering_long():
                counter += 1
                results.append(symbol)
        elif obj.filtering_short():
            counter += 1
            results.append(symbol)
        if obj.shaking(20):
            list_shk20.append(symbol)
        if obj.shaking(50):
            list_shk50.append(symbol)
    if trade_type == 'short':
        results.reverse()

    mega_df = mega_df[mega_df['symbols'].isin(results)]

    return all_symbols_number, counter, results, ranks, list_shk20, list_shk50, mega_df

# the streamlit interface allows the user to export the results into a txt file, if desired
def exporting_to_txtfile(reporting_date, trade_type, all_symbols_number, counter, results, ranks, list_shk20, list_shk50):
    file_name = f'{trade_type} filtered tokens_{reporting_date}.txt'
    file = open(file_name, 'w')
    if counter > 0:
        file.write(
            f'Coverage {counter / all_symbols_number:0.1%} with {counter} token(s) found on the {trade_type} side '
            f'out of {all_symbols_number} as at {reporting_date}:' + 2 * '\n')
    else:
        print(f'No token found out of {all_symbols_number} filtered.' + '\n')
    for symbol in results:
        file.write(f'{symbol}  {ranks[symbol]}')
        if symbol in list_shk20 and symbol not in list_shk50:
            file.write(f' (20ma);  ')
        elif symbol in list_shk50 and symbol not in list_shk20:
            file.write(f' (50ma);  ')
        elif symbol in list_shk20 and symbol in list_shk50:
            file.write(f' (20-50ma);  ')
        else:
            file.write('; ')
    file.close()


def chart_symbol(symbol, df):
    fig = make_subplots(rows=3, cols=1, subplot_titles=[symbol, 'Volume', 'ATR(14)'], shared_xaxes=True)
    fig.add_trace(go.Candlestick(x=df.date, open=df.open, high=df.high, low=df.low, close=df.close,
                                 name=symbol, showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.date, y=df.dma10, line=dict(color='blue', width=2), name='10dma'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.date, y=df.dma20, line=dict(color='violet', width=2), name='20dma'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.date, y=df.dma50, line=dict(color='orange', width=2), name='50dma'), row=1, col=1)
    fig.add_trace(go.Bar(x=df.date, y=df.volume, name='Volume'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.date, y=df.vol30dma, line=dict(color='darkblue', width=1), name='Vol30dma'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.date, y=df.ATR, line=dict(color='darkblue', width=1), name='ATR(14)'), row=3, col=1)
    fig.update(layout_xaxis_rangeslider_visible=False)
    fig.update_yaxes(autorange=True)
    fig.show()
