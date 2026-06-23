# Minervini Scanner — USIC 2026

## 每次使用
雙擊桌面 Minervini_Scan.bat → 自動掃描 → 自動開瀏覽器

## 檔案說明
- minervini_scanner.py  主掃描程式
- backtest.py           回測程式（5年歷史驗證）
- minervini_YYYY-MM-DD.html  每次掃描結果報告

## 系統功能
- 8條 Minervini Trend Template
- RS Rating 對比 SPY
- 市場環境燈號 BULL / NEUTRAL / BEAR
- 自動生成 HTML 報告

## Backtest 結果（2020-2025）
- 勝率：59.2%（3個月持股）
- 平均回報：+7.98%
- Alpha vs SPY：+4.1%

## 待加入策略
1. 止蝕 7-8%
2. 動態倉位（Bull=100%, Neutral=50%, Bear=0%）
3. 成交量確認 Vol Ratio > 1.5x
4. VCP 形態篩選

## 篩選條件
- Trend Score 6/8 以上
- RS Rating 70 以上
- EPS 或營收成長 20% 以上
- 距52週高點 35% 以內
