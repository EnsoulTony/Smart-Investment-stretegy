"""持倉重算模組（Position Rebuilder）。

本模組負責從 trades 表重新計算每個用戶的當前持倉狀態。

架構分層：
- Router (main.py) ➜ 接收 HTTP 請求，處理身份驗證
- Service (本模組) ➜ 協調業務流程，處理錯誤
- Calculator (avg_cost_calculator.py) ➜ 純函數，實作均價法計算邏輯
- Repository (trades_repository.py) ➜ 資料庫 CRUD 操作

當前階段（Sprint 1-4.2）：
- ✅ 建立骨架結構（Sprint 1-4.0）
- ✅ 均價法計算邏輯（Sprint 1-4.1）
- ✅ DB 查詢與預覽重算（Sprint 1-4.2）
- ⏸ positions 表寫入（Sprint 1-4.3）
- ⏸ 外幣折算（未來）
"""

import logging
import hashlib
import json
from sqlalchemy.orm import Session
from typing import Dict, List
from decimal import Decimal
from collections import defaultdict
from datetime import datetime, timezone, date
from uuid import uuid4

from app.schemas import TradeRecord
from app.avg_cost_calculator import compute_avg_cost
from app.trades_repository import list_trades_for_user

logger = logging.getLogger(__name__)


