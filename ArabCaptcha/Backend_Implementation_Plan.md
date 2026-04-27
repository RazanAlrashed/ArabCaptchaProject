# ArabCaptcha — Backend Implementation Plan
## خطة تنفيذ الباك-اند

---

## 1. نظرة عامة (Overview)

**ArabCaptcha** هو نظام كابتشا عربي يجمع بين التحقق من هوية المستخدم (هل هو إنسان أم بوت؟) مع رقمنة النصوص العربية عبر التعهيد الجماعي (Crowdsourcing).

### الفكرة الأساسية:
- يُعرض للمستخدم **كلمتان** في كل تحدي:
  - **كلمة مرجعية (Reference Word)**: نصها الصحيح معروف مسبقاً → تُستخدم للتحقق من الإنسان
  - **كلمة غير واضحة (Low Confidence Word)**: نصها غير معروف → تُجمع إجابات المستخدمين لتحديد نصها

### التقنيات المستخدمة:
| المكون | التقنية |
|--------|---------|
| الإطار (Framework) | FastAPI (Python) |
| قاعدة البيانات | SQLite (تطوير) / MySQL (إنتاج) |
| ORM | SQLAlchemy |
| التحقق من البيانات | Pydantic |
| الإعدادات | pydantic-settings + ملف `.env` |

---

## 2. هيكل المشروع (Project Structure)

```
ArabCaptcha/
├── app/
│   ├── __init__.py
│   ├── main.py                    # نقطة الدخول + CORS + Static Files
│   ├── core/
│   │   └── config.py              # جميع الإعدادات القابلة للتعديل
│   ├── db/
│   │   ├── session.py             # إعداد اتصال قاعدة البيانات
│   │   └── models.py              # جداول ORM (10 جداول)
│   ├── schemas/
│   │   ├── session.py             # نماذج Pydantic للجلسات
│   │   ├── challenge.py           # نماذج Pydantic للتحديات
│   │   ├── attempt.py             # نماذج Pydantic للمحاولات
│   │   └── word.py                # نماذج Pydantic للكلمات
│   ├── routers/
│   │   ├── session.py             # POST /sessions
│   │   ├── challenge.py           # POST /challenges, GET /challenges/{id}
│   │   ├── solve.py               # POST /challenges/{id}/solve
│   │   ├── ocr.py                 # POST /ocr/upload
│   │   └── admin.py               # GET /words, GET /consensus
│   ├── services/
│   │   ├── session_service.py     # منطق إنشاء الجلسات
│   │   ├── challenge_service.py   # منطق إنشاء التحديات
│   │   ├── solve_service.py       # منطق التحقق من الإجابات
│   │   └── consensus_service.py   # منطق التعهيد الجماعي
│   └── utils/
│       ├── hashing.py             # تشفير مفتاح API
│       ├── bot_scorer.py          # حساب نقاط البوت
│       └── text_normalizer.py     # تطبيع النص العربي
├── assets/words/                  # صور الكلمات
├── seed.py                        # بيانات تجريبية
├── requirements.txt               # المكتبات المطلوبة
└── arabcaptcha.db                 # قاعدة البيانات (SQLite)
```

---

## 3. قاعدة البيانات — مخطط ER (Database Schema)

### 3.1 جداول العملاء (Client Tables)

#### `client_site` — المواقع المسجلة
| العمود | النوع | الوصف |
|--------|-------|-------|
| site_id | Integer (PK) | معرّف الموقع |
| site_name | String(255) | اسم الموقع |
| api_key_hash | String(64) | مفتاح API مشفّر (SHA-256) |
| status | String(20) | الحالة: active / inactive |

#### `client_domain` — النطاقات المسموحة
| العمود | النوع | الوصف |
|--------|-------|-------|
| domain_id | Integer (PK) | معرّف النطاق |
| site_id | Integer (FK) | مرتبط بـ client_site |
| domain_url | String(255) | رابط النطاق المسموح |

### 3.2 جداول الجلسات (Session Tables)

#### `site_session` — جلسات المستخدمين
| العمود | النوع | الوصف |
|--------|-------|-------|
| session_id | UUID (PK) | معرّف فريد للجلسة |
| site_id | Integer (FK) | مرتبط بـ client_site |
| bot_score_initial | Float | نقاط البوت الأولية |
| bot_score_final | Float | نقاط البوت النهائية |
| risk_level | String(10) | مستوى الخطر: low / med / high |
| status | String(20) | الحالة: active / expired |

