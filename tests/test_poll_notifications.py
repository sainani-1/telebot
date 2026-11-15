import asyncio
from types import SimpleNamespace

from successkart import bot as bot_module
from successkart.db import init_db, connection


class FakeBot:
    def __init__(self):
        self.sent = []
    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


class FakeContext:
    def __init__(self, db_path, fake_bot):
        self.bot = fake_bot
        self.application = SimpleNamespace(bot_data={
            "db": db_path, "timeout": 5, "max_items": 20, "max_attempts": 3
        })


def test_poll_writes_source_health_and_sends_new_matching_alert(tmp_path, monkeypatch):
    db_path = str(tmp_path / "successkart.db")
    init_db(db_path)
    with connection(db_path) as db:
        db.execute("""INSERT INTO users(telegram_id,name,qualification,grad_year,skills,
            opportunity_type,location_preference,min_stipend,notification_mode)
            VALUES(1,'Test','B.Tech','2027','Python','Internship','Any',NULL,'all')""")

    item = {
        "source_key": "test-source-item", "source": "Test Feed", "title": "Python Intern",
        "company": "Example Ltd", "skills": "Python", "qualification": "B.Tech",
        "location": "Remote", "stipend_text": "Not disclosed", "stipend_min": None,
        "deadline": "Not specified", "url": "https://example.com/apply",
        "description": "Python internship", "opportunity_type": "Internship"
    }

    async def fake_fetch_all(timeout, limit):
        return [item], [{"source": "Test Feed", "ok": True, "count": 1, "error": None}]

    monkeypatch.setattr(bot_module, "fetch_all", fake_fetch_all)
    fake_bot = FakeBot()
    asyncio.run(bot_module.poll(FakeContext(db_path, fake_bot)))

    with connection(db_path) as db:
        health = db.execute("SELECT * FROM source_health WHERE source='Test Feed'").fetchone()
        delivery = db.execute("SELECT status FROM deliveries WHERE user_id=1").fetchone()
    assert health["last_status"] == "OK"
    assert health["items_seen"] == 1
    assert delivery["status"] == "sent"
    assert len(fake_bot.sent) == 1
