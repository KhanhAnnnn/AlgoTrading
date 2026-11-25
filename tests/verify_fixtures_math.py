def build_and_test_fixtures():
    BASE_TS = 1792238400
    SYMBOL = 'BTC/USD'
    
    bars = []
    news = []
    
    # 1. Baseline: Bars 0 to 24 (t = 0..24 min), Price = 80,000.0
    for i in range(25):
        t = BASE_TS + i * 60
        bars.append({'idx': len(bars), 'time': t, 'close': 80000.0})
        
    # Case 1: Early News at t = 3 min (t = BASE_TS + 180s), sentiment = 0.75
    news.append({'id': 9001, 'time': BASE_TS + 3 * 60, 'sentiment': 0.75, 'desc': 'Early news / insufficient SMA'})
    
    # 2. BUY Setup:
    # Bar 25 (t = 25 min): close = 80000.0
    bars.append({'idx': len(bars), 'time': BASE_TS + 25 * 60, 'close': 80000.0})
    # Bar 26 (t = 26 min): close = 79500.0 (Cross below SMA20)
    bars.append({'idx': len(bars), 'time': BASE_TS + 26 * 60, 'close': 79500.0})
    # News 9002 at t = 26 min + 10s, sentiment = 0.65
    news.append({'id': 9002, 'time': BASE_TS + 26 * 60 + 10, 'sentiment': 0.65, 'desc': 'BUY signal'})
    
    # Bars 27..40 (t = 27..40 min): close stays low at 79500.0 to let SMA20 settle below 80000
    for i in range(27, 41):
        t = BASE_TS + i * 60
        bars.append({'idx': len(bars), 'time': t, 'close': 79500.0})
        
    # 3. SELL Setup:
    # Bar 41 (t = 41 min): close = 79500.0
    bars.append({'idx': len(bars), 'time': BASE_TS + 41 * 60, 'close': 79500.0})
    # Bar 42 (t = 42 min): close = 80500.0 (Cross above SMA20)
    bars.append({'idx': len(bars), 'time': BASE_TS + 42 * 60, 'close': 80500.0})
    # News 9003 at t = 42 min + 10s, sentiment = -0.70
    news.append({'id': 9003, 'time': BASE_TS + 42 * 60 + 10, 'sentiment': -0.70, 'desc': 'SELL signal'})
    
    # Bars 43..55 (t = 43..55 min): close stays high at 80500.0
    for i in range(43, 56):
        t = BASE_TS + i * 60
        bars.append({'idx': len(bars), 'time': t, 'close': 80500.0})
        
    # 4. NO SIGNAL Setup (Positive sentiment without crossover):
    # Bars around 58 min: price stays at 80500.0
    # News 9004 at t = 58 min + 10s, sentiment = 0.80
    for i in range(56, 61):
        t = BASE_TS + i * 60
        bars.append({'idx': len(bars), 'time': t, 'close': 80500.0})
    news.append({'id': 9004, 'time': BASE_TS + 58 * 60 + 10, 'sentiment': 0.80, 'desc': 'No crossover (elevated)'})
    
    # 5. Neutral Sentiment Setup (sentiment == 0.0):
    # At t = 65 min: price drops to 79500.0 (cross below), BUT sentiment is 0.0!
    for i in range(61, 65):
        t = BASE_TS + i * 60
        bars.append({'idx': len(bars), 'time': t, 'close': 80500.0})
    # Bar at 65 min: drops to 79500.0
    bars.append({'idx': len(bars), 'time': BASE_TS + 65 * 60, 'close': 79500.0})
    # Bars 66..68: stays at 79500.0
    for i in range(66, 69):
        t = BASE_TS + i * 60
        bars.append({'idx': len(bars), 'time': t, 'close': 79500.0})
    news.append({'id': 9005, 'time': BASE_TS + 65 * 60 + 10, 'sentiment': 0.0, 'desc': 'Neutral sentiment == 0.0'})
    
    # Calculate SMA20 and SMA50 for each bar
    for i, b in enumerate(bars):
        w20 = [x['close'] for x in bars[max(0, i - 19):i + 1]]
        w50 = [x['close'] for x in bars[max(0, i - 49):i + 1]]
        b['sma20'] = round(sum(w20) / len(w20), 2)
        b['sma50'] = round(sum(w50) / len(w50), 2)
        
    joined = []
    for n in news:
        matched = [b for b in bars if abs(n['time'] - b['time']) <= 120]
        for b in matched:
            joined.append({
                'news_id': n['id'],
                'news_desc': n['desc'],
                'news_time': n['time'],
                'sentiment': n['sentiment'],
                'bar_idx': b['idx'],
                'price_time': b['time'],
                'close': b['close'],
                'sma20': b['sma20'],
                'sma50': b['sma50']
            })
            
    joined.sort(key=lambda x: (x['news_time'], x['price_time']))
    
    signals = []
    prev_close = None
    for j in joined:
        c = j['close']
        s20 = j['sma20']
        sent = j['sentiment']
        sig = None
        if sent > 0 and c < s20 and prev_close is not None and prev_close >= s20:
            sig = 'BUY'
        elif sent < 0 and c > s20 and prev_close is not None and prev_close <= s20:
            sig = 'SELL'
            
        if sig:
            signals.append({
                'signal': sig,
                'news_id': j['news_id'],
                'news_desc': j['news_desc'],
                'bar_idx': j['bar_idx'],
                'close': c,
                'sma20': s20,
                'prev_close': prev_close,
                'sentiment': sent
            })
        prev_close = c
        
    print(f"Total Bars: {len(bars)}, Total News: {len(news)}, Total Joined Rows: {len(joined)}")
    print(f"Signals Emitted: {len(signals)}")
    for s in signals:
        print(f"  --> {s['signal']} at Bar {s['bar_idx']} (News {s['news_id']} '{s['news_desc']}'): close={s['close']}, sma20={s['sma20']}, prev_close={s['prev_close']}, sent={s['sentiment']}")

build_and_test_fixtures()

