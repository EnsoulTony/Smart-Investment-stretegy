#!/usr/bin/env python3
"""替換 position_rebuilder.py 中的 preview_rebuild 函數"""

import re

# 讀取檔案
with open("services/portfolio-service/app/position_rebuilder.py", "r", encoding="utf-8") as f:
    content = f.read()

# 新的 preview_rebuild 實作
new_preview_rebuild = '''

def rebuild_positions(user_id: str, db: Session) -> Dict:
    """向後相容的 rebuild_positions 函數（僅供 main.py 使用）。"""
    rebuilder = PositionRebuilder(session=db)
    return rebuilder.rebuild_positions(user_id=user_id)


def preview_rebuild(user_id: str, db: Session) -> Dict:
    """預覽 rebuild_positions 的計算結果（不寫DB）。
    
    與 rebuild_positions 共享計算邏輯，但：
    - 不寫入 DB
    - 回傳 computed_positions_hash 用於與 write 比對
    - status 為 "preview" 而非 "succeeded"
    
    Args:
        user_id: 使用者 ID
        db: SQLAlchemy Session
    
    Returns:
        dict: 預覽結果，包含 positions_hash 和完整 evidence
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id 不可為空")
    
    logger.info("開始預覽持倉重算（不寫DB），user_id=%s", user_id)
    
    try:
        trades_orm = list_trades_for_user(db, user_id)
        grouped_trades = defaultdict(list)
        
        for trade_orm in trades_orm:
            quantity = abs(trade_orm.quantity)
            trade_record = TradeRecord(
                user_id=trade_orm.user_id,
                symbol=trade_orm.symbol,
                asset_ccy=trade_orm.asset_ccy,
                side=trade_orm.side,
                quantity=quantity,
                price=trade_orm.price,
                fee=trade_orm.fee,
                trade_date=trade_orm.trade_date,
                broker=trade_orm.broker
            )
            grouped_trades[(trade_record.symbol, trade_record.asset_ccy)].append(trade_record)
        
        # 計算 positions（與 write 共享邏輯）
        computed_positions = []
        for (symbol, asset_ccy), trades in grouped_trades.items():
            state = compute_avg_cost(trades)
            
            # qty=0 的不包含在結果中
            if state.qty == 0:
                continue
            
            computed_positions.append({
                "symbol": symbol,
                "asset_ccy": asset_ccy,
                "quantity": state.qty,
                "avg_cost": state.avg_cost,
                "realized_pnl": state.realized_pnl,
                "u_pnl": Decimal("0"),
                "qty": float(state.qty),  # 相容舊格式
                "total_fee": sum(t.fee for t in trades),
                "trades_count": len(trades)
            })
        
        # 計算 hash
        positions_hash = compute_positions_hash(computed_positions)
        
        # 獲取當前日期
        as_of = date.today().isoformat()
        
        evidence = {
            "decision": "proceed",
            "as_of": as_of,
            "precondition_snapshot": {
                "trades_count": len(trades_orm),
                "distinct_symbols_count": len(grouped_trades)
            },
            "positions_count": len(computed_positions),
            "computed_positions_hash": positions_hash,
            "verification_sql": {
                "trades_count": f"select count(*) from trades where user_id='{user_id}';",
                "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';",
                "positions_count": "N/A (preview mode)"
            }
        }
        
        result = {
            "status": "preview",
            "user_id": user_id,
            "computed_positions_count": len(computed_positions),
            "computed_positions_hash": positions_hash,
            "positions": computed_positions,  # 完整列表或前N筆
            "evidence": evidence
        }
        
        logger.info("持倉預覽完成,user_id=%s, computed_count=%d", user_id, len(computed_positions))
        return result
        
    except Exception as e:
        logger.exception("持倉預覽失敗，user_id=%s", user_id)
        raise
'''

# 找到所有從 def rebuild_positions(user_id: str, db: Session) 開始到檔案結尾的部分
pattern = r'\n\ndef rebuild_positions\(user_id: str, db: Session\).*$'
if re.search(pattern, content, re.DOTALL):
    # 替換掉從該函數到檔案結尾的所有內容
    content = re.sub(pattern, new_preview_rebuild, content, flags=re.DOTALL)
    
    # 寫回檔案
    with open("services/portfolio-service/app/position_rebuilder.py", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ preview_rebuild 函數替換成功")
else:
    print("❌ 找不到 rebuild_positions(user_id: str, db: Session) 函數")
