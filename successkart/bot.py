import logging, hashlib, re
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
                      BotCommandScopeChat, BotCommandScopeDefault)
from telegram.ext import (Application, CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, filters)
from .db import connection,init_db
from .matching import parse_stipend
from .sources import fetch_all, search_partner_sources
from .service import queue_opportunity,deliver_pending,render,queue_recent_for_user
from .portals import PORTALS, build_portal_searches
from html import escape
log=logging.getLogger(__name__)

# Registration: use buttons for constrained choices; keep genuinely personal fields as text.
RN, RQ, RY, RS, RT, RL, RLCITY, RMIN, RMINCUSTOM, RMODE = range(10)
AT, AC, AS, AQ, AL, AP, AD, AU, AX, AK = range(10, 20)

USER_COMMANDS = [
    BotCommand("start", "Open SuccessKart"),
    BotCommand("register", "Create or update your profile"),
    BotCommand("jobs", "Browse all opportunities"),
    BotCommand("internships", "Browse internships"),
    BotCommand("government", "Browse government recruitment"),
    BotCommand("remote", "Browse remote opportunities"),
    BotCommand("search", "Search by keywords"),
    BotCommand("settings", "View your saved preferences"),
    BotCommand("notifications", "Check alert delivery status"),
    BotCommand("catchup", "Get recent matching listings"),
    BotCommand("testalert", "Test Telegram notifications"),
    BotCommand("mode", "Choose skill-matched or all alerts"),
    BotCommand("pause", "Pause notifications"),
    BotCommand("resume", "Resume notifications"),
    BotCommand("sources", "View connected sources"),
    BotCommand("help", "Show all commands"),
]
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("addinternship", "Publish a job or internship"),
    BotCommand("adminstats", "View users, alerts and source health"),
    BotCommand("adminjobs", "List published opportunities"),
    BotCommand("deletejob", "Hide a listing by ID"),
    BotCommand("retryfailed", "Retry failed notifications"),
    BotCommand("refresh", "Fetch connected sources now"),
]

def db(c): return c.application.bot_data["db"]
def admin(u,c): return bool(u.effective_user and u.effective_user.id in c.application.bot_data["admins"])

def keyboard(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows])

async def prompt(u, text, rows):
    await u.message.reply_text(text, reply_markup=keyboard(rows))

async def cb_prompt(q, text, rows):
    await q.edit_message_text(text, reply_markup=keyboard(rows))

async def start(u,c):
    with connection(db(c)) as x:
        found=x.execute("SELECT 1 FROM users WHERE telegram_id=?",(u.effective_user.id,)).fetchone()
    commands=ADMIN_COMMANDS if admin(u,c) else USER_COMMANDS
    try:
        await c.bot.set_my_commands(commands,scope=BotCommandScopeChat(chat_id=u.effective_chat.id))
    except Exception as exc:
        log.warning("Could not set role-based Telegram command menu: %s",exc)
    role="Administrator" if admin(u,c) else "User"
    await u.message.reply_text(
        f"<b>Welcome to SuccessKart</b>\nAccount type: {role}\n\n"
        + ("Use /settings to manage your profile." if found else "Use /register to create your job profile.")
        + "\n\nOpen the bot command menu or use /help to see all commands available to your role.",
        parse_mode="HTML")

async def register(u,c):
    c.user_data.clear()
    await u.message.reply_text("Let's set up your job preferences. You can cancel anytime with /cancel.\n\nWhat is your name?")
    return RN

async def rname(u,c):
    value=(u.message.text or "").strip()
    if not 2 <= len(value) <= 80:
        await u.message.reply_text("Enter a name between 2 and 80 characters.")
        return RN
    c.user_data["name"]=value
    await prompt(u,"Select your highest/current qualification:",[
        [("B.Tech / B.E.","regqual:B.Tech / B.E."),("M.Tech / M.E.","regqual:M.Tech / M.E.")],
        [("B.Sc / BCA","regqual:B.Sc / BCA"),("M.Sc / MCA","regqual:M.Sc / MCA")],
        [("Diploma","regqual:Diploma"),("12th / Intermediate","regqual:12th / Intermediate")],
        [("10th","regqual:10th"),("Other","regqual:Other")]])
    return RQ

async def rqual_cb(u,c):
    q=u.callback_query; await q.answer()
    value=q.data.split(":",1)[1]
    if value=="Other":
        await cb_prompt(q,"Type your qualification (for example: MBA, PhD, ITI):",[])
        return RQ
    c.user_data["qual"]=value
    await cb_prompt(q,"Select your expected/actual graduation year:",[
        [("2026","regyear:2026"),("2027","regyear:2027"),("2028","regyear:2028")],
        [("2029","regyear:2029"),("2030","regyear:2030"),("2031","regyear:2031")],
        [("2032 or later","regyear:2032+")]])
    return RY

