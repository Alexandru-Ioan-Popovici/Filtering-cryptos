import streamlit as st
import datetime as dt
import time
import crypto_filter

def dates_to_combo(nr_of_days):
    current_gmt_date = dt.date(time.gmtime()[0], time.gmtime()[1], time.gmtime()[2])
    dates = []
    for i in range(1, nr_of_days+1):
        if i == 1 and dt.date.today() > current_gmt_date:
            continue  # accounting for the several-hour difference btw current local time and GMT time, if the case
        date = dt.date.today() - dt.timedelta(i)
        dates.append(date)

    return dates


nr_of_dates = 300

st.title(f"Filtering for Binance coins:")
st.write('\n')

input_container = st.container()
with input_container:
    st.subheader("Input data:")
    col_width = 1
    col1, col2, col3, col4, col5 = st.columns((col_width, col_width, col_width, 0.5, 1.5))
    with col1:
        st.markdown("<br />", unsafe_allow_html=True)
        check_new_symbols = st.checkbox('Check for new tokens listed')
        '\n'
        update_db = st.checkbox('Update ohlcv data')
        '\n'
        critical_date = None
        if st.checkbox('Set critical date'):
            critical_date = st.date_input('Date of critical high/low: ')

    with col2:
        trade_type = st.radio("Trade type (long/short): ", ('long', 'short'))

        minimum_coin_price = st.number_input('Minimum coin price: ', 0.01) if trade_type == 'long' else 0

        reporting_date = st.selectbox("Reporting date: ", dates_to_combo(nr_of_dates))

    with col3:
        ma_threshold = st.number_input('Critical dma: ', value=50)
        '\n'
        critical_rank = st.number_input('Critical IBD-like rank: ', value=80 if trade_type == 'long' else 30)
        '\n'
        '\n'
        filter_button = st.button('Filter')
        if "filter" not in st.session_state:
            st.session_state.filter = False

try:
    returns = crypto_filter.backend(reporting_date, trade_type, ma_threshold, check_new_symbols, update_db,
                                critical_rank, minimum_coin_price, critical_date)
    all_symbols_number, counter, results, ranks, list_shk20, list_shk50, mega_df = returns
except Exception as e:
    st.error(e)
    st.stop()

if filter_button or st.session_state.filter:
    st.session_state.filter = True
    output_container = st.container()
    with output_container:
        st.subheader('Output data')
        if counter == 0:
            st.write(f'No token found out of {all_symbols_number} filtered.' + '\n')
        else:
            st.write(f'Coverage {counter / all_symbols_number:0.1%} with {counter} token(s) found '
                     f'on the {trade_type} side out of {all_symbols_number} as at {reporting_date}:' + 2 * '\n')
            line = ''
            count, index = 0, 0
            max_symbols_row = 10
            for symbol in results:
                line += f'{symbol} {ranks[symbol]} '
                if symbol in list_shk20 and symbol not in list_shk50:
                    line += f' (20ma)'
                elif symbol in list_shk50 and symbol not in list_shk20:
                    line += f' (50ma)'
                elif symbol in list_shk20 and symbol in list_shk50:
                    line += f' (20-50ma)'
                line += '.' if index == len(results) - 1 else ';  '
                count += 1
                if count == max_symbols_row or index == len(results) - 1:
                    st.write(line)
                    line = ''
                    count = 0
                index += 1

        '\n'
        cols = st.columns(5)
        with cols[2]:
            if st.button('Show chart(s) for the symbol(s)'):
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

        with cols[0]:
            export_file = st.button('Export output to txt file')
            if export_file:
                file_name = crypto_filter.exporting_to_txtfile(reporting_date, trade_type, all_symbols_number, counter,
                                                               results, ranks, list_shk20, list_shk50)