#### `behavior_log` — سجل السلوك
| العمود | النوع | الوصف |
|--------|-------|-------|
| log_id | Integer (PK) | معرّف السجل |
| session_id | UUID (FK) | مرتبط بـ site_session |
| event_type | String(100) | نوع الحدث |
| signals_json | Text | بيانات السلوك (JSON) |

### 3.3 جداول الكلمات (Word Tables)

#### `word` — جدول أساسي لكل صورة كلمة
| العمود | النوع | الوصف |
|--------|-------|-------|
| word_id | Integer (PK) | معرّف الكلمة |
| image_path | String(500) | مسار صورة الكلمة |
| word_type | String(20) | النوع: reference / low_confidence |

#### `reference_word` — كلمات مرجعية (نصها معروف)
| العمود | النوع | الوصف |
|--------|-------|-------|
| word_id | Integer (PK, FK) | مرتبط بـ word |
| correct_text | String(255) | النص الصحيح |
| source | String(50) | المصدر: manual / ocr |
| active | Boolean | مفعّلة أم لا |

#### `low_confidence_word` — كلمات غير واضحة (نصها مجهول)
| العمود | النوع | الوصف |
|--------|-------|-------|
| word_id | Integer (PK, FK) | مرتبط بـ word |
| initial_confidence | Float | مستوى الثقة الأولي (0-1) |
| status | String(20) | pending / verified / unreadable |
| verified_text | String(255) | النص بعد التحقق |
| total_votes | Integer | عدد الأصوات الكلي |

### 3.4 جداول التحديات (Challenge Tables)

#### `challenge` — التحدي المعروض للمستخدم
| العمود | النوع | الوصف |
|--------|-------|-------|
| challenge_id | UUID (PK) | معرّف فريد |
| session_id | UUID (FK) | مرتبط بـ site_session |
| ref_word_id | Integer (FK) | الكلمة المرجعية |
| low_conf_word_id | Integer (FK) | الكلمة غير الواضحة |
| difficulty | String(10) | easy / medium / hard |
| max_attempts | Integer | أقصى عدد محاولات |
| expires_at | DateTime | وقت الانتهاء |
| status | String(20) | pending / passed / failed / expired |

#### `attempt` — محاولة حل
| العمود | النوع | الوصف |
|--------|-------|-------|
| attempt_id | Integer (PK) | معرّف المحاولة |
| challenge_id | UUID (FK) | مرتبط بـ challenge |
| attempt_number | Integer | رقم المحاولة |
| reference_input_text | String(255) | إجابة الكلمة المرجعية |
| low_conf_input_text | String(255) | إجابة الكلمة غير الواضحة |
| passed | Boolean | هل نجحت؟ |
| response_time_ms | Float | زمن الاستجابة |

### 3.5 جداول التعهيد الجماعي (Crowdsourcing Tables)

#### `low_confidence_submission` — إجابات موثوقة فقط
| العمود | النوع | الوصف |
|--------|-------|-------|
| submission_id | Integer (PK) | معرّف الإرسال |
| low_conf_word_id | Integer (FK) | الكلمة غير الواضحة |
| attempt_id | Integer (FK) | المحاولة الأصلية |
| submitted_text | String(255) | النص المُدخل |
| normalized_text | String(255) | النص بعد التطبيع |

#### `low_confidence_consensus` — ملخص الإجماع
| العمود | النوع | الوصف |
|--------|-------|-------|
| consensus_id | Integer (PK) | معرّف الإجماع |
| low_conf_word_id | Integer (FK) | الكلمة غير الواضحة |
| top_candidate_text | String(255) | النص الأكثر تصويتاً |
| votes | Integer | عدد الأصوات للنص الأعلى |
| total | Integer | إجمالي الأصوات |
| ratio | Float | نسبة الاتفاق |
| is_verified | Boolean | هل تم التحقق؟ |

---

## 4. واجهات API (API Endpoints)

### 4.1 إنشاء جلسة — `POST /sessions`

**الغرض**: إنشاء جلسة جديدة للمستخدم مع حساب نقاط البوت الأولية.

