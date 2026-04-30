import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

options = Options()
# محاولة إخفاء هوية البوت
options.add_argument("--disable-blink-features=AutomationControlled")
driver = webdriver.Chrome(options=options)

def human_typing(element, text):
    """محاكاة الكتابة البشرية: تأخير عشوائي بين كل حرف"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3)) # تأخير بين 100 و 300 ميلي ثانية
        
try:
    # 1. فتح صفحة تسجيل الدخول
    driver.get("http://localhost:8000/frontend/login_page/index.html")
    wait = WebDriverWait(driver, 15)
    print("✅ تم فتح الصفحة...")

    # 2. تعبئة البيانات (محاكاة بشرية)
    email_field = driver.find_element(By.ID, "email")
    human_typing(email_field, "test_user@example.com")
    time.sleep(0.5)
    password_field = driver.find_element(By.ID, "password")
    human_typing(password_field, "Pass123!@#")

    # 3. الانتقال داخل الـ Iframe الخاص بالكابتشا
    # بما أن الـ Widget يُرندَر داخل #arabcaptcha، فإنه ينشئ iframe تلقائياً
    print("⏳ جاري البحث عن إطار الكابتشا...")
    
    # ننتظر ظهور الـ iframe داخل div الـ arabcaptcha
    captcha_iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#arabcaptcha iframe")))
    
    # تحويل تركيز Selenium إلى داخل الـ iframe
    driver.switch_to.frame(captcha_iframe)
    print("📥 دخلنا داخل إطار الكابتشا بنجاح!")

    # 4. النقر على زر التحقق (الدائرة)
    # الآن Selenium يرى العناصر الموجودة في widget.html
    start_btn = wait.until(EC.element_to_be_clickable((By.ID, "capStartBtn")))
    
    # حركة ماوس بسيطة للتمويه
    action = webdriver.ActionChains(driver)
    action.move_to_element(start_btn).pause(0.3).click().perform()
    print("⚠️ تم النقر على زر التحقق!")

    # 5. العودة للصفحة الرئيسية لرؤية النتائج (اختياري)
    # driver.switch_to.default_content()

    # انتظر لترى هل ستظهر الصورة متموجة (كشفك كبوت) أم لا
    time.sleep(20)

except Exception as e:
    print(f"❌ فشل الاختبار. السبب: {e}")

finally:
    driver.quit()