def compute_positions_hash(positions: List[Dict]) -> str:
    """計算 positions 的穩定 hash（用於驗證 preview 與 write 的一致性）。
    
    Args:
        positions: positions 列表，每個 position 包含: symbol, asset_ccy, quantity, avg_cost, realized_pnl, u_pnl
    
    Returns:
        str: SHA256 hash (hex)
    
    規格：
    - 按 symbol 排序（避免順序差異）
    - 只取固定欄位：symbol, asset_ccy, quantity, avg_cost, realized_pnl, u_pnl
    - 數字轉為 canonical string（避免 Decimal/float 差異）
    - 不包含 last_updated_at（避免時間戳差異）
    """
    if not positions:
        return hashlib.sha256(b"").hexdigest()
    
    # 排序與正規化
    normalized = []
    for pos in sorted(positions, key=lambda p: (p.get("symbol", ""), p.get("asset_ccy", ""))):
        normalized.append({
            "symbol": pos.get("symbol", ""),
            "asset_ccy": pos.get("asset_ccy", ""),
            "quantity": str(pos.get("quantity", "0")),
            "avg_cost": str(pos.get("avg_cost", "0")),
            "realized_pnl": str(pos.get("realized_pnl", "0")),
            "u_pnl": str(pos.get("u_pnl", "0"))
        })
    
    # 計算 hash
    canonical_json = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class PositionRebuilder:
    """持倉重算服務類別。
    
    職責：
    1. 讀取指定用戶的所有交易記錄（按日期排序）
    2. 呼叫均價法計算器
    3. 寫入 positions 表
    4. 回傳重算結果與警告訊息
    
    Attributes：
        session: SQLAlchemy Session，用於資料庫操作
    """
    
    def __init__(self, session: Session):
        """初始化 PositionRebuilder。
        
        Args：
            session: SQLAlchemy Session 物件
        """
        self.session = session
    
    def rebuild_positions(self, user_id: str) -> Dict:
        """重算指定用戶的持倉狀態並寫入 positions 表。"""
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不可為空")

        logger.info("開始重算持倉並寫入 positions 表，user_id=%s", user_id)

        try:
            trades_orm = list_trades_for_user(self.session, user_id)
            grouped_trades = defaultdict(list)

            for trade_orm in trades_orm:
                # DB 中賣出交易 quantity 可能為負數，統一轉為正數
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

            # Fail Fast 驗證
            logger.info("開始 Fail Fast 驗證，user_id=%s, symbols_count=%d", user_id, len(grouped_trades))
            validation_errors = []
            for (symbol, asset_ccy), trades in grouped_trades.items():
                try:
                    compute_avg_cost(trades)
                except ValueError as e:
                    validation_errors.append({
                        "symbol": symbol,
                        "asset_ccy": asset_ccy,
                        "error": str(e),
                        "trades_count": len(trades),
                        "first_trade_date": trades[0].trade_date.isoformat() if trades else None,
                        "last_trade_date": trades[-1].trade_date.isoformat() if trades else None
                    })
                    logger.warning("驗證失敗，symbol=%s, error=%s", symbol, str(e))

            if validation_errors:
                error_summary = "\n".join([
                    f"  • {e['symbol']} ({e['asset_ccy']}): {e['error']} (共 {e['trades_count']} 筆交易)"
                    for e in validation_errors
                ])
                error_msg = (
                    f"交易資料驗證失敗，發現 {len(validation_errors)} 個問題標的：\n{error_summary}\n\n"
                    f"建議檢查 trades 資料：\n"
                    f"  docker compose exec -T postgres psql -U postgres -d portfolio -c \\\n"
                    f"    \"SELECT trade_date, action, quantity, price FROM trades WHERE user_id='{user_id}' "
                    f"AND symbol='{validation_errors[0]['symbol']}' ORDER BY trade_date, created_at;\""
                )
                logger.error("Fail Fast 驗證失敗，user_id=%s, errors_count=%d", user_id, len(validation_errors))
                raise ValueError(error_msg)

            # 開始 transaction：DELETE + INSERT (idempotent)
            upserted_count = 0
            deleted_or_zeroed_count = 0
            run_id = str(uuid4())

            try:
                from app.models import Position
                from sqlalchemy import delete

                # Step 1: 刪除該 user 的所有 positions（覆蓋語意）
                delete_stmt = delete(Position).where(Position.user_id == user_id)
                result = self.session.execute(delete_stmt)
                deleted_count = result.rowcount
                logger.info("已刪除 user 的舊 positions, user_id=%s, deleted_count=%d", user_id, deleted_count)

                # Step 2: 計算新 positions 並批次插入
                positions_to_insert = []
                for (symbol, asset_ccy), trades in grouped_trades.items():
                    state = compute_avg_cost(trades)

                    # 若 qty=0，不插入（已在 Step 1 刪除）
                    if state.qty == 0:
                        deleted_or_zeroed_count += 1
                        continue

                    positions_to_insert.append({
                        "user_id": user_id,
                        "symbol": symbol,
                        "asset_ccy": asset_ccy,
                        "quantity": state.qty,
                        "avg_cost": state.avg_cost,
                        "realized_pnl": state.realized_pnl,
                        "u_pnl": Decimal("0"),
                        "last_updated_at": datetime.now(timezone.utc)
                    })

                # Step 3: bulk insert
                if positions_to_insert:
                    self.session.bulk_insert_mappings(Position, positions_to_insert)
                    upserted_count = len(positions_to_insert)
                    logger.info("已插入新 positions, user_id=%s, inserted_count=%d", user_id, upserted_count)

                self.session.commit()

                # 計算 positions_hash
                positions_for_hash = [
                    {
                        "symbol": p["symbol"],
                        "asset_ccy": p["asset_ccy"],
                        "quantity": p["quantity"],
                        "avg_cost": p["avg_cost"],
                        "realized_pnl": p["realized_pnl"],
                        "u_pnl": p["u_pnl"]
                    }
                    for p in positions_to_insert
                ]
                # 即使 positions 為空也要 hash
                positions_hash = compute_positions_hash(positions_for_hash)

                # 獲取當前日期
                as_of = date.today().isoformat()

                evidence = {
                    "run_id": run_id,
                    "decision": "proceed",
                    "as_of": as_of,
                    "precondition_snapshot": {
                        "trades_count": len(trades_orm),
                        "distinct_symbols_count": len(grouped_trades)
                    },
                    "positions_count": upserted_count,
                    "positions_hash": positions_hash,
                    "deleted_count": deleted_count,
                    "positions_columns": list(Position.__table__.columns.keys())
                }

                result = {
                    "status": "succeeded",
                    "user_id": user_id,
                    "symbols_count": len(grouped_trades),
                    "upserted_count": upserted_count,
                    "deleted_or_zeroed_count": deleted_or_zeroed_count,
                    "run_id": run_id,
                    "positions_hash": positions_hash,
                    "evidence": evidence,
                }

                logger.info("持倉重算完成,user_id=%s, result=%s", user_id, result)
                return result

            except Exception:
                logger.exception("持倉重算 transaction 失敗,user_id=%s", user_id)
                self.session.rollback()
                raise

        except ValueError as e:
            logger.exception("持倉重算失敗（業務錯誤），user_id=%s, error=%s", user_id, str(e))
            self.session.rollback()

            # 嘗試從錯誤訊息提取 symbol
            error_symbol = None
            error_str = str(e)
            if "symbol=" in error_str:
                import re
                match = re.search(r"symbol=(\w+)", error_str)
                if match:
                    error_symbol = match.group(1)

            return {
                "status": "failed",
                "user_id": user_id,
                "symbols_count": 0,
                "upserted_count": 0,
                "deleted_or_zeroed_count": 0,
                "run_id": str(uuid4()),
                "evidence": {
                    "error_type": "ValueError",
                    "error_message": error_str,
                    "error_symbol": error_symbol,
                    "positions_columns": [],
                    "verification_sql": {
                        "trades_count": f"select count(*) from trades where user_id='{user_id}';",
                        "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';",
                        "trades_for_error_symbol": (
                            f"select trade_date, action, quantity, price from trades "
                            f"where user_id='{user_id}' and symbol='{error_symbol}' "
                            f"order by trade_date, created_at;"
                        ) if error_symbol else None
                    }
                }
            }

        except Exception as e:
            logger.exception("持倉重算失敗（系統錯誤），user_id=%s, error=%s", user_id, str(e))
            self.session.rollback()
            return {
                "status": "failed",
                "user_id": user_id,
                "symbols_count": 0,
                "upserted_count": 0,
                "deleted_or_zeroed_count": 0,
                "run_id": str(uuid4()),
                "evidence": {
                    "error_type": e.__class__.__name__,
                    "error_message": str(e),
                    "positions_columns": [],
                    "verification_sql": {
                        "trades_count": f"select count(*) from trades where user_id='{user_id}';"
                    }
                }
            }


