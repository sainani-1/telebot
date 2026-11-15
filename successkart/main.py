import logging
from .config import load_config
from .bot import build
if __name__=="__main__":
    cfg=load_config()
    logging.basicConfig(level=getattr(logging,cfg.log_level,logging.INFO),format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.info("Starting SuccessKart Telegram bot.")
    build(cfg).run_polling(allowed_updates=["message","callback_query"])
