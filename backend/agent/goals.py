"""
Goal progress computation.
Used by the /goals API and the detect_goal_risks agent module.
"""
from datetime import datetime
from backend.storage.database import db


def compute_progress(goal: dict) -> dict:
    """
    Add live progress fields to a goal dict:
      current_amount, progress_pct, days_left, on_track
    """
    g = dict(goal)
    goal_type = g["goal_type"]
    target = g["target_amount"] or 0

    current = _compute_current(g)
    g["current_amount"] = current

    if target > 0:
        if goal_type == "spend_limit":
            # Lower is better — progress shows how much of the limit is used
            g["progress_pct"] = round(min(current / target * 100, 150), 1)
            g["on_track"] = current <= target
        else:
            # Higher is better — progress toward the target
            g["progress_pct"] = round(min(current / target * 100, 100), 1)
            g["on_track"] = current >= target
    else:
        g["progress_pct"] = 0.0
        g["on_track"] = True

    g["days_left"] = _days_left(g)
    return g


def _compute_current(goal: dict) -> float:
    goal_type = goal["goal_type"]
    period = goal.get("period", "monthly")

    date_filter = _date_filter(period, goal.get("target_date"))

    with db() as conn:
        if goal_type == "spend_limit":
            category = goal.get("category")
            if category:
                row = conn.execute(
                    f"""SELECT COALESCE(SUM(amount), 0) as total
                        FROM transactions
                        WHERE transaction_type='debit'
                          AND category = ?
                          AND {date_filter}""",
                    (category,),
                ).fetchone()
            else:
                row = conn.execute(
                    f"""SELECT COALESCE(SUM(amount), 0) as total
                        FROM transactions
                        WHERE transaction_type='debit'
                          AND {date_filter}"""
                ).fetchone()
            return row["total"]

        elif goal_type == "savings":
            income = conn.execute(
                f"""SELECT COALESCE(SUM(amount), 0) as total
                    FROM transactions
                    WHERE transaction_type='credit'
                      AND {date_filter}"""
            ).fetchone()["total"]
            expenses = conn.execute(
                f"""SELECT COALESCE(SUM(amount), 0) as total
                    FROM transactions
                    WHERE transaction_type='debit'
                      AND {date_filter}"""
            ).fetchone()["total"]
            return max(income - expenses, 0)

        elif goal_type == "investment":
            row = conn.execute(
                """SELECT COALESCE(SUM(total_value), 0) as total
                   FROM investment_holdings
                   WHERE as_of_date = (SELECT MAX(as_of_date) FROM investment_holdings)"""
            ).fetchone()
            return row["total"]

        else:
            return 0.0


def _date_filter(period: str, target_date: str | None) -> str:
    if period == "monthly":
        return "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
    elif period == "yearly":
        return "strftime('%Y', date) = strftime('%Y', 'now')"
    elif period == "one_time" and target_date:
        created_placeholder = "date('now', '-365 days')"  # broad window
        return f"date >= {created_placeholder}"
    return "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"


def _days_left(goal: dict) -> int | None:
    target_date = goal.get("target_date")
    if not target_date:
        if goal.get("period") == "monthly":
            today = datetime.now()
            # Days left in current month
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]
            return last_day - today.day
        return None
    try:
        td = datetime.strptime(target_date, "%Y-%m-%d")
        return max((td - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days, 0)
    except ValueError:
        return None
