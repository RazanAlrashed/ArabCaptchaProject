
import os
import traceback
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# استيراد المكونات من المجلد الداخلي app
from app.db.session import engine, Base, get_db
from app.routers import session, challenge, solve, ocr, admin
from app.db.models import Word, ReferenceWord, LowConfidenceWord ,Challenge
from sqlalchemy import func

if os.environ.get("ARABCAPTCHA_SECRET", "change-me-in-production") == "change-me-in-production":
    print("⚠️  WARNING: ARABCAPTCHA_SECRET env var not set. Set it before going to production.")
# 1. إنشاء جداول قاعدة البيانات (إذا لم تكن موجودة)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ArabCaptcha Dashboard API",
    version="1.0.0",
)

# 2. إعدادات CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
os.makedirs("assets/captcha", exist_ok=True)
# 3. إعداد الملفات الساكنة والقوالب (Templates)
# تأكدي من وجود مجلدات assets و templates في المجلد الرئيسي
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/public", StaticFiles(directory="public"), name="public")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.mount("/static", StaticFiles(directory="static"), name="static")
#app.mount("/templates", StaticFiles(directory="templates"), name="templates")

templates = Jinja2Templates(directory="templates")

# 4. تضمين الروترات مع البادئة الموحدة لتنظيم الـ Swagger
app.include_router(ocr.router, prefix="/api/ocr", tags=["OCR Extraction"])
app.include_router(session.router, prefix="/api", tags=["Sessions"])
app.include_router(challenge.router, prefix="/api", tags=["Challenges"])
app.include_router(solve.router, prefix="/api", tags=["Validation"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
# 5. واجهة لوحة البيانات (Dashboard) - الصفحة الرئيسية
# ابحث عن المسار الرئيسي وقم بتعديله كالتالي:
# ابحث عن المسار الرئيسي السابق وقم بتغييره بالكامل إلى هذا:

@app.get("/", include_in_schema=False)
async def admin_portal(request: Request):
    # هذه هي الصفحة التي ستفتح فور تشغيل السيرفر
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/dashboard", include_in_schema=False)
async def dashboard_page(request: Request, db: Session = Depends(get_db)):
    # جلب البيانات المطلوبة للداشبورد
    stats = {
        "total": db.query(Word).count(),
        "reference": db.query(ReferenceWord).count(),
        "low_conf": db.query(LowConfidenceWord).count(),
    }
    recent_words = db.query(Word).order_by(Word.added_at.desc()).limit(10).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "stats": stats,
        "recent_words": recent_words
    })

# 1. مسار صفحة التحديات (Challenges Page)
@app.get("/challenges", include_in_schema=False)
async def challenges_page(request: Request, db: Session = Depends(get_db)):
    # جلب إحصائيات مفيدة وشاملة
    stats = {
        "total_attempts": db.query(Challenge).count(),
        "passed": db.query(Challenge).filter(Challenge.status == 'passed').count(),
        "failed": db.query(Challenge).filter(Challenge.status == 'failed').count(),
        # متوسط درجة البوت (كلما زادت زاد الاشتباه بالنشاط الآلي)
        "avg_bot_score": db.query(func.avg(Challenge.bot_score)).scalar() or 0
    }
    return templates.TemplateResponse("challenges.html", {
        "request": request,
        "stats": stats
    })

# 2. API لجلب البيانات للجدول بشكل حي
@app.get("/admin/recent-challenges")
async def get_recent_challenges(db: Session = Depends(get_db)):
    # جلب آخر 50 محاولة من الداتابيس
    challenges = db.query(Challenge).order_by(Challenge.created_at.desc()).limit(50).all()
    # تحويل البيانات لتنسيق JSON متوافق مع الفرونت إند
    return [
        {
            "session_id": c.session_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "difficulty": c.difficulty,
            "status": c.status,
            "bot_score": c.bot_score or 0
        } for c in challenges
    ]
@app.get("/live-demo", include_in_schema=False)
async def live_demo_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/bot-simulation", include_in_schema=False)
async def bot_sim_page(request: Request):
    return templates.TemplateResponse("bot_demo.html", {"request": request})

# 6. معالج الأخطاء المطور لسهولة الـ Debugging
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(f"❌ ERROR: {exc}")
    return JSONResponse(
        status_code=500, 
        content={"detail": str(exc), "traceback": tb_str}
    )