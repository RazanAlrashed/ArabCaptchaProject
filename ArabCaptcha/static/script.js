const loginForm = document.getElementById("loginForm");
const emailEl = document.getElementById("email");
const passwordEl = document.getElementById("password");
const togglePwdBtn = document.getElementById("togglePwd");
const loginStatus = document.getElementById("loginStatus");

let captchaVerified = false;

// Initialize Widget inside the div #arabcaptcha
window.ArabCaptcha.render("#arabcaptcha", {
  apiKey: "demo_secret_key",
  onSuccess: function (token) {
    captchaVerified = true;
    loginStatus.textContent = "✅ تم التحقق!";
    loginStatus.style.color = "#1e7e34";

    // Auto submit if fields are filled
    if (emailEl.value && passwordEl.value) {
      setTimeout(() => {
        loginStatus.textContent = "جاري تسجيل الدخول...";
        setTimeout(() => {
          alert("تم تسجيل الدخول بنجاح! 🎉");
          loginStatus.textContent = "";
        }, 700);
      }, 500);
    }
  }
});

// ── Toggle Password ─────────────────────────────────────────────────────
togglePwdBtn.addEventListener("click", () => {
  passwordEl.type = passwordEl.type === "password" ? "text" : "password";
});

// ── Form Submit ─────────────────────────────────────────────────────────
loginForm.addEventListener("submit", (e) => {
  e.preventDefault();

  if (!emailEl.value || !passwordEl.value) {
    loginStatus.textContent = "⚠️ يرجى تعبئة البريد الإلكتروني وكلمة المرور أولاً.";
    loginStatus.style.color = "#b03a2e";
    return;
  }

  if (!captchaVerified) {
    loginStatus.textContent = "⚠️ يجب إكمال التحقق البشري أولاً للمتابعة.";
    loginStatus.style.color = "#b03a2e";
    return;
  }

  alert("تم تسجيل الدخول بنجاح! 🎉");
});
