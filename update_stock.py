import os
import sys
import time
import random
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
    """從美股 Notion Database 取得所有股票資料"""
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
            
            # 同時支援名為 'Ticker' 或 'Name' 的欄位
            ticker = ""
            for field_name in ["Ticker", "Name"]:
                ticker_data = properties.get(field_name, {})
                ticker_type = ticker_data.get("type")
                
                if ticker_type == "rich_text" and ticker_data.get("rich_text"):
                    ticker = "".join([t["plain_text"] for t in ticker_data["rich_text"]]).strip()
                    break
                elif ticker_type == "title" and ticker_data.get("title"):
                    ticker = "".join([t["plain_text"] for t in ticker_data["title"]]).strip()
                    break
                
            if ticker:
                stocks.append({"page_id": page_id, "ticker": ticker})
                
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
        
    return stocks

def get_single_stock_price(ticker):
    """個別抓取最新美股股價"""
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.get('last_price')
        
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
    print("開始執行【美股】Notion 股價更新排程...")
    
    stocks = get_notion_stocks()
    if not stocks:
        print("美股 Database 中沒有找到任何股票代號。")
        return
        
    print(f"成功從 Notion 讀取到 {len(stocks)} 筆美股資料。")
    
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
            
        # 隨機休息 1.5 ~ 2.5 秒，防止被 Yahoo Finance 限流封鎖
        time.sleep(random.uniform(1.5, 2.5))
            
    print(f"執行完畢！美股成功更新 {success_count} / {len(stocks)} 筆資料。")

if __name__ == "__main__":
    main()
    
