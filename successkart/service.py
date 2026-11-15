import logging
from telegram.error import RetryAfter, TimedOut, NetworkError, Forbidden
from .db import connection
from .matching import matches
log=logging.getLogger(__name__)

def render(job):
    return (f"📣 {job['opportunity_type']}: {job['title']}\n🏢 Company: {job['company']}\n"
      f"📍 Location: {job['location']}\n💰 Stipend/Salary: {job['stipend_text']}\n"
      f"📰 Source: {job['source']}\n"
      f"🧩 Skills: {job['skills'] or 'Not specified'}\n🎓 Eligibility: {job['qualification'] or 'Check application page'}\n"
      f"⏳ Deadline: {job['deadline']}\n🔗 Apply: {job['url']}")

async def deliver_pending(bot,db_path,max_attempts,batch=100,user_id=None):
    with connection(db_path) as db:
        query="""SELECT d.id,d.user_id,d.opportunity_id,d.attempts,o.*
          FROM deliveries d JOIN opportunities o ON o.id=d.opportunity_id
          WHERE d.status='pending' AND d.attempts<? AND
          (d.next_attempt_at IS NULL OR d.next_attempt_at<=CURRENT_TIMESTAMP) AND o.status='published'"""
        params=[max_attempts]
        if user_id is not None:
            query += " AND d.user_id=?"
            params.append(user_id)
        query += " ORDER BY d.id LIMIT ?"
        params.append(batch)
        rows=db.execute(query,params).fetchall()
    sent=0
    for row in rows:
        try:
            await bot.send_message(row["user_id"],render(row),disable_web_page_preview=True)
            with connection(db_path) as db:
                db.execute("UPDATE deliveries SET status='sent',attempts=attempts+1,sent_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=?",(row["id"],))
            sent+=1
        except RetryAfter as exc:
            delay=max(5,int(exc.retry_after))
            attempt = row["attempts"] + 1
            status = "failed" if attempt >= max_attempts else "pending"
            with connection(db_path) as db:
                db.execute("UPDATE deliveries SET status=?,attempts=?,next_attempt_at=datetime('now',?),last_error=? WHERE id=?",
                    (status,attempt,f"+{delay} seconds",str(exc)[:400],row["id"]))
        except Forbidden as exc:
            with connection(db_path) as db:
                db.execute("UPDATE deliveries SET status='failed',attempts=?,last_error=? WHERE id=?",
                    (max_attempts,str(exc)[:400],row["id"]))
        except (TimedOut,NetworkError,Exception) as exc:
            attempt=row["attempts"]+1
            delay=min(360,15*(2**attempt))
            status="failed" if attempt>=max_attempts else "pending"
            with connection(db_path) as db:
                db.execute("UPDATE deliveries SET status=?,attempts=?,next_attempt_at=datetime('now',?),last_error=? WHERE id=?",
                    (status,attempt,f"+{delay} seconds",str(exc)[:400],row["id"]))
            log.warning("Send failed user=%s job=%s attempt=%s: %s",row["user_id"],row["opportunity_id"],attempt,exc)
    return sent

async def queue_opportunity(bot,db_path,job_id,max_attempts):
    with connection(db_path) as db:
        job=db.execute("SELECT * FROM opportunities WHERE id=? AND status='published'",(job_id,)).fetchone()
        users=db.execute("SELECT * FROM users WHERE active=1").fetchall()
        if not job: return 0
        count=0
        for user in users:
            if user["notification_mode"]=="matching" and not matches(user,job): continue
            cur=db.execute("INSERT OR IGNORE INTO deliveries(user_id,opportunity_id,status) VALUES(?,?,'pending')",
                           (user["telegram_id"],job_id))
            count+=cur.rowcount
    await deliver_pending(bot,db_path,max_attempts)
    return count


async def queue_recent_for_user(bot,db_path,user_id,max_attempts,limit=10):
    """Queue recent already-collected listings for a newly registered user."""
    from .matching import matches
    with connection(db_path) as db:
        user=db.execute("SELECT * FROM users WHERE telegram_id=? AND active=1",(user_id,)).fetchone()
        if not user:
            return 0
        jobs=db.execute("""SELECT * FROM opportunities WHERE status='published'
            AND created_at >= datetime('now','-14 days') ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
        queued=0
        for job in jobs:
            if user['notification_mode'] != 'all' and not matches(user,job):
                continue
            cur=db.execute("INSERT OR IGNORE INTO deliveries(user_id,opportunity_id,status) VALUES(?,?,'pending')",
                           (user_id,job['id']))
            queued += max(cur.rowcount,0)
    if queued:
        await deliver_pending(bot,db_path,max_attempts,batch=limit,user_id=user_id)
    return queued
