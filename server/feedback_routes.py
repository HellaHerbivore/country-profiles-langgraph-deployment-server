"""
Feedback & Query-Log API routes for user testing.

Endpoints:
  POST /api/feedback          — submit feedback (authenticated)
  GET  /api/feedback/export   — CSV/JSON export of feedback
  GET  /api/query-logs/export — CSV/JSON export of query logs
  GET  /api/admin             — simple HTML dashboard
"""

import csv
import io
import json
import logging
import os

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from server.models import Feedback, QueryLog, get_session_factory

logger = logging.getLogger(__name__)


# ── POST /api/feedback ──

async def submit_feedback(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    user_id = getattr(request.state, "user_id", None)

    # Resolve email via Clerk Backend API
    user_email = None
    if user_id:
        try:
            import httpx
            secret = os.getenv("CLERK_SECRET_KEY")
            if secret:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"https://api.clerk.com/v1/users/{user_id}",
                        headers={"Authorization": f"Bearer {secret}"},
                    )
                    if resp.status_code == 200:
                        addrs = resp.json().get("email_addresses", [])
                        if addrs:
                            user_email = addrs[0].get("email_address")
        except Exception as e:
            logger.debug(f"Could not resolve email: {e}")

    session = get_session_factory()()
    try:
        session.add(Feedback(
            user_id=user_id,
            user_email=user_email,
            feedback_type=body.get("feedback_type", "general"),
            message=message,
            page_context=json.dumps(body.get("page_context")) if body.get("page_context") else None,
        ))
        session.commit()
    finally:
        session.close()

    return JSONResponse({"status": "ok"})


# ── GET /api/feedback/export ──

async def export_feedback(request: Request) -> Response:
    fmt = request.query_params.get("format", "csv")
    session = get_session_factory()()
    try:
        rows = session.query(Feedback).order_by(Feedback.created_at.desc()).all()
        data = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_email": r.user_email,
                "feedback_type": r.feedback_type,
                "message": r.message,
                "page_context": r.page_context,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    finally:
        session.close()

    if fmt == "json":
        return JSONResponse(data)
    return _csv_response(data, "feedback.csv")


# ── GET /api/query-logs/export ──

async def export_query_logs(request: Request) -> Response:
    fmt = request.query_params.get("format", "csv")
    session = get_session_factory()()
    try:
        rows = session.query(QueryLog).order_by(QueryLog.created_at.desc()).all()
        data = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_email": r.user_email,
                "topic": r.topic,
                "max_analysts": r.max_analysts,
                "thread_id": r.thread_id,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    finally:
        session.close()

    if fmt == "json":
        return JSONResponse(data)
    return _csv_response(data, "query_logs.csv")


# ── GET /api/admin ──

async def admin_dashboard(request: Request) -> Response:
    session = get_session_factory()()
    try:
        feedbacks = session.query(Feedback).order_by(Feedback.created_at.desc()).limit(100).all()
        queries = session.query(QueryLog).order_by(QueryLog.created_at.desc()).limit(100).all()
        total_queries = session.query(QueryLog).count()
        total_feedback = session.query(Feedback).count()
        unique_users = session.query(QueryLog.user_id).distinct().count()
    finally:
        session.close()

    def _fb_rows():
        out = ""
        for f in feedbacks:
            ctx = ""
            if f.page_context:
                try:
                    ctx = json.loads(f.page_context).get("topic", "")
                except Exception:
                    ctx = f.page_context[:60]
            out += f"<tr><td>{f.created_at}</td><td>{f.user_email or f.user_id or '—'}</td><td>{f.feedback_type}</td><td>{f.message}</td><td>{ctx}</td></tr>\n"
        return out

    def _ql_rows():
        out = ""
        for q in queries:
            out += f"<tr><td>{q.created_at}</td><td>{q.user_email or q.user_id or '—'}</td><td>{q.topic}</td><td>{q.max_analysts}</td></tr>\n"
        return out

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Testing Admin</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #fafaf8; color: #1a1a1a; }}
h1 {{ font-size: 1.5rem; }}
h2 {{ font-size: 1.125rem; margin-top: 2rem; }}
.stats {{ display: flex; gap: 1.5rem; margin: 1rem 0; }}
.stat {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem 1.5rem; }}
.stat-val {{ font-size: 1.5rem; font-weight: 700; }}
.stat-label {{ font-size: 0.8rem; color: #666; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #fff; }}
th, td {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #eee; }}
th {{ background: #f5f5f0; font-weight: 600; }}
a.btn {{ display: inline-block; margin: 0.5rem 0.25rem; padding: 0.4rem 1rem; background: #00081e; color: #fff; text-decoration: none; border-radius: 4px; font-size: 0.8rem; }}
</style></head><body>
<h1>Country Profiles — Testing Dashboard</h1>
<div class="stats">
  <div class="stat"><div class="stat-val">{total_queries}</div><div class="stat-label">Total Queries</div></div>
  <div class="stat"><div class="stat-val">{unique_users}</div><div class="stat-label">Unique Users</div></div>
  <div class="stat"><div class="stat-val">{total_feedback}</div><div class="stat-label">Feedback Items</div></div>
</div>

<h2>Feedback</h2>
<a class="btn" href="/api/feedback/export?format=csv">Download CSV</a>
<a class="btn" href="/api/feedback/export?format=json">Download JSON</a>
<table><tr><th>Time</th><th>User</th><th>Type</th><th>Message</th><th>Context</th></tr>
{_fb_rows()}
</table>

<h2>Query Logs</h2>
<a class="btn" href="/api/query-logs/export?format=csv">Download CSV</a>
<a class="btn" href="/api/query-logs/export?format=json">Download JSON</a>
<table><tr><th>Time</th><th>User</th><th>Topic</th><th>Analysts</th></tr>
{_ql_rows()}
</table>
</body></html>"""

    return HTMLResponse(html)


# ── Helpers ──

def _csv_response(data: list, filename: str) -> Response:
    if not data:
        return Response("No data", media_type="text/plain")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Route list (import this in app.py) ──

feedback_routes = [
    Route("/api/feedback", submit_feedback, methods=["POST"]),
    Route("/api/feedback/export", export_feedback, methods=["GET"]),
    Route("/api/query-logs/export", export_query_logs, methods=["GET"]),
    Route("/api/admin", admin_dashboard, methods=["GET"]),
]