async def rqual_text(u,c):
    value=(u.message.text or "").strip()
    if not 2 <= len(value) <= 80:
        await u.message.reply_text("Enter a valid qualification.")
        return RQ
    c.user_data["qual"]=value
    await prompt(u,"Select your expected/actual graduation year:",[
        [("2026","regyear:2026"),("2027","regyear:2027"),("2028","regyear:2028")],
        [("2029","regyear:2029"),("2030","regyear:2030"),("2031","regyear:2031")],
        [("2032 or later","regyear:2032+")]])
    return RY

async def ryear_cb(u,c):
    q=u.callback_query; await q.answer()
    c.user_data["year"]=q.data.split(":",1)[1]
    await cb_prompt(q,"Enter your skills separated by commas.\nExample: Python, Java, SQL, React\nYou can enter one or more skills.",[])
    return RS

async def rskills(u,c):
    value=(u.message.text or "").strip()
    if len(value)<2 or len(value)>300:
        await u.message.reply_text("Enter skills using 2–300 characters, separated by commas.")
        return RS
    c.user_data["skills"]=value
    await prompt(u,"What opportunities do you want?",[
        [("Internships","regtype:Internship"),("Full-time jobs","regtype:Full-time")],
        [("Both","regtype:Both")]])
    return RT

async def rtype_cb(u,c):
    q=u.callback_query; await q.answer()
    c.user_data["type"]=q.data.split(":",1)[1]
    await cb_prompt(q,"Choose your preferred location:",[
        [("Remote","regloc:Remote"),("Anywhere in India","regloc:India")],
        [("Any location","regloc:Any"),("Choose a city","regloc:Custom")]])
    return RL

async def rloc_cb(u,c):
    q=u.callback_query; await q.answer()
    value=q.data.split(":",1)[1]
    if value=="Custom":
        await cb_prompt(q,"Type your preferred city/state/country (for example: Vijayawada, Andhra Pradesh):",[])
        return RLCITY
    c.user_data["loc"]=value
    await cb_prompt(q,"Choose your minimum monthly stipend/salary filter:",[
        [("No minimum","regmin:0"),("₹5,000+","regmin:5000")],
        [("₹10,000+","regmin:10000"),("₹15,000+","regmin:15000")],
        [("₹20,000+","regmin:20000"),("₹30,000+","regmin:30000")],
        [("₹50,000+","regmin:50000"),("Enter amount","regmin:custom")]])
    return RMIN

async def rloc_city(u,c):
    value=(u.message.text or "").strip()
    if not 2 <= len(value) <= 100:
        await u.message.reply_text("Enter a valid city, state or country.")
        return RLCITY
    c.user_data["loc"]=value
    await u.message.reply_text("Choose your minimum monthly stipend/salary filter:",
        reply_markup=keyboard([
        [("No minimum","regmin:0"),("₹5,000+","regmin:5000")],
        [("₹10,000+","regmin:10000"),("₹15,000+","regmin:15000")],
        [("₹20,000+","regmin:20000"),("₹30,000+","regmin:30000")],
        [("₹50,000+","regmin:50000"),("Enter amount","regmin:custom")]]))
    return RMIN

async def rmin_cb(u,c):
    q=u.callback_query; await q.answer()
    value=q.data.split(":",1)[1]
    if value=="custom":
        await cb_prompt(q,"Enter a whole-number minimum monthly amount in INR (0–10,00,000):",[])
        return RMINCUSTOM
    c.user_data["min"]=int(value)
    await cb_prompt(q,"How should SuccessKart notify you?",[
        [("Skill-matched only","regmode:matching")],
        [("Every notification","regmode:all")]])
    return RMODE

async def rmin_custom(u,c):
    raw=(u.message.text or "").replace(",","").strip()
    if not raw.isdigit() or not 0 <= int(raw) <= 1000000:
        await u.message.reply_text("Enter a whole number between 0 and 10,00,000.")
        return RMINCUSTOM
    c.user_data["min"]=int(raw)
    await prompt(u,"How should SuccessKart notify you?",[
        [("Skill-matched only","regmode:matching")],
        [("Every notification","regmode:all")]])
    return RMODE