**المدخلات (Request Body)**:
```json
{
  "api_key": "demo_secret_key",
  "domain": "http://localhost",
  "signals_json": "{}"
}
```

**المخرجات (Response)**:
```json
{
  "session_id": "uuid-string",
  "risk_level": "low",
  "bot_score": 0.0
}
```

**المنطق الداخلي**:
1. تشفير مفتاح API بـ SHA-256 والبحث عنه في `client_site`
2. التحقق من أن النطاق مسجل في `client_domain`
3. حساب `bot_score` من الإشارات السلوكية
4. تحديد مستوى الخطر (low / med / high)
5. إنشاء سجل `site_session`

---

### 4.2 إنشاء تحدي — `POST /challenges`

**الغرض**: إنشاء تحدي كابتشا جديد.

**المدخلات**:
```json
{
  "session_id": "uuid-string"
}
```

**المخرجات**:
```json
{
  "challenge_id": "uuid-string",
  "ref_image_url": "assets/words/word1.jpg",
  "low_conf_image_url": "assets/words/word2.jpg",
  "difficulty": "easy",
  "expires_at": "2026-04-01T09:00:00",
  "max_attempts": 3
}
```

**المنطق الداخلي**:
1. التحقق من أن الجلسة فعّالة
2. اختيار كلمة مرجعية عشوائية (active = True)
3. اختيار كلمة غير واضحة عشوائية (status = pending)
4. تحديد مستوى الصعوبة بناءً على `bot_score`
5. تعيين وقت انتهاء (3 دقائق افتراضياً)

---

### 4.3 تقديم إجابة — `POST /challenges/{challenge_id}/solve`

**الغرض**: التحقق من إجابة المستخدم.

**المدخلات**:
```json
{
  "ref_answer": "الحجاز",
  "low_conf_answer": "بارسانها",
  "response_time_ms": 1500,
  "signals_json": "{}"
}
```

**المخرجات**:
```json
{
  "passed": true,
  "attempts_left": 2,
  "token": "uuid-verification-token"
}
```

**المنطق الداخلي (Trust Gate)**:
1. التحقق من صلاحية التحدي (موجود، لم ينتهِ، لم يُحل)
2. فحص عدد المحاولات السابقة
3. **بوابة الثقة (Trust Gate)**: مقارنة الإجابة المرجعية مع النص الصحيح
4. إذا صحيحة → تخزين إجابة الكلمة غير الواضحة في `low_confidence_submission`
5. تحديث الإجماع (Consensus) للكلمة غير الواضحة
6. إرجاع توكن التحقق

---

## 5. الخوارزميات الأساسية (Core Algorithms)

### 5.1 حساب نقاط البوت (Bot Score)

**الملف**: `app/utils/bot_scorer.py`

يحلل الإشارات السلوكية ويعطي نقاط (0-100):

| الإشارة | النقاط | الشرط |
|---------|--------|-------|
| إرسال سريع جداً | +35 | أقل من 800ms |
| لصق الإجابة | +25 | paste_used = true |
| بدون حركة فأرة | +15 | mouse_moves = 0 و scroll = 0 |
| أتمتة (Webdriver) | +40 | navigator.webdriver = true |
| تفاعل أول سريع | +15 | أقل من 150ms |
| تبديل تبويبات كثير | +10 | أكثر من 3 مرات |
| محاولات فاشلة كثيرة | +15 | 3 أو أكثر |

**تحديد مستوى الخطر**:
- `bot_score < 30` → **low** (سهل)
- `30 ≤ bot_score < 70` → **med** (متوسط)
- `bot_score ≥ 70` → **high** (صعب)

### 5.2 خوارزمية الإجماع (Consensus Algorithm)

**الملف**: `app/services/consensus_service.py`

بعد كل إجابة موثوقة:
1. جمع كل الإجابات المطبّعة (normalized) للكلمة غير الواضحة
2. حساب النص الأكثر تكراراً ونسبة الاتفاق
3. إذا `عدد الأصوات ≥ 10` **و** `نسبة الاتفاق ≥ 70%`:
   - تأكيد الكلمة → `status = verified`
4. إذا `المحاولات ≥ 50` بدون إجماع:
   - إهمال الكلمة → `status = unreadable`

### 5.3 تطبيع النص العربي (Arabic Text Normalization)

**الملف**: `app/utils/text_normalizer.py`

