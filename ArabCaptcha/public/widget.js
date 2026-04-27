/*
const BACKEND_BASE_URL = "http://127.0.0.1:8000/api";
const BASE_ORIGIN = "http://127.0.0.1:8000";

let sessionId = null;
let challengeId = null;
let verifiedToken = null;
let challengeStartedAt = null;

// ── Behavioral Tracking ──────────────────────────────────────────────
let behavioralData = {
  mouse_moves: 0,
  scrolls: 0,
  click_count: 0,
  paste_used: false,
  webdriver: navigator.webdriver || false,
  first_interaction_ms: null,
  focus_blur_count: 0,
  failed_attempts: 0
};

function recordFirstInteraction() {
  if (behavioralData.first_interaction_ms === null && challengeStartedAt) {
    behavioralData.first_interaction_ms = Math.round(performance.now() - challengeStartedAt);
  }
}

window.addEventListener("mousemove", () => behavioralData.mouse_moves++);
window.addEventListener("scroll", () => behavioralData.scrolls++);
window.addEventListener("blur", () => behavioralData.focus_blur_count++);
window.addEventListener("keydown", recordFirstInteraction);
window.addEventListener("click", () => {
  behavioralData.click_count++;
  recordFirstInteraction();
});

let isLockedOut = false;
let failedAttempts = 0;
let cooldownTimer = null;

const capPage1 = document.getElementById("capPage1");
const capPage2 = document.getElementById("capPage2");
const startBtn = document.getElementById("capStartBtn");

const refImage = document.getElementById("refImage");
const lowConfImage = document.getElementById("lowConfImage");

const refAnswerInput = document.getElementById("refAnswer");
const lowConfAnswerInput = document.getElementById("lowConfAnswer");

refAnswerInput.addEventListener("paste", () => behavioralData.paste_used = true);
lowConfAnswerInput.addEventListener("paste", () => behavioralData.paste_used = true);
const captchaStatus = document.getElementById("captchaStatus");

const verifyBtn = document.getElementById("verifyCaptchaBtn");
const refreshBtn = document.getElementById("refreshCaptcha");

function notifyParentHeight() {
  const height = document.documentElement.scrollHeight;
  window.parent.postMessage({ type: "ARABCAPTCHA_RESIZE", height: height }, "*");
}

function getHostDomain() {
  const params = new URLSearchParams(window.location.search);
  return params.get("domain") || "http://localhost";
}

function getApiKey() {
  const params = new URLSearchParams(window.location.search);
  return params.get("apiKey") || "demo_secret_key";
}

async function createSession() {
  const response = await fetch(`${BACKEND_BASE_URL}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: getApiKey(),
      domain: getHostDomain(),
      signals_json: JSON.stringify(behavioralData)
    })
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Session failed: ${response.status} ${errorText}`);
  }

  const data = await response.json();
  sessionId = data.session_id;
  return data;
}

async function loadChallenge(keepStatus = false) {
  if (!keepStatus) {
    captchaStatus.textContent = "جاري التحميل...";
    captchaStatus.style.color = "rgba(0,0,0,0.65)";
  }

  refAnswerInput.value = "";
  lowConfAnswerInput.value = "";
  verifiedToken = null;

  if (!isLockedOut) {
    verifyBtn.disabled = false;
    refAnswerInput.disabled = false;
    lowConfAnswerInput.disabled = false;
  }

  if (!sessionId) {
    await createSession();
  }

  const response = await fetch(`${BACKEND_BASE_URL}/challenges`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  });

  if (!response.ok) {
    throw new Error(`Challenge failed`);
  }

  const data = await response.json();
  challengeId = data.challenge_id;

  const getFullUrl = (path) => path.startsWith("http") ? path : `${BASE_ORIGIN}${path.startsWith('/') ? '' : '/'}${path}`;  refImage.src = getFullUrl(data.ref_image_url);
  lowConfImage.src = getFullUrl(data.low_conf_image_url);

  // Apply Dynamic Difficulty CSS
  if (data.difficulty === "hard") {
    refImage.style.filter = "contrast(200%) grayscale(100%) blur(1px)";
    lowConfImage.style.filter = "contrast(200%) grayscale(100%) blur(1px)";
    refImage.style.transform = "rotate(-3deg) scale(0.95)";
    lowConfImage.style.transform = "rotate(3deg) scale(0.95)";
  } else if (data.difficulty === "medium") {
    refImage.style.filter = "contrast(150%) blur(0.5px)";
    lowConfImage.style.filter = "contrast(150%) blur(0.5px)";
    refImage.style.transform = "none";
    lowConfImage.style.transform = "none";
  } else {
    refImage.style.filter = "none";
    lowConfImage.style.filter = "none";
    refImage.style.transform = "none";
    lowConfImage.style.transform = "none";
  }

  challengeStartedAt = performance.now();

  if (!keepStatus) {
    captchaStatus.textContent = "";
  }
  notifyParentHeight();
}

// ── Cooldown Timer ──────────────────────────────────────────────────────
function startCooldown() {
  const extraMinutes = failedAttempts - 2;
  const cooldownSeconds = extraMinutes * 60;
  let remaining = cooldownSeconds;

  isLockedOut = true;
  verifyBtn.disabled = true;
  refAnswerInput.disabled = true;
  lowConfAnswerInput.disabled = true;

  function updateTimer() {
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = mins > 0
      ? `${mins} دقيقة${secs > 0 ? ` و ${secs} ثانية` : ""}`
      : `${secs} ثانية`;
    captchaStatus.textContent = `⏳ حاولت كثيرًا. حاول مرة أخرى بعد ${timeStr}`;
    captchaStatus.style.color = "#b03a2e";
  }

  updateTimer();

  cooldownTimer = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
      isLockedOut = false;
      verifyBtn.disabled = false;
      refAnswerInput.disabled = false;
      lowConfAnswerInput.disabled = false;
      captchaStatus.textContent = "يمكنك المحاولة الآن.";
      captchaStatus.style.color = "rgba(0,0,0,0.65)";
      loadChallenge();
    } else {
      updateTimer();
    }
  }, 1000);
}

startBtn.addEventListener("click", async () => {
  capPage1.classList.add("hidden");
  capPage2.classList.remove("hidden");
  notifyParentHeight();
  if (!isLockedOut) {
    try {
      await loadChallenge();
    } catch (error) {
      console.error(error);
      captchaStatus.textContent = "⚠️ فشل تحميل التحدي.";
      captchaStatus.style.color = "#b03a2e";
    }
  }
});

refreshBtn.addEventListener("click", async () => {
  if (isLockedOut) return;
  try {
    await loadChallenge();
  } catch (error) {
    console.error(error);
    captchaStatus.textContent = "⚠️ فشل التحديث.";
    captchaStatus.style.color = "#b03a2e";
  }
});

verifyBtn.addEventListener("click", async () => {
  if (isLockedOut || !challengeId) return;

  const refAnswer = refAnswerInput.value.trim();
  const lowConfAnswer = lowConfAnswerInput.value.trim();

  if (!refAnswer) {
    captchaStatus.textContent = "⚠️ يرجى كتابة الكلمة المرجعية.";
    captchaStatus.style.color = "#b03a2e";
    return;
  }
  if (!lowConfAnswer) {
    captchaStatus.textContent = "⚠️ يرجى كتابة الكلمة غير الواضحة.";
    captchaStatus.style.color = "#b03a2e";
    return;
  }

  captchaStatus.textContent = "جاري التحقق...";
  captchaStatus.style.color = "rgba(0,0,0,0.65)";
  verifyBtn.disabled = true;

  const responseTimeMs = challengeStartedAt
    ? Math.round(performance.now() - challengeStartedAt)
    : null;

  try {
    behavioralData.failed_attempts = failedAttempts;

    const response = await fetch(`${BACKEND_BASE_URL}/challenges/${challengeId}/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ref_answer: refAnswer,
        low_conf_answer: lowConfAnswer,
        response_time_ms: responseTimeMs,
        signals_json: JSON.stringify(behavioralData)
      })
    });

    if (!response.ok) throw new Error("Solve failed");

    const data = await response.json();

    if (data.passed) {
      verifiedToken = data.token || "verified";
      captchaStatus.textContent = "✅ تم التحقق بنجاح!";
      captchaStatus.style.color = "#1e7e34";
      failedAttempts = 0;
      refAnswerInput.disabled = true;
      lowConfAnswerInput.disabled = true;

      window.parent.postMessage(
        { type: "ARABCAPTCHA_SUCCESS", token: verifiedToken },
        "*"
      );
    } else {
      failedAttempts++;
      if (failedAttempts >= 3) {
        captchaStatus.textContent = "❌ إجابة خاطئة.";
        captchaStatus.style.color = "#b03a2e";
        startCooldown();
      } else {
        captchaStatus.textContent = "❌ إجابة خاطئة. حاول مرة أخرى.";
        captchaStatus.style.color = "#b03a2e";
        verifyBtn.disabled = false;
        loadChallenge(true); // reload images, keep error message
      }
    }
  } catch (error) {
    console.error(error);
    failedAttempts++;
    if (failedAttempts >= 3) {
      captchaStatus.textContent = "❌ إجابة خاطئة.";
      captchaStatus.style.color = "#b03a2e";
      startCooldown();
    } else {
      captchaStatus.textContent = "❌ إجابة خاطئة. حاول مرة أخرى.";
      captchaStatus.style.color = "#b03a2e";
      verifyBtn.disabled = false;
      loadChallenge(true);
    }
  }
});

const observer = new MutationObserver(() => notifyParentHeight());
observer.observe(document.body, { childList: true, subtree: true, attributes: true });

window.addEventListener("load", notifyParentHeight);
*/
const BACKEND_BASE_URL = "http://127.0.0.1:8000/api";
const BASE_ORIGIN      = "http://127.0.0.1:8000";