async def rmode_cb(u,c):
    q=u.callback_query; await q.answer()
    mode=q.data.split(":",1)[1]
    d=c.user_data
    with connection(db(c)) as x:
        x.execute("""INSERT INTO users(telegram_id,name,qualification,grad_year,skills,opportunity_type,location_preference,min_stipend,notification_mode)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name,qualification=excluded.qualification,
        grad_year=excluded.grad_year,skills=excluded.skills,opportunity_type=excluded.opportunity_type,
        location_preference=excluded.location_preference,min_stipend=excluded.min_stipend,notification_mode=excluded.notification_mode,
        active=1,updated_at=CURRENT_TIMESTAMP""",
        (u.effective_user.id,d["name"],d["qual"],d["year"],d["skills"],d["type"],d["loc"],d["min"] or None,mode))
    c.user_data.clear()
    await q.edit_message_text("Your SuccessKart profile has been saved. Checking existing opportunities now...")
    queued=await queue_recent_for_user(c.bot,db(c),u.effective_user.id,c.application.bot_data["max_attempts"],limit=25)
    await c.bot.send_message(u.effective_chat.id,
        "<b>SuccessKart test notification</b>\n\nYour Telegram chat is reachable. This confirms message delivery; it is not a job vacancy.",
        parse_mode="HTML")
    await c.bot.send_message(u.effective_chat.id,
        f"Recent matching opportunities queued: {queued}.\nUse /notifications to inspect alerts, /jobs to browse listings, or /help for commands.")
    return ConversationHandler.END

async def settings(u,c):
    with connection(db(c)) as x:
        r=x.execute("SELECT * FROM users WHERE telegram_id=?",(u.effective_user.id,)).fetchone()
    if not r:
        await u.message.reply_text("Register first with /register.")
        return
    await u.message.reply_text(
        f"Name: {r['name']}\nQualification: {r['qualification']}\nGraduation: {r['grad_year']}\n"
        f"Skills: {r['skills']}\nType: {r['opportunity_type']}\nLocation: {r['location_preference']}\n"
        f"Minimum monthly amount: ₹{r['min_stipend'] or 0}\n"
        f"Notifications: {'Every notification' if r['notification_mode']=='all' else 'Skill-matched only'}\n"
        f"Status: {'Active' if r['active'] else 'Paused'}\n\n"
        "Use /register to update your profile, /mode to change alert mode, /pause or /resume to control alerts.")

