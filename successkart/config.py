import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Config:
    token: str
    admins: set[int]
    db: str
    poll_minutes: int
    max_items: int
    max_attempts: int
    retry_minutes: int
    timeout: int
    log_level: str
    apish_api_key: str

def load_config():
    token=os.getenv("BOT_TOKEN","").strip()
    if not token or token=="replace_with_real_token":
        raise RuntimeError("Set BOT_TOKEN in .env")
    admins={int(x.strip()) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()}
    if not admins:
        raise RuntimeError("Set ADMIN_IDS to your numeric Telegram user ID")
    return Config(token,admins,os.getenv("DATABASE_PATH","/data/successkart.db"),
        max(2,int(os.getenv("POLL_INTERVAL_MINUTES","10"))),
        max(10,int(os.getenv("MAX_ITEMS_PER_SOURCE","250"))),
        max(1,int(os.getenv("DELIVERY_MAX_ATTEMPTS","5"))),
        max(1,int(os.getenv("DELIVERY_RETRY_INTERVAL_MINUTES","3"))),
        max(5,int(os.getenv("HTTP_TIMEOUT_SECONDS","25"))),
        os.getenv("LOG_LEVEL","INFO").upper(),
        os.getenv("APISH_API_KEY", "").strip())