let sessionId          = null;
let challengeId        = null;
let verifiedToken      = null;
let challengeStartedAt = null;
let pageLoadedAt       = Date.now();
let currentDifficulty  = "easy";

// ─────────────────────────────────────────────────────────────
// BEHAVIORAL SIGNALS
// ─────────────────────────────────────────────────────────────
let sig = {
  mouse_moves:          0,
  mouse_path_length:    0,
  mouse_speed_avg:      0,
  _mouse_speed_sum:     0,
  _mouse_speed_count:   0,

  keystroke_intervals:  [],
  key_hold_durations:   [],
  paste_used:           false,

  scroll_events:        0,
  scroll_depth_max:     0,

  first_interaction_ms: null,
  submit_time_ms:       null,
  time_on_page_ms:      null,

  focus_blur_count:     0,
  tab_hidden_count:     0,
  click_count:          0,
  touch_events:         0,

  webdriver:            navigator.webdriver || false,
  device_pixel_ratio:   window.devicePixelRatio || 1,
  screen_width:         window.screen.width,
  screen_height:        window.screen.height,
  timezone_offset:      new Date().getTimezoneOffset(),
  language:             navigator.language || "",
  platform:             navigator.platform || "",

  failed_attempts:      0,
};

// ── Collectors ────────────────────────────────────────────────
let _lastMouseX = null, _lastMouseY = null;
window.addEventListener("mousemove", (e) => {
  sig.mouse_moves++;
  if (_lastMouseX !== null) {
    const dx   = e.clientX - _lastMouseX;
    const dy   = e.clientY - _lastMouseY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    sig.mouse_path_length  += dist;
    sig._mouse_speed_sum   += dist;
    sig._mouse_speed_count += 1;
  }
  _lastMouseX = e.clientX;
  _lastMouseY = e.clientY;
});