async def mode(u,c):
    if not c.args or c.args[0].lower() not in ("skill","all"):
        await u.message.reply_text("Choose notification mode:",reply_markup=keyboard([
            [("Skill-matched only","mode:matching"),("Every notification","mode:all")]]))
        return
    selected="matching" if c.args[0].lower()=="skill" else "all"
    with connection(db(c)) as x:
        cur=x.execute("UPDATE users SET notification_mode=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(selected,u.effective_user.id))
    await u.message.reply_text("Updated." if cur.rowcount else "Register first.")

async def mode_cb(u,c):
    q=u.callback_query; await q.answer()
    selected=q.data.split(":",1)[1]
    with connection(db(c)) as x:
        cur=x.execute("UPDATE users SET notification_mode=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",(selected,u.effective_user.id))
    await q.edit_message_text("Notification mode updated." if cur.rowcount else "Register first with /register.")

async def pause(u,c):
    with connection(db(c)) as x: cur=x.execute("UPDATE users SET active=0 WHERE telegram_id=?",(u.effective_user.id,))
    await u.message.reply_text("Alerts paused." if cur.rowcount else "Register first.")
async def resume(u,c):
    with connection(db(c)) as x: cur=x.execute("UPDATE users SET active=1 WHERE telegram_id=?",(u.effective_user.id,))
    await u.message.reply_text("Alerts resumed." if cur.rowcount else "Register first.")
async def _send_job_page(chat_id, context, page=1, category="all", edit=None):
    page=max(1,int(page)); page_size=5
    where="status='published'"
    if category=="internship":
        where += " AND lower(opportunity_type) LIKE '%intern%'"
    elif category=="government":
        where += " AND (lower(source) LIKE '%government%' OR lower(source) LIKE '%upsc%' OR lower(source) LIKE '%ssc%' OR lower(source) LIKE '%rrb%' OR lower(source) LIKE '%ibps%' OR lower(source) LIKE '%sbi%' OR lower(source) LIKE '%rbi%' OR lower(source) LIKE '%appsc%' OR lower(source) LIKE '%slprb%' OR lower(source) LIKE '%employment news%' OR lower(source) LIKE '%national career%')"
    elif category=="remote":
        where += " AND (lower(location) LIKE '%remote%' OR lower(location) LIKE '%work from home%')"
    with connection(context.application.bot_data["db"]) as x:
        total=x.execute(f"SELECT COUNT(*) n FROM opportunities WHERE {where}").fetchone()["n"]
        rows=x.execute(f"SELECT * FROM opportunities WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",(page_size,(page-1)*page_size)).fetchall()
    pages=max(1,(total+page_size-1)//page_size)
    page=min(page,pages)
    if page != 1 and not rows:
        with connection(context.application.bot_data["db"]) as x:
            rows=x.execute(f"SELECT * FROM opportunities WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",(page_size,(page-1)*page_size)).fetchall()
    label={"all":"Latest opportunities","internship":"Internships","government":"Government recruitment","remote":"Remote opportunities"}.get(category,"Opportunities")
    msg=f"<b>{label}</b>\nShowing page {page}/{pages} · {total} listings\n\n"
    if not rows:
        msg += "No listings collected in this category yet. Ask an admin to run /refresh to check connected sources."
    else:
        for r in rows:
            msg += (f"<b>{escape(r['title'])}</b> — {escape(r['company'])}\n"
                    f"{escape(r['location'] or 'Location not specified')} · {escape(r['opportunity_type'])}\n"
                    f"Pay: {escape(r['stipend_text'] or 'Not disclosed')} · Source: {escape(r['source'])}\n"
                    f"<a href=\"{escape(r['url'], quote=True)}\">View details / apply</a>\n\n")
    buttons=[]
    if page>1: buttons.append(InlineKeyboardButton("‹ Previous",callback_data=f"jobpage:{category}:{page-1}"))
    if page<pages: buttons.append(InlineKeyboardButton("Next ›",callback_data=f"jobpage:{category}:{page+1}"))
    markup=InlineKeyboardMarkup([buttons]) if buttons else None
    if edit is not None:
        await edit.edit_message_text(msg,parse_mode="HTML",disable_web_page_preview=True,reply_markup=markup)
    else:
        await context.bot.send_message(chat_id,msg,parse_mode="HTML",disable_web_page_preview=True,reply_markup=markup)

async def jobs(u,c):
    await _send_job_page(u.effective_chat.id,c,int(c.args[0]) if c.args and c.args[0].isdigit() else 1,"all")

async def internships(u,c):
    await _send_job_page(u.effective_chat.id,c,int(c.args[0]) if c.args and c.args[0].isdigit() else 1,"internship")

async def government(u,c):
    await _send_job_page(u.effective_chat.id,c,int(c.args[0]) if c.args and c.args[0].isdigit() else 1,"government")

async def remotejobs(u,c):
    await _send_job_page(u.effective_chat.id,c,int(c.args[0]) if c.args and c.args[0].isdigit() else 1,"remote")

async def job_page(u,c):
    q=u.callback_query; await q.answer()
    _,category,page=q.data.split(":",2)
    await _send_job_page(u.effective_chat.id,c,int(page),category,edit=q.message)


async def search(u,c):
    query=" ".join(c.args).strip()
    if not query:
        await u.message.reply_text("Usage: /search python internship\nSearches SuccessKart's database and connected live listing providers.")
        return
    terms=[x for x in query.split() if len(x)>1][:8]
    if not terms:
        await u.message.reply_text("Enter at least one searchable keyword."); return

    live_items, health = await search_partner_sources(query, c.application.bot_data["timeout"],
                                                       c.application.bot_data.get("apish_api_key", ""))
    imported = 0
    live_keys = []
    for item in live_items:
        with connection(db(c)) as x:
            cur=x.execute("""INSERT OR IGNORE INTO opportunities(source_key,source,title,company,skills,qualification,location,stipend_text,stipend_min,deadline,url,description,opportunity_type)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item["source_key"],item["source"],item["title"],item["company"],item["skills"],item["qualification"],item["location"],item["stipend_text"],item["stipend_min"],item["deadline"],item["url"],item["description"],item["opportunity_type"]))
            imported += max(cur.rowcount, 0)
            live_keys.append(item["source_key"])

    where=" AND ".join(["(lower(title) LIKE ? OR lower(company) LIKE ? OR lower(skills) LIKE ? OR lower(description) LIKE ? OR lower(source) LIKE ?)"]*len(terms))
    params=[]
    for term in terms:
        like=f"%{term.lower()}%"; params.extend([like]*5)
    with connection(db(c)) as x:
        live_rows=[]
        if live_keys:
            marks=",".join("?" for _ in live_keys)
            live_rows=x.execute(f"SELECT * FROM opportunities WHERE status='published' AND source_key IN ({marks}) ORDER BY id DESC LIMIT 10",live_keys).fetchall()
        extra_rows=x.execute(f"SELECT * FROM opportunities WHERE status='published' AND {where} ORDER BY id DESC LIMIT 10",params).fetchall()
        rows=list(live_rows)
        seen_ids={r["id"] for r in rows}
        rows.extend(r for r in extra_rows if r["id"] not in seen_ids)
        rows=rows[:10]

    await u.message.reply_text(f"<b>SuccessKart results for:</b> {escape(query)}\nNew live listings imported: {imported}",parse_mode="HTML")
    if rows:
        for r in rows:
            text=(f"<b>{escape(r['title'])}</b> — {escape(r['company'])}\n"
                  f"{escape(r['location'] or 'Location not specified')} | {escape(r['opportunity_type'])}\n"
                  f"Stipend/Salary: {escape(r['stipend_text'] or 'Not disclosed')}\n"
                  f"Source: {escape(r['source'])}\n"
                  f"Skills: {escape(r['skills'] or 'Not specified')}\n"
                  f"Deadline: {escape(r['deadline'] or 'Not specified')}\n"
                  f"<a href=\"{escape(r['url'], quote=True)}\">View listing / apply</a>")
            await u.message.reply_text(text,parse_mode="HTML",disable_web_page_preview=True)
    else:
        await u.message.reply_text("No matching opportunity is currently available in SuccessKart's connected feeds. Try broader keywords or check /jobs.")

    if not c.application.bot_data.get("apish_api_key"):
        await u.message.reply_text("<i>Live Unstop and Internshala import is not configured yet. Add APISH_API_KEY to your .env to enable it. No external search redirects are shown.</i>",parse_mode="HTML")
    else:
        status_lines=[f"{escape(h['source'])}: {'connected' if h['ok'] else 'unavailable'} ({h['count']} results)" for h in health]
        await u.message.reply_text("<b>Live source status</b>\n"+"\n".join(status_lines),parse_mode="HTML")


async def sources(u,c):
    await u.message.reply_text(
        "<b>SuccessKart connected sources</b>\n"
        "<b>Automatic public feeds/pages:</b> Remotive, Arbeitnow, National Career Service, Employment News, APPSC, AP SLPRB, RRB, UPSC, SSC, IBPS, SBI, RBI, ISRO and DRDO.\n\n"
        "<b>On-demand structured imports (requires APISH_API_KEY):</b> Unstop and Internshala. Results are imported into SuccessKart and displayed here with the original application link.\n\n"
        "<b>Not currently imported automatically:</b> Indeed, Naukri, LinkedIn, Foundit, Wellfound, Cutshort, Hirist, Instahyre and Glassdoor. These require approved partner access or a separately licensed data provider.\n\n"
        "Use /search <keywords> to search connected listings and /jobs to browse collected listings.",
        parse_mode="HTML",disable_web_page_preview=True)


# Admin listing fields that have fixed choices use buttons; free-form title/company/URL remain validated text.
async def addstart(u,c):
    if not admin(u,c):
        await u.message.reply_text("Admin-only.")
        return ConversationHandler.END
    c.user_data.clear()
    await u.message.reply_text("Enter the internship/job title:")
    return AT
async def at(u,c):
    v=(u.message.text or "").strip()
    if not 3<=len(v)<=240:
        await u.message.reply_text("Title must be 3–240 characters.")
        return AT
    c.user_data["title"]=v; await u.message.reply_text("Company / organization name:")
    return AC
async def ac(u,c):
    v=(u.message.text or "").strip()
    if not 2<=len(v)<=180:
        await u.message.reply_text("Company name must be 2–180 characters.")
        return AC
    c.user_data["company"]=v; await u.message.reply_text("Required skills (comma-separated; enter - if not specified):")
    return AS
async def ass(u,c):
    v=(u.message.text or "").strip()
    if len(v)>300:
        await u.message.reply_text("Keep skills under 300 characters.")
        return AS
    c.user_data["skills"]="" if v=="-" else v; await u.message.reply_text("Eligibility / qualification (or - if not specified):")
    return AQ
async def aq(u,c):
    v=(u.message.text or "").strip()
    if not 1<=len(v)<=300:
        await u.message.reply_text("Enter eligibility or -.")
        return AQ
    c.user_data["qual"]="" if v=="-" else v; await u.message.reply_text("Location (e.g. Remote, India, Hyderabad):")
    return AL
async def al(u,c):
    v=(u.message.text or "").strip()
    if not 2<=len(v)<=100:
        await u.message.reply_text("Enter a valid location.")
        return AL
    c.user_data["loc"]=v
    await prompt(u,"Select stipend/salary:",[
        [("Unpaid","adminstip:Unpaid"),("Not disclosed","adminstip:Not disclosed")],
        [("₹5,000/month","adminstip:5000/month"),("₹10,000/month","adminstip:10000/month")],
        [("₹15,000/month","adminstip:15000/month"),("₹20,000/month","adminstip:20000/month")],
        [("Enter custom amount","adminstip:custom")]])
    return AP
async def ap_cb(u,c):
    q=u.callback_query; await q.answer()
    v=q.data.split(":",1)[1]
    if v=="custom":
        await cb_prompt(q,"Enter salary/stipend (example: 25000/month or 6 LPA):",[])
        return AP
    c.user_data["stipend"]=v
    await cb_prompt(q,"Application deadline (or type Not specified):",[])
    return AD
async def ap_text(u,c):
    v=(u.message.text or "").strip()
    if not 1<=len(v)<=80:
        await u.message.reply_text("Enter a valid stipend/salary.")
        return AP
    c.user_data["stipend"]=v
    await u.message.reply_text("Application deadline (or type Not specified):")
    return AD
async def ad(u,c):
    v=(u.message.text or "").strip()
    if not 1<=len(v)<=80:
        await u.message.reply_text("Enter a valid deadline.")
        return AD
    c.user_data["deadline"]=v; await u.message.reply_text("Application URL (must start with https://):")
    return AU
async def au(u,c):
    url=(u.message.text or "").strip()
    if not re.match(r"^https://[^\s]+$",url,re.I):
        await u.message.reply_text("Enter a valid HTTPS application URL.")
        return AU
    c.user_data["url"]=url; await u.message.reply_text("Description, or - to skip:")
    return AX
async def ax(u,c):
    v=(u.message.text or "").strip()
    if len(v)>1800:
        await u.message.reply_text("Keep description under 1,800 characters.")
        return AX
    c.user_data["desc"]="" if v=="-" else v
    await prompt(u,"Select opportunity type:",[
        [("Internship","admintype:Internship"),("Full-time job","admintype:Full-time")],
        [("Government recruitment","admintype:Full-time")]])
    return AK
async def ak_cb(u,c):
    q=u.callback_query; await q.answer()
    typ=q.data.split(":",1)[1]
    d=c.user_data; key=hashlib.sha256(("admin:"+d["url"]).encode()).hexdigest()
    with connection(db(c)) as x:
        cur=x.execute("""INSERT OR IGNORE INTO opportunities(source_key,source,title,company,skills,qualification,location,stipend_text,stipend_min,deadline,url,description,opportunity_type,created_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (key,"Admin",d["title"],d["company"],d["skills"],d["qual"],d["loc"],d["stipend"],parse_stipend(d["stipend"]),d["deadline"],d["url"],d["desc"],typ,u.effective_user.id))
        row=x.execute("SELECT id FROM opportunities WHERE source_key=?",(key,)).fetchone()
    c.user_data.clear()
    if cur.rowcount:
        n=await queue_opportunity(c.bot,db(c),row["id"],c.application.bot_data["max_attempts"])
        await q.edit_message_text(f"Published. Notification records queued: {n}. Skill-based users receive it only if matched; Every notification users receive it all.")
    else:
        await q.edit_message_text("That URL already exists.")
    return ConversationHandler.END

async def cancel(u,c): c.user_data.clear(); await u.message.reply_text("Cancelled."); return ConversationHandler.END
async def stats(u,c):
    if not admin(u,c): await u.message.reply_text("Admin-only."); return
    with connection(db(c)) as x:
        users=x.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        active=x.execute("SELECT COUNT(*) n FROM users WHERE active=1").fetchone()["n"]
        listings=x.execute("SELECT COUNT(*) n FROM opportunities WHERE status='published'").fetchone()["n"]
        sent=x.execute("SELECT COUNT(*) n FROM deliveries WHERE status='sent'").fetchone()["n"]
        failed=x.execute("SELECT COUNT(*) n FROM deliveries WHERE status='failed'").fetchone()["n"]
        health=x.execute("SELECT * FROM source_health ORDER BY source").fetchall()
    msg=f"Users: {users} (active {active})\nPublished listings: {listings}\nSent alerts: {sent}\nFailed alerts: {failed}"
    for h in health: msg+=f"\n{h['source']}: {h['last_status']} | seen {h['items_seen']} | new {h['new_items']} | {h['last_error'] or 'OK'}"
    await u.message.reply_text(msg[:4000])
async def adminjobs(u,c):
    if not admin(u,c): await u.message.reply_text("Admin-only."); return
    with connection(db(c)) as x: rows=x.execute("SELECT id,title,company FROM opportunities WHERE status='published' ORDER BY id DESC LIMIT 30").fetchall()
    await u.message.reply_text("\n".join(f"#{r['id']} {r['title']} — {r['company']}" for r in rows) or "No published listings.")
async def deletejob(u,c):
    if not admin(u,c): await u.message.reply_text("Admin-only."); return
    if not c.args or not c.args[0].isdigit(): await u.message.reply_text("Usage: /deletejob ID"); return
    with connection(db(c)) as x: cur=x.execute("UPDATE opportunities SET status='deleted' WHERE id=?",(int(c.args[0]),))
    await u.message.reply_text("Listing hidden." if cur.rowcount else "ID not found.")
async def retryfailed(u,c):
    if not admin(u,c): await u.message.reply_text("Admin-only."); return
    with connection(db(c)) as x: x.execute("UPDATE deliveries SET status='pending',attempts=0,next_attempt_at=CURRENT_TIMESTAMP WHERE status='failed'")
    await u.message.reply_text("Failed delivery records reset for retry.")

async def notifications(u,c):
    with connection(db(c)) as x:
        user=x.execute("SELECT * FROM users WHERE telegram_id=?",(u.effective_user.id,)).fetchone()
        if not user:
            await u.message.reply_text("Register first with /register.")
            return
        counts=x.execute("SELECT status,COUNT(*) n FROM deliveries WHERE user_id=? GROUP BY status",(u.effective_user.id,)).fetchall()
        stats={r["status"]:r["n"] for r in counts}
        total=x.execute("SELECT COUNT(*) n FROM opportunities WHERE status='published'").fetchone()["n"]
    await u.message.reply_text(
        "<b>Your notification status</b>\n"
        f"Account: {'Active' if user['active'] else 'Paused'}\n"
        f"Mode: {'Every notification' if user['notification_mode']=='all' else 'Skill-matched only'}\n"
        f"Published listings in SuccessKart: {total}\n"
        f"Sent: {stats.get('sent',0)} · Waiting: {stats.get('pending',0)} · Failed: {stats.get('failed',0)}\n\n"
        "If no alerts have arrived, use /catchup to check recent listings. Ask an admin to run /refresh if the database has no listings.",
        parse_mode="HTML")

async def catchup(u,c):
    queued=await queue_recent_for_user(c.bot,db(c),u.effective_user.id,c.application.bot_data["max_attempts"],limit=25)
    await u.message.reply_text(f"Checked up to 25 published listings from the last 14 days. New alert records queued: {queued}.\nUse /notifications to inspect delivery status.")

async def testalert(u,c):
    await u.message.reply_text(
        "<b>SuccessKart test notification</b>\n\nThis confirms the bot can send a message to this Telegram chat. It is not a job vacancy.\nUse /notifications for real alert status.",
        parse_mode="HTML")

async def helpcmd(u,c):
    lines=["<b>SuccessKart — User commands</b>",
        "/start — Open the bot", "/register — Create/update your profile",
        "/jobs — Browse all collected opportunities", "/internships — Browse internships",
        "/government — Browse government recruitment", "/remote — Browse remote opportunities",
        "/search keywords — Search listings", "/settings — View your preferences",
        "/notifications — Check alert delivery status", "/catchup — Get recent matching listings",
        "/testalert — Test Telegram delivery", "/mode — Choose skill-matched or all alerts",
        "/pause — Pause alerts", "/resume — Resume alerts", "/sources — View connected sources"]
    if admin(u,c):
        lines += ["", "<b>Administrator commands</b>", "/addinternship — Publish a listing",
            "/adminstats — View users, deliveries and source health", "/adminjobs — List published opportunities",
            "/deletejob ID — Hide a listing", "/retryfailed — Retry failed alerts",
            "/refresh — Run an immediate source check"]
    await u.message.reply_text("\n".join(lines),parse_mode="HTML")

async def poll(ctx):
    cfg=ctx.application.bot_data
    items,health=await fetch_all(cfg["timeout"],cfg["max_items"])
    for h in health:
        with connection(cfg["db"]) as x:
            x.execute("""INSERT INTO source_health(source,last_checked_at,last_success_at,last_status,last_error,items_seen,new_items)
            VALUES(?,CURRENT_TIMESTAMP,CASE WHEN ?='OK' THEN CURRENT_TIMESTAMP ELSE NULL END,?,?,?,0)
            ON CONFLICT(source) DO UPDATE SET
            last_checked_at=CURRENT_TIMESTAMP,last_success_at=CASE WHEN excluded.last_status='OK' THEN CURRENT_TIMESTAMP ELSE source_health.last_success_at END,
            last_status=excluded.last_status,last_error=excluded.last_error,items_seen=excluded.items_seen,new_items=0""",
            (h["source"],"OK" if h["ok"] else "ERROR","OK" if h["ok"] else "ERROR",h["error"],h["count"]))
    new_count=0
    for item in items:
        with connection(cfg["db"]) as x:
            cur=x.execute("""INSERT OR IGNORE INTO opportunities(source_key,source,title,company,skills,qualification,location,stipend_text,stipend_min,deadline,url,description,opportunity_type)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item["source_key"],item["source"],item["title"],item["company"],item["skills"],item["qualification"],item["location"],item["stipend_text"],item["stipend_min"],item["deadline"],item["url"],item["description"],item["opportunity_type"]))
            job_id=x.execute("SELECT id FROM opportunities WHERE source_key=?",(item["source_key"],)).fetchone()["id"]
            is_new=cur.rowcount>0
            if is_new: x.execute("UPDATE source_health SET new_items=new_items+1 WHERE source=?",(item["source"],))
        if is_new:
            new_count+=1
            await queue_opportunity(ctx.bot,cfg["db"],job_id,cfg["max_attempts"])
    logging.info("Poll finished: fetched=%s new=%s",len(items),new_count)

async def refresh(u,c):
    if not admin(u,c):
        await u.message.reply_text("Admin-only. Ask the SuccessKart admin to run /refresh.")
        return
    await u.message.reply_text("Checking connected sources now. This can take a minute...")
    await poll(c)
    with connection(db(c)) as x:
        health=x.execute("SELECT source,last_status,items_seen,new_items,last_error FROM source_health ORDER BY source").fetchall()
    lines=["<b>Source refresh complete</b>"]
    for h in health:
        state="OK" if h["last_status"]=="OK" else "FAILED"
        line=f"{escape(h['source'])}: {state} · fetched {h['items_seen']} · new {h['new_items']}"
        if h["last_status"]!="OK" and h["last_error"]:
            line += " · " + escape(h["last_error"][:120])
        lines.append(line)
    await u.message.reply_text("\n".join(lines),parse_mode="HTML")

async def retry_worker(ctx):
    cfg=ctx.application.bot_data
    await deliver_pending(ctx.bot,cfg["db"],cfg["max_attempts"],100)

def build(cfg):
    init_db(cfg.db)
    app=Application.builder().token(cfg.token).build()
    app.bot_data.update(db=cfg.db,admins=cfg.admins,timeout=cfg.timeout,max_items=cfg.max_items,max_attempts=cfg.max_attempts,apish_api_key=cfg.apish_api_key)
    reg=ConversationHandler(entry_points=[CommandHandler("register",register)],
      states={
      RN:[MessageHandler(filters.TEXT&~filters.COMMAND,rname)],
      RQ:[CallbackQueryHandler(rqual_cb,pattern=r"^regqual:"),MessageHandler(filters.TEXT&~filters.COMMAND,rqual_text)],
      RY:[CallbackQueryHandler(ryear_cb,pattern=r"^regyear:")],
      RS:[MessageHandler(filters.TEXT&~filters.COMMAND,rskills)],
      RT:[CallbackQueryHandler(rtype_cb,pattern=r"^regtype:")],
      RL:[CallbackQueryHandler(rloc_cb,pattern=r"^regloc:")],
      RLCITY:[MessageHandler(filters.TEXT&~filters.COMMAND,rloc_city)],
      RMIN:[CallbackQueryHandler(rmin_cb,pattern=r"^regmin:")],
      RMINCUSTOM:[MessageHandler(filters.TEXT&~filters.COMMAND,rmin_custom)],
      RMODE:[CallbackQueryHandler(rmode_cb,pattern=r"^regmode:")]},
      fallbacks=[CommandHandler("cancel",cancel)],allow_reentry=True)
    add=ConversationHandler(entry_points=[CommandHandler("addinternship",addstart)],
      states={
      AT:[MessageHandler(filters.TEXT&~filters.COMMAND,at)],AC:[MessageHandler(filters.TEXT&~filters.COMMAND,ac)],
      AS:[MessageHandler(filters.TEXT&~filters.COMMAND,ass)],AQ:[MessageHandler(filters.TEXT&~filters.COMMAND,aq)],
      AL:[MessageHandler(filters.TEXT&~filters.COMMAND,al)],
      AP:[CallbackQueryHandler(ap_cb,pattern=r"^adminstip:"),MessageHandler(filters.TEXT&~filters.COMMAND,ap_text)],
      AD:[MessageHandler(filters.TEXT&~filters.COMMAND,ad)],AU:[MessageHandler(filters.TEXT&~filters.COMMAND,au)],
      AX:[MessageHandler(filters.TEXT&~filters.COMMAND,ax)],
      AK:[CallbackQueryHandler(ak_cb,pattern=r"^admintype:")]},
      fallbacks=[CommandHandler("cancel",cancel)],allow_reentry=True)
    app.add_handler(CommandHandler("start",start)); app.add_handler(reg); app.add_handler(add)
    app.add_handler(CallbackQueryHandler(mode_cb,pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(job_page,pattern=r"^jobpage:"))
    for name,fn in [("settings",settings),("mode",mode),("pause",pause),("resume",resume),("jobs",jobs),
      ("internships",internships),("government",government),("remote",remotejobs),("search",search),("sources",sources),
      ("notifications",notifications),("catchup",catchup),("testalert",testalert),
      ("adminstats",stats),("adminjobs",adminjobs),("deletejob",deletejob),("retryfailed",retryfailed),("refresh",refresh),("help",helpcmd)]:
        app.add_handler(CommandHandler(name,fn))
    async def install_default_commands(application):
        try:
            await application.bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
        except Exception as exc:
            log.warning("Could not install default user command menu: %s",exc)
    app.post_init=install_default_commands
    app.job_queue.run_repeating(poll,interval=cfg.poll_minutes*60,first=2)
    app.job_queue.run_repeating(retry_worker,interval=cfg.retry_minutes*60,first=45)
    return app
