
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
from app.db.models import Word, ReferenceWord, LowConfidenceWord

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
templates = Jinja2Templates(directory="templates")

# 4. تضمين الروترات مع البادئة الموحدة لتنظيم الـ Swagger
app.include_router(ocr.router, prefix="/api/ocr", tags=["OCR Extraction"])
app.include_router(session.router, prefix="/api", tags=["Sessions"])
app.include_router(challenge.router, prefix="/api", tags=["Challenges"])
app.include_router(solve.router, prefix="/api", tags=["Validation"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
# 5. واجهة لوحة البيانات (Dashboard) - الصفحة الرئيسية
@app.get("/", include_in_schema=False)
async def dashboard_view(request: Request, db: Session = Depends(get_db)):
    # جلب الإحصائيات الحقيقية من قاعدة البيانات [cite: 5, 11]
    stats = {
        "total": db.query(Word).count(),
        "reference": db.query(ReferenceWord).count(),
        "low_conf": db.query(LowConfidenceWord).count(),
    }
    
    # جلب آخر 10 كلمات تمت معالجتها
    recent_words = db.query(Word).order_by(Word.added_at.desc()).limit(10).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "stats": stats,
        "recent_words": recent_words
    })

# 6. معالج الأخطاء المطور لسهولة الـ Debugging
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(f"❌ ERROR: {exc}")
    return JSONResponse(
        status_code=500, 
        content={"detail": str(exc), "traceback": tb_str}
    )