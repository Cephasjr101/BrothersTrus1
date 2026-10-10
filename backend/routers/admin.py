# Admin: stats, analytics, bookings, users (with booking counts + spend).
import json
import sqlite3

from fastapi import APIRouter, Depends

from database import get_db
from deps import admin_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _scalar(db, sql, args=()):
    return db.execute(sql, args).fetchone()[0]


@router.get("/stats")
def stats(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    by_type = {r["type"]: r["n"] for r in db.execute(
        "SELECT type, COUNT(*) AS n FROM bookings GROUP BY type")}
    by_status = {r["status"]: r["n"] for r in db.execute(
        "SELECT status, COUNT(*) AS n FROM bookings GROUP BY status")}
    daily = db.execute(
        "SELECT date(created_at) AS d, COUNT(*) AS n, COALESCE(SUM(amount),0) AS rev "
        "FROM bookings WHERE status='confirmed' GROUP BY date(created_at) ORDER BY d DESC LIMIT 14").fetchall()
    return {
        "users": _scalar(db, "SELECT COUNT(*) FROM users"),
        "bookings": _scalar(db, "SELECT COUNT(*) FROM bookings"),
        "by_type": by_type, "by_status": by_status,
        "revenue_confirmed": _scalar(db, "SELECT COALESCE(SUM(amount),0) FROM bookings WHERE status='confirmed'"),
        "revenue_pending": _scalar(db, "SELECT COALESCE(SUM(amount),0) FROM bookings WHERE status='pending'"),
        "daily": [{"date": r["d"], "bookings": r["n"], "revenue": r["rev"]} for r in daily],
    }


@router.get("/analytics")
def analytics(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    pageviews = _scalar(db, "SELECT COUNT(*) FROM analytics WHERE kind='page_view'")
    events = {r["kind"]: r["n"] for r in db.execute(
        "SELECT kind, COUNT(*) AS n FROM analytics WHERE kind!='page_view' GROUP BY kind")}
    top_pages = db.execute(
        "SELECT page, COUNT(*) AS n FROM analytics WHERE kind='page_view' "
        "GROUP BY page ORDER BY n DESC LIMIT 10").fetchall()
    daily = db.execute(
        "SELECT date(created_at) AS d, COUNT(*) AS n FROM analytics "
        "WHERE created_at >= datetime('now', '-14 days') GROUP BY date(created_at) ORDER BY d").fetchall()
    return {
        "pageviews": pageviews,
        "events": events,
        "top_pages": [{"page": r["page"], "views": r["n"]} for r in top_pages],
        "daily": [{"date": r["d"], "views": r["n"]} for r in daily],
        "max_daily": max([r["n"] for r in daily], default=1),
    }


@router.get("/bookings")
def all_bookings(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    rows = db.execute(
        "SELECT b.*, u.email FROM bookings b JOIN users u ON u.id=b.user_id "
        "ORDER BY b.created_at DESC LIMIT 200").fetchall()
    return [{"reference": r["reference"], "type": r["type"], "status": r["status"],
             "amount": r["amount"], "email": r["email"],
             "travelers": json.loads(r["travelers"]), "created_at": r["created_at"]} for r in rows]


@router.get("/users")
def all_users(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    rows = db.execute(
        """SELECT u.id, u.email, u.full_name, u.phone, u.role, u.created_at,
                  COUNT(b.id) AS bookings,
                  COALESCE(SUM(CASE WHEN b.status='confirmed' THEN b.amount END), 0) AS spent
           FROM users u LEFT JOIN bookings b ON b.user_id = u.id
           GROUP BY u.id ORDER BY bookings DESC, u.created_at DESC LIMIT 200""").fetchall()
    return [dict(r) for r in rows]