let _lastKeyTime  = null;
let _keyDownTimes = {};
window.addEventListener("keydown", (e) => {
  _keyDownTimes[e.key] = Date.now();
  if (_lastKeyTime !== null) sig.keystroke_intervals.push(Date.now() - _lastKeyTime);
  _lastKeyTime = Date.now();
  _recordFirstInteraction();
});
window.addEventListener("keyup", (e) => {
  if (_keyDownTimes[e.key] !== undefined) {
    sig.key_hold_durations.push(Date.now() - _keyDownTimes[e.key]);
    delete _keyDownTimes[e.key];
  }
});
window.addEventListener("scroll", () => {
  sig.scroll_events++;
  const pageH = document.body.scrollHeight - window.innerHeight;
  if (pageH > 0) {
    const pct = Math.round((window.scrollY / pageH) * 100);
    if (pct > sig.scroll_depth_max) sig.scroll_depth_max = pct;
  }
});
window.addEventListener("blur",       () => sig.focus_blur_count++);
window.addEventListener("click",      () => { sig.click_count++; _recordFirstInteraction(); });
window.addEventListener("touchstart", () => sig.touch_events++);
document.addEventListener("visibilitychange", () => { if (document.hidden) sig.tab_hidden_count++; });

function _recordFirstInteraction() {
  if (sig.first_interaction_ms === null) sig.first_interaction_ms = Date.now() - pageLoadedAt;
}

