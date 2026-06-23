import yfinance as yf
import pandas as pd
import time
from datetime import datetime

print("🚀 Mark Minervini 策略篩選器 v2 啟動中...\n")
print("清單來源：QQQ + SPYG 成長股\n")

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        df = stock.history(period="1y")
        
        if len(df) < 200:
            return None
        
        current_price = df['Close'].iloc[-1]
        high52 = df['Close'].max()
        avg_volume = df['Volume'].mean()
        
        # Minervini Trend Template
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma150 = df['Close'].rolling(150).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        conditions = [
            current_price > sma50,
            current_price > sma150,
            current_price > sma200,
            sma150 > sma200,
            sma200 > df['Close'].rolling(200).mean().iloc[-20],
            current_price >= 0.75 * high52,
        ]
        
        score = sum(conditions)
        distance_from_high = ((current_price - high52) / high52) * 100
        
        fundamentals = {
            'eps_growth': info.get('earningsGrowth') or info.get('earningsQuarterlyGrowth'),
            'revenue_growth': info.get('revenueGrowth'),
            'current_price': current_price,
            'avg_volume': int(avg_volume),
            'distance_from_high': round(distance_from_high, 2),
            'trend_score': score
        }
        
        return fundamentals
        
    except:
        return None

# === 擴大後的成長股清單 (QQQ + SPYG 風格) ===
test_tickers = [
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","AVGO","MU","AMD","TSLA","ARM","CRWD",
    "SNOW","DDOG","MDB","HUBS","ZETA","APP","VRT","TTD","DKNG","HOOD","RKLB","SMR",
    "ASTS","COIN","MSTR","CLS","ONTO","AEHR","ACLS","FORM","KLAC","LRCX","AMAT",
    "ASML","CDNS","SNPS","MRVL","PANW","FTNT","ZS","NET","ESTC","WDAY","TEAM","ADSK",
    "NOW","ISRG","SPOT","PLTR","NFLX","COST","ADBE","QCOM","TXN","INTU","CMCSA",
    "BKNG","MELI","SHOP","UBER","ABNB","PYPL","SQ","TOST","RBLX","U","EA","TTWO",
    "ZM","DOCU","OKTA","TWLO","PATH","S","AI","UPST","CVNA","ELF","FRPT","CELH",
    "WING","DUOL","LLY","VRTX","REGN","PFE","MRK","TMO","DHR","AMGN","GFS","MPWR",
    "ON","MCHP","NXPI","SMCI","V","MA","AXP","BAC","JPM","GS","MS","BLK","SCHW"
    # 你之後可以繼續在這裡新增想追蹤的股票
]

print(f"正在掃描 {len(test_tickers)} 檔成長股...（預計 4~8 分鐘）\n")

results = []
for i, ticker in enumerate(test_tickers, 1):
    print(f"檢查 {i:3d}/{len(test_tickers)}: {ticker} ...")
    data = get_stock_data(ticker)
    
    if data and data['trend_score'] == 6:
        eps = data['eps_growth']
        rev = data['revenue_growth']
        if (eps is not None and eps > 0.20) or (rev is not None and rev > 0.20):
            results.append({
                '股票代碼': ticker,
                '技術分數': f"{data['trend_score']}/6",
                '目前股價': round(data['current_price'], 2),
                '離52週高點': f"{data['distance_from_high']}%",
                '平均成交量': f"{data['avg_volume']:,}",
                'EPS成長': f"{eps:.1%}" if eps is not None else "N/A",
                '營收成長': f"{rev:.1%}" if rev is not None else "N/A",
                '掃描日期': datetime.now().strftime("%Y-%m-%d")
            })
    
    time.sleep(1.0)

# 顯示結果
print("\n" + "="*110)
print(f"✅ 找到 {len(results)} 檔符合 Minervini 技術 + 基本面雙強股票：")
print("="*110)

for r in sorted(results, key=lambda x: float(x['離52週高點'][:-1]), reverse=False):  # 離高點最近的排前面
    print(f"   ⭐ {r['股票代碼']:6} | 技術: {r['技術分數']} | 股價: ${r['目前股價']:<8} | 離高點: {r['離52週高點']:>8} | EPS: {r['EPS成長']:>8} | 營收: {r['營收成長']:>8}")

# 存成 CSV
if results:
    df = pd.DataFrame(results)
    filename = "minervini_results.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"\n💾 已儲存至 {filename} （可用 Excel 打開）")