- إزالة التشكيل (الحركات)
- توحيد الألف (أ، إ، آ → ا)
- توحيد الهاء والتاء المربوطة
- إزالة المسافات الزائدة

---

## 6. الإعدادات القابلة للتعديل (Configuration)

**الملف**: `app/core/config.py`

| الإعداد | القيمة الافتراضية | الوصف |
|---------|-------------------|-------|
| LOW_RISK_THRESHOLD | 30 | حد الخطر المنخفض |
| HIGH_RISK_THRESHOLD | 70 | حد الخطر العالي |
| MIN_VOTES_REQUIRED_FOR_CONSENSUS | 10 | الحد الأدنى للأصوات |
| CONSENSUS_AGREEMENT_RATIO | 0.70 | نسبة الاتفاق المطلوبة (70%) |
| MAX_ATTEMPTS_BEFORE_DISCARD | 50 | حد الإهمال |
| CHALLENGE_EXPIRY_MINUTES | 3 | مدة صلاحية التحدي |
| MAX_CHALLENGE_ATTEMPTS | 3 | أقصى محاولات لكل تحدي |

---

## 7. مراحل التنفيذ (Implementation Phases)

### المرحلة 1: الأساسيات ✅
- [x] إعداد بيئة Python + FastAPI
- [x] تصميم مخطط قاعدة البيانات (ER Diagram)
- [x] إنشاء نماذج ORM (Models)
- [x] إعداد الاتصال بقاعدة البيانات

### المرحلة 2: الـ API Layer ✅
- [x] إنشاء Pydantic Schemas
- [x] بناء Routers (session, challenge, solve, ocr, admin)
- [x] بناء Services (business logic)

### المرحلة 3: الخوارزميات ✅
- [x] خوارزمية Bot Score
- [x] خوارزمية Consensus
- [x] أداة تطبيع النص العربي
- [x] أداة تشفير مفتاح API

### المرحلة 4: ربط الواجهة ✅
- [x] تفعيل CORS
- [x] تقديم الصور كـ Static Files
- [x] ربط الواجهة الأمامية مع الـ API
- [x] إضافة نافذة الكابتشا المنبثقة (Modal)

### المرحلة 5: التحسينات ✅
- [x] Seed data للتطوير والاختبار
- [x] معالجة الأخطاء (Error Handling)
- [x] رسائل باللغة العربية
- [x] تايمر الحماية من المحاولات الكثيرة

---

## 8. كيفية تشغيل المشروع (How to Run)

```bash
# 1. استنساخ المشروع
git clone https://github.com/RaghadFayez/ArabCaptcha.git
cd ArabCaptcha

# 2. إنشاء بيئة افتراضية
python3 -m venv .venv
source .venv/bin/activate

# 3. تثبيت المكتبات
pip install -r requirements.txt

# 4. تهيئة قاعدة البيانات بالبيانات التجريبية
python seed.py

# 5. تشغيل السيرفر
uvicorn app.main:app --reload

# 6. فتح واجهة API التفاعلية
# http://127.0.0.1:8000/docs

# 7. فتح الواجهة الأمامية
# open frontend/login\ page/index.html
```

---

## 9. مخطط تدفق البيانات (Data Flow)

```
المستخدم يفتح صفحة تسجيل الدخول
         │
         ▼
    يعبّئ البريد وكلمة المرور
         │
         ▼
    يضغط "Sign in"
         │
         ▼
  ┌──────────────────────┐
  │  POST /sessions      │ ← إنشاء جلسة + حساب bot_score
  └──────┬───────────────┘
         ▼
  ┌──────────────────────┐
  │  POST /challenges    │ ← اختيار كلمتين عشوائياً
  └──────┬───────────────┘
         ▼
    تُعرض صورتا الكلمتين للمستخدم
         │
         ▼
    المستخدم يكتب الكلمتين ويضغط "تحقق"
         │
         ▼
  ┌──────────────────────────────┐
  │  POST /challenges/{id}/solve │
  │                              │
  │  1. Trust Gate:              │
  │     هل الكلمة المرجعية صح؟   │
  │     ├─ نعم → حفظ إجابة      │
  │     │  الكلمة غير الواضحة    │
  │     │  + تحديث الإجماع       │
  │     │  + إرجاع token ✅      │
  │     └─ لا → رفض ❌           │
  └──────────────────────────────┘
```