function _finalizeSignals() {
  sig.time_on_page_ms = Date.now() - pageLoadedAt;
  if (sig._mouse_speed_count > 0) sig.mouse_speed_avg = sig._mouse_speed_sum / sig._mouse_speed_count;
  if (sig.keystroke_intervals.length > 50) sig.keystroke_intervals = sig.keystroke_intervals.slice(-50);
  if (sig.key_hold_durations.length  > 50) sig.key_hold_durations  = sig.key_hold_durations.slice(-50);
}

function _exportSignals() {
  const out = { ...sig };
  delete out._mouse_speed_sum;
  delete out._mouse_speed_count;
  return out;
}

// ─────────────────────────────────────────────────────────────
// DOM REFS
// ─────────────────────────────────────────────────────────────
let isLockedOut    = false;
let failedAttempts = 0;
let cooldownTimer  = null;

const capPage1           = document.getElementById("capPage1");
const capPage2           = document.getElementById("capPage2");
const startBtn           = document.getElementById("capStartBtn");
const compositeImage     = document.getElementById("compositeImage");   // NEW single image
const refAnswerInput     = document.getElementById("refAnswer");
const lowConfAnswerInput = document.getElementById("lowConfAnswer");
const captchaStatus      = document.getElementById("captchaStatus");
const verifyBtn          = document.getElementById("verifyCaptchaBtn");
const refreshBtn         = document.getElementById("refreshCaptcha");

refAnswerInput.addEventListener("paste",     () => sig.paste_used = true);
lowConfAnswerInput.addEventListener("paste", () => sig.paste_used = true);

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
function notifyParentHeight() {
  window.parent.postMessage(
    { type: "ARABCAPTCHA_RESIZE", height: document.documentElement.scrollHeight },
    "*"
  );
}

function getHostDomain() {
  return new URLSearchParams(window.location.search).get("domain") || "http://localhost";
}
function getApiKey() {
  return new URLSearchParams(window.location.search).get("apiKey") || "demo_secret_key";
}

function fullUrl(path) {
  if (!path) return "";
  return path.startsWith("http") ? path : `${BASE_ORIGIN}${path.startsWith("/") ? "" : "/"}${path}`;
}

/**
 * Apply a CSS filter to the composite image based on difficulty.
 * The actual heavy distortions are baked into the PNG by the server;
 * these CSS tweaks are a lightweight extra layer that bots can't strip
 * because they're applied after image decode in the browser.
 */
function _applyDifficultyStyle(difficulty) {
  if (!compositeImage) return;
  switch (difficulty) {
    case "hard":
      compositeImage.style.filter    = "contrast(115%) brightness(0.95)";
      compositeImage.style.transform = "perspective(600px) rotateX(2deg)";
      break;
    case "medium":
      compositeImage.style.filter    = "contrast(108%)";
      compositeImage.style.transform = "none";
      break;
    default:
      compositeImage.style.filter    = "none";
      compositeImage.style.transform = "none";
  }
}

