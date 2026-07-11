import os
import sys
from notion_client import Client
import yfinance as yf

# 1. 初始化 Notion Client
notion_token = os.environ.get("NOTION_TOKEN")
database_id = os.environ.get("DATABASE_ID")

if not notion_token or not database_id:
    print("錯誤：找不到 NOTION_TOKEN 或 DATABASE_ID 環境變數。")
    sys.exit(1)

notion = Client(auth=notion_token)

def get_notion_stocks():
    """從 Notion Database 取得所有股票資料"""
    stocks = []
    has_more = True
    start_cursor = None
    
    while has_more:
        kwargs = {"database_id": database_id}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
            
        response = notion.databases.query(**kwargs)
        
        for row in response.get("results", []):
            page_id = row["id"]
            properties = row.get("properties", {})
            
            # 取得 Ticker 欄位
            ticker_data = properties.get("Ticker", {})
            ticker_type = ticker_data.get("type")
            
            ticker = ""
            # 同時支援 Rich Text (文字屬性) 與 Title (標題屬性)
            if ticker_type == "rich_text" and ticker_data.get("rich_text"):
                ticker = "".join([t["plain_text"] for t in ticker_data["rich_text"]]).strip()
            elif ticker_type == "title" and ticker_data.get("title"):
                ticker = "".join([t["plain_text"] for t in ticker_data["title"]]).strip()
                
            if ticker:
                stocks.append({"page_id": page_id, "ticker": ticker})
                
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
        
    return stocks

def get_single_stock_price(ticker):
    """改用 yf.Ticker 個別抓取最新股價，避開 download() 的環境衝突問題"""
    try:
        t = yf.Ticker(ticker)
        # 嘗試從 fast_info 取得最新價格
        price = t.fast_info.get('last_price')
        
        # 如果 fast_info 拿不到，改從 history 拿最後一筆收盤價
        if price is None:
            hist = t.history(period="1d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                
        if price is not None and price > 0:
            return round(float(price), 2)
    except Exception as e:
        print(f"查詢 {ticker} 股價時發生錯誤: {e}")
    return None

def update_notion_price(page_id, price):
    """更新 Notion 的 Current price 欄位"""
    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "Current price": {
                    "number": price
                }
            }
        )
        return True
    except Exception as e:
        print(f"更新 Notion 失敗 (Page ID: {page_id}): {e}")
        return False

def main():
    print("開始執行 Notion 股價更新排程...")
    
    # 步驟 1: 抓取 Notion 資料
    stocks = get_notion_stocks()
    if not stocks:
        print("Notion Database 中沒有找到任何 Ticker，請確認欄位名稱是否為 'Ticker' 且有資料。")
        return
        
    print(f"成功從 Notion 讀取到 {len(stocks)} 筆股票資料。")
    
    # 步驟 2 & 步驟 3: 逐一查詢並更新到 Notion
    success_count = 0
    for stock in stocks:
        ticker = stock["ticker"]
        page_id = stock["page_id"]
        
        print(f"正在查詢 {ticker} 的最新股價...")
        price = get_single_stock_price(ticker)
        
        if price is not None:
            if update_notion_price(page_id, price):
                print(f"成功更新 {ticker}: ${price}")
                success_count += 1
        else:
            print(f"跳過 {ticker}：未能取得有效股價。")
            
    print(f"執行完畢！成功更新 {success_count} / {len(stocks)} 筆資料。")

if __name__ == "__main__":
    main()
