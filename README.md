# Filtering-cryptos

The software consecutively: 
  1. scrapes all crypto pairs from Binance API, via endpoint /api/v3/exchangeInfo, cleans them (no USD-stablecoins, only pairs with USDT and/or BUSD) and pushes/updates them (updates at user's discretion via a Streamlit checkbox widget) into the cryptos table of an empty Sqlite db (initially set up via SqliteStudio); 
  2. pushes/updates (at user's discretion via a Streamlit checkbox widget) the ohlcv table with daily quotes and volume for all symbols in cryptos table; if the table is empty, the initial push is for the last 400 days; filtering begins by pandas taking the ohclv data of all symbols into a dataframe (mega_df) with dates column type=datetime.date; 
  3. filtering is done based on user's inputs in the Streamlit app; one of the most important filters is based on the Relative Strength, ranging 1-99, inspired by Investors Business Daily computation of relative strength ranks across the whole US stock market, in this case across all about 350 valid Binance cryptos.

The output is a list of symbols (for long position sorted in the descending order of their IBD-like ranks and in ascending order for short trades), mentioning whether 20dma and/or 50dma have been shaken in the last couple of days. DataViz is delivered by interactive plotly charst exhibiting daily ohlc candles, 10dma, 20dma and 50dma in the former panel, daily volume bars with 30-day average volume line on the latter panel and ATR(14), i.e. average true range.

The software allows for historical query.