// ─────────────────────────────────────────────────────────────
// SESSION
// ─────────────────────────────────────────────────────────────
async function createSession() {
  _finalizeSignals();
  const response = await fetch(`${BACKEND_BASE_URL}/sessions`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key:      getApiKey(),
      domain:       getHostDomain(),
      signals_json: JSON.stringify(_exportSignals()),
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Session failed: ${response.status} ${text}`);
  }
  const data = await response.json();
  sessionId = data.session_id;
  return data;
}

// ─────────────────────────────────────────────────────────────
// CHALLENGE
// ─────────────────────────────────────────────────────────────
async function loadChallenge(keepStatus = false) {
  if (!keepStatus) {
    captchaStatus.textContent = "جاري التحميل...";
    captchaStatus.style.color = "rgba(0,0,0,0.65)";
  }

  refAnswerInput.value     = "";
  lowConfAnswerInput.value = "";
  verifiedToken = null;

  if (!isLockedOut) {
    verifyBtn.disabled          = false;
    refAnswerInput.disabled     = false;
    lowConfAnswerInput.disabled = false;
  }

  const response = await fetch(`${BACKEND_BASE_URL}/challenges`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!response.ok) throw new Error("Challenge request failed");

  const data    = await response.json();
  challengeId   = data.challenge_id;
  currentDifficulty = data.difficulty || "easy";

  // ── Show the stitched composite image ──────────────────────
  // composite_image_url is the server-distorted PNG with both words joined.
  // Fall back to ref_image_url if composite isn't available yet.
  const imgUrl = data.composite_image_url || data.ref_image_url;
  if (compositeImage) {
    compositeImage.src = fullUrl(imgUrl);
    _applyDifficultyStyle(currentDifficulty);
  }

  challengeStartedAt = performance.now();
  if (!keepStatus) captchaStatus.textContent = "";
  notifyParentHeight();
}

// ─────────────────────────────────────────────────────────────
// ESCALATION — reload challenge at harder difficulty
// Called when server returns needs_upgrade: true
// ─────────────────────────────────────────────────────────────
async function upgradeChallenge(newCompositeUrl, newDifficulty) {
  currentDifficulty = newDifficulty;

  captchaStatus.textContent = "🔒 جاري تحديث مستوى التحقق...";
  captchaStatus.style.color = "#b47b00";

  if (newCompositeUrl && compositeImage) {
    // Bust cache so the browser fetches the new harder image
    compositeImage.src = fullUrl(newCompositeUrl) + "?t=" + Date.now();
    _applyDifficultyStyle(newDifficulty);
  }

  refAnswerInput.value     = "";
  lowConfAnswerInput.value = "";
  verifyBtn.disabled       = false;
  refAnswerInput.disabled  = false;
  lowConfAnswerInput.disabled = false;

  challengeStartedAt = performance.now();

  setTimeout(() => {
    captchaStatus.textContent = "⚠️ يرجى إعادة المحاولة.";
    captchaStatus.style.color = "#b47b00";
  }, 800);

  notifyParentHeight();
}

// ─────────────────────────────────────────────────────────────
// COOLDOWN
// ─────────────────────────────────────────────────────────────
function startCooldown() {
  const cooldownSeconds = Math.max(30, (failedAttempts - 2) * 60);
  let remaining = cooldownSeconds;

  isLockedOut             = true;
  verifyBtn.disabled      = true;
  refAnswerInput.disabled = true;
  lowConfAnswerInput.disabled = true;

  const updateTimer = () => {
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    const t = m > 0 ? `${m} دقيقة${s > 0 ? ` و ${s} ثانية` : ""}` : `${s} ثانية`;
    captchaStatus.textContent = `⏳ حاولت كثيرًا. حاول مرة أخرى بعد ${t}`;
    captchaStatus.style.color = "#b03a2e";
  };

  updateTimer();
  cooldownTimer = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer  = null;
      isLockedOut    = false;
      failedAttempts = 0;
      verifyBtn.disabled          = false;
      refAnswerInput.disabled     = false;
      lowConfAnswerInput.disabled = false;
      captchaStatus.textContent   = "يمكنك المحاولة الآن.";
      captchaStatus.style.color   = "rgba(0,0,0,0.65)";
      loadChallenge();
    } else {
      updateTimer();
    }
  }, 1000);
}

// ─────────────────────────────────────────────────────────────
// EVENT HANDLERS
// ─────────────────────────────────────────────────────────────
startBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  e.stopPropagation();

  capPage1.classList.add("hidden");
  capPage2.classList.remove("hidden");
  notifyParentHeight();

  if (isLockedOut) return;

  try {
    const sessionData = await createSession();

    // Trusted user — skip challenge entirely (reCAPTCHA v3 style)
    if (!sessionData.needs_challenge) {
      verifiedToken = `trusted_${sessionId}`;
      captchaStatus.textContent = "✅ تم التحقق تلقائيًا!";
      captchaStatus.style.color = "#1e7e34";
      capPage2.classList.add("hidden");
      capPage1.classList.remove("hidden");
      notifyParentHeight();
      window.parent.postMessage({ type: "ARABCAPTCHA_SUCCESS", token: verifiedToken }, "*");
      return;
    }

    await loadChallenge();
  } catch (err) {
    console.error("❌ Start error:", err);
    capPage2.classList.add("hidden");
    capPage1.classList.remove("hidden");
    notifyParentHeight();
  }
});

refreshBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  e.stopPropagation();
  if (isLockedOut) return;
  try {
    await loadChallenge();
  } catch (err) {
    captchaStatus.textContent = "⚠️ فشل التحديث.";
    captchaStatus.style.color = "#b03a2e";
  }
});

verifyBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  e.stopPropagation();
  if (isLockedOut || !challengeId) return;

  const refAnswer     = refAnswerInput.value.trim();
  const lowConfAnswer = lowConfAnswerInput.value.trim();

  if (!refAnswer) {
    captchaStatus.textContent = "⚠️ يرجى كتابة الكلمة الأولى.";
    captchaStatus.style.color = "#b03a2e";
    return;
  }
  if (!lowConfAnswer) {
    captchaStatus.textContent = "⚠️ يرجى كتابة الكلمة الثانية.";
    captchaStatus.style.color = "#b03a2e";
    return;
  }

  captchaStatus.textContent = "جاري التحقق...";
  captchaStatus.style.color = "rgba(0,0,0,0.65)";
  verifyBtn.disabled = true;

  const responseTimeMs   = challengeStartedAt ? Math.round(performance.now() - challengeStartedAt) : null;
  sig.submit_time_ms     = responseTimeMs;
  sig.failed_attempts    = failedAttempts;

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/challenges/${challengeId}/solve`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ref_answer:       refAnswer,
        low_conf_answer:  lowConfAnswer,
        response_time_ms: responseTimeMs,
        signals_json:     JSON.stringify(_exportSignals()),
      }),
    });

    if (!response.ok) throw new Error("Solve request failed");
    const data = await response.json();

    // ── Escalation: server detected bot behaviour mid-challenge ────────
    if (data.needs_upgrade) {
      await upgradeChallenge(data.new_composite_url, data.new_difficulty);
      return;
    }

    // ── Passed ────────────────────────────────────────────────────────
    if (data.passed) {
      verifiedToken = data.token || "verified";
      captchaStatus.textContent = "✅ تم التحقق بنجاح!";
      captchaStatus.style.color = "#1e7e34";
      failedAttempts = 0;
      refAnswerInput.disabled     = true;
      lowConfAnswerInput.disabled = true;
      window.parent.postMessage({ type: "ARABCAPTCHA_SUCCESS", token: verifiedToken }, "*");
    } else {
      // ── Wrong answer ─────────────────────────────────────────────────
      failedAttempts++;
      if (failedAttempts >= 3) {
        captchaStatus.textContent = "❌ إجابة خاطئة.";
        captchaStatus.style.color = "#b03a2e";
        startCooldown();
      } else {
        captchaStatus.textContent = `❌ إجابة خاطئة. تبقى ${Math.max(0, 3 - failedAttempts)} محاولة.`;
        captchaStatus.style.color = "#b03a2e";
        verifyBtn.disabled = false;
        await loadChallenge(true);
      }
    }
  } catch (err) {
    console.error("❌ Verify error:", err);
    failedAttempts++;
    if (failedAttempts >= 3) {
      startCooldown();
    } else {
      captchaStatus.textContent = "❌ خطأ في الاتصال. حاول مرة أخرى.";
      captchaStatus.style.color = "#b03a2e";
      verifyBtn.disabled = false;
    }
  }
});

// ─────────────────────────────────────────────────────────────
// HEIGHT OBSERVER
// ─────────────────────────────────────────────────────────────
const observer = new MutationObserver(notifyParentHeight);
observer.observe(document.body, { childList: true, subtree: true, attributes: true });
window.addEventListener("load", notifyParentHeight);