def rebuild_positions(user_id: str, db: Session) -> Dict:
    """持倉重算的函式介面（Functional Interface）。"""
    rebuilder = PositionRebuilder(session=db)
    return rebuilder.rebuild_positions(user_id=user_id)


def preview_rebuild(user_id: str, db: Session) -> Dict:
    """預覽持倉重算結果（不寫入 DB）。"""
    if not user_id or not user_id.strip():
        raise ValueError("user_id 不可為空")

    logger.info("開始預覽持倉重算，user_id=%s", user_id)

    try:
        # 步驟 1: 從 DB 查詢交易記錄
        trades_orm = list_trades_for_user(db, user_id)
        logger.info("查詢到 %d 筆交易記錄，user_id=%s", len(trades_orm), user_id)

        # 步驟 2: 轉換為 TradeRecord（Pydantic 模型）
        trades_pydantic: List[TradeRecord] = []
        for trade_orm in trades_orm:
            try:
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
                trades_pydantic.append(trade_record)
            except Exception as e:
                logger.warning(
                    "交易記錄轉換失敗，trade_id=%s, error=%s",
                    trade_orm.id, e
                )

        logger.info("成功轉換 %d 筆交易記錄為 TradeRecord", len(trades_pydantic))

        # 步驟 3: 按 (symbol, asset_ccy) 分組
        grouped_trades = defaultdict(list)
        for trade in trades_pydantic:
            key = (trade.symbol, trade.asset_ccy)
            grouped_trades[key].append(trade)

        logger.info("交易記錄分組完成，共 %d 個標的", len(grouped_trades))

        # 步驟 4: 每組計算均價法
        symbols_result = []
        positions_for_hash_calc = []
        warnings = []

        for (symbol, asset_ccy), group_trades in grouped_trades.items():
            try:
                state = compute_avg_cost(group_trades)

                # For hash calculation, use precise Decimal values
                positions_for_hash_calc.append({
                    "symbol": symbol,
                    "asset_ccy": asset_ccy,
                    "quantity": state.qty,
                    "avg_cost": state.avg_cost,
                    "realized_pnl": state.realized_pnl,
                    "u_pnl": 0
                })

                # For JSON response, convert Decimals to floats
                symbols_result.append({
                    "symbol": symbol,
                    "asset_ccy": asset_ccy,
                    "qty": float(state.qty),
                    "avg_cost": float(state.avg_cost),
                    "realized_pnl": float(state.realized_pnl),
                    "total_fee": float(state.total_fee),
                    "trades_count": len(group_trades)
                })

                logger.debug(
                    "計算完成：symbol=%s, asset_ccy=%s, qty=%s, avg_cost=%s",
                    symbol, asset_ccy, state.qty, state.avg_cost
                )

            except ValueError as e:
                warning_msg = f"標的 {symbol} ({asset_ccy}) 計算失敗：{str(e)}"
                warnings.append(warning_msg)
                logger.warning(warning_msg)

            except Exception as e:
                warning_msg = f"標的 {symbol} ({asset_ccy}) 發生未預期錯誤：{str(e)}"
                warnings.append(warning_msg)
                logger.exception(warning_msg)

        # 計算 positions_hash using the precise list
        positions_hash = compute_positions_hash(positions_for_hash_calc)

        result = {
            "status": "preview",
            "user_id": user_id,
            "positions_count": len(symbols_result),
            "positions_hash": positions_hash,
            "positions": symbols_result,
            "warnings": warnings,
            "trades_count": len(trades_pydantic),
            "distinct_symbols_count": len(grouped_trades),
            "evidence": {
                "positions_hash": positions_hash,
                "positions_count": len(symbols_result),
                "trades_count": len(trades_pydantic),
                "distinct_symbols_count": len(grouped_trades)
            }
        }

        logger.info(
            "預覽重算完成，user_id=%s, symbols_count=%d, warnings_count=%d",
            user_id, len(symbols_result), len(warnings)
        )

        return result

    except Exception:
        logger.exception("預覽重算失敗，user_id=%s", user_id)
        raise

