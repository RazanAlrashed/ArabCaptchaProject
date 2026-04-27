window.ArabCaptcha = {
  render: function (selector, options = {}) {
    const container = document.querySelector(selector);

    if (!container) {
      console.error("ArabCaptcha container not found");
      return;
    }

    const params = new URLSearchParams({
      domain: "http://localhost",
      apiKey: options.apiKey || "demo_secret_key"
    });

    const iframe = document.createElement("iframe");
    iframe.src = `http://127.0.0.1:8000/public/widget.html?${params.toString()}`;
    iframe.width = "100%";
    iframe.height = "56";
    iframe.style.border = "0";
    iframe.style.borderRadius = "12px";
    iframe.style.background = "transparent";
    iframe.style.transition = "height 0.25s ease-out";
    iframe.setAttribute("title", "ArabCaptcha");

    container.innerHTML = "";
    container.appendChild(iframe);

    window.addEventListener("message", function (event) {
      const data = event.data;

      if (data.type === "ARABCAPTCHA_SUCCESS") {
        if (typeof options.onSuccess === "function") {
          options.onSuccess(data.token);
        }
      }

      if (data.type === "ARABCAPTCHA_RESIZE") {
        iframe.style.height = data.height + "px";
      }
    });
  }
};