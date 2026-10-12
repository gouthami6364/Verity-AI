/* =========================================================
   VERITY AI — Main JavaScript (corrected)
   Flask routes: POST /chat and POST /analyze
   ========================================================= */

"use strict";

/* ----------------------------- Global state ----------------------------- */

var chatId = (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : Math.random().toString(36).substring(2);

var refinementTimer = null;
var refinementRequestId = 0;
var isSending = false;

var MAX_TOKENS = 131072;
var CURRENCY = "₹";
var EMPTY_REFINED = "Start typing a prompt...";
var REFINE_STATES = [
    EMPTY_REFINED,
    "REFINING...",
    "No refinement suggestion available.",
    "Prompt refinement is temporarily unavailable."
];

/* ----------------------------- Helpers ---------------------------------- */

function $(id) { return document.getElementById(id); }

function isChecked(id, fallback) {
    var el = $(id);
    return el ? el.checked : fallback;
}

function getToggles() {
    return {
        pii_protection: isChecked("piiToggle", true),
        context_lock: isChecked("contextToggle", true),
        token_manager: isChecked("tokenToggle", true)
    };
}

/* ----------------------------- DOM ready -------------------------------- */

document.addEventListener("DOMContentLoaded", function () {
    setupSanitizer();
    setupInput();
    setupClicks();
    setupDashboardResponsiveBehavior();
    updateCharacterCounter();
});

/* Make links in rendered markdown safe */
function setupSanitizer() {
    if (!window.DOMPurify) return;
    DOMPurify.addHook("afterSanitizeAttributes", function (node) {
        if (node.tagName === "A") {
            node.setAttribute("target", "_blank");
            node.setAttribute("rel", "noopener noreferrer");
        }
    });
}

/* ----------------------------- Input setup ------------------------------ */

function setupInput() {
    var input = $("msg");
    var form = $("chatForm");

    if (form) {
        // Single send path: form submit (covers button click too).
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            sendMessage();
        });
    }

    if (input) {
        input.addEventListener("input", function () {
            autoResize(input);
            updateCharacterCounter();
            schedulePromptRefinement();
        });

        input.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                sendMessage();
            }
        });
    }
}

function autoResize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 130) + "px";
}

/* One delegated click handler for all data-action / data-prompt buttons */
function setupClicks() {
    document.addEventListener("click", function (event) {
        var promptEl = event.target.closest("[data-prompt]");
        if (promptEl) {
            setInputValue(promptEl.getAttribute("data-prompt"));
            return;
        }

        var actionEl = event.target.closest("[data-action]");
        if (!actionEl) return;

        switch (actionEl.getAttribute("data-action")) {
            case "new-chat":
                window.location.reload();
                break;
            case "scroll-chat":
                var chat = $("chat");
                if (chat) chat.scrollIntoView({ behavior: "smooth" });
                break;
            case "focus-input":
                if ($("msg")) $("msg").focus();
                break;
            case "toggle-dashboard":
                toggleDashboard();
                break;
            case "close-dashboard":
                closeDashboard();
                break;
        }
    });

    var refinedBtn = $("useRefinedPrompt");
    if (refinedBtn) refinedBtn.addEventListener("click", useRefinedPrompt);
}

function setInputValue(text) {
    var input = $("msg");
    if (!input) return;
    input.value = text || "";
    autoResize(input);
    input.focus();
    updateCharacterCounter();
    schedulePromptRefinement();
}

/* ----------------------------- Prompt refinement ------------------------ */

function schedulePromptRefinement() {
    clearTimeout(refinementTimer);
    refinementTimer = setTimeout(refinePrompt, 800);
}

async function refinePrompt() {
    var input = $("msg");
    var refinedBox = $("refinedPrompt");
    if (!input || !refinedBox) return;

    var text = input.value.trim();

    if (!text) {
        refinementRequestId++;
        refinedBox.textContent = EMPTY_REFINED;
        return;
    }

    var requestId = ++refinementRequestId;
    refinedBox.textContent = "REFINING...";

    try {
        var response = await fetch("/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.assign(
                { message: maskPIIForAnalysis(text) },
                getToggles()
            ))
        });

        if (!response.ok) throw new Error("Prompt refinement failed: " + response.status);

        var data = await response.json();
        if (requestId !== refinementRequestId) return; // stale

        // Don't fall back to data.message / data.prompt — those aren't refinements.
        var refined = data.refined_prompt || data.refinedPrompt || data.refined;

        refinedBox.textContent =
            typeof refined === "string" && refined.trim()
                ? refined
                : "No refinement suggestion available.";

        // Update everything except the refined box (already set above).
        updateDashboard(data, { skipRefined: true });
    } catch (error) {
        if (requestId !== refinementRequestId) return;
        refinedBox.textContent = "Prompt refinement is temporarily unavailable.";
        console.error("Prompt refinement error:", error);
    }
}

function useRefinedPrompt() {
    var refinedBox = $("refinedPrompt");
    if (!refinedBox) return;

    var refined = refinedBox.textContent.trim();
    if (!refined || REFINE_STATES.indexOf(refined) !== -1) return;

    setInputValue(refined);
}

/* ----------------------------- PII masking ------------------------------ */

function maskPIIForAnalysis(text) {
    if (!text) return "";
    var masked = String(text);

    // Email
    masked = masked.replace(
        /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
        "[EMAIL REDACTED]"
    );

    // Indian PAN
    masked = masked.replace(/\b[A-Z]{5}[0-9]{4}[A-Z]\b/gi, "[PAN REDACTED]");

    // Cards FIRST (Luhn-valid only) so phone/Aadhaar rules can't chew into them.
    masked = masked.replace(
        /(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)/g,
        function (candidate) {
            return isLuhnValid(candidate.replace(/\D/g, ""))
                ? "[CARD NUMBER REDACTED]"
                : candidate;
        }
    );

    // Aadhaar-like 12 digits (first digit 2-9), exact boundaries.
    masked = masked.replace(
        /(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)/g,
        "[ID NUMBER REDACTED]"
    );

    // Indian mobile numbers, exact boundaries (won't match inside longer numbers).
    masked = masked.replace(
        /(?<![\d+])(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)/g,
        "[PHONE REDACTED]"
    );

    return masked;
}

function isLuhnValid(number) {
    if (!/^\d{13,19}$/.test(number)) return false;

    var sum = 0;
    var doubleDigit = false;

    for (var i = number.length - 1; i >= 0; i--) {
        var digit = parseInt(number.charAt(i), 10);
        if (doubleDigit) {
            digit *= 2;
            if (digit > 9) digit -= 9;
        }
        sum += digit;
        doubleDigit = !doubleDigit;
    }
    return sum % 10 === 0;
}

/* ----------------------------- Send chat message ------------------------ */

async function sendMessage() {
    var input = $("msg");
    var sendButton = $("sendBtn");

    if (!input || isSending) return;

    var message = input.value.trim();
    if (!message) return;

    isSending = true;
    if (sendButton) {
        sendButton.disabled = true;
        sendButton.classList.add("loading");
    }

    clearTimeout(refinementTimer);
    refinementRequestId++;

    hideWelcome();

    var safeMessage = maskPIIForAnalysis(message);
    addMessage(safeMessage, "user");

    input.value = "";
    autoResize(input);
    updateCharacterCounter();

    var refinedBox = $("refinedPrompt");
    if (refinedBox) refinedBox.textContent = EMPTY_REFINED;

    setText("activityStatus", "Processing…");
    showTypingIndicator();

    try {
        var response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.assign(
                { message: message, chat_id: chatId },
                getToggles()
            ))
        });

        var data;
        try {
            data = await response.json();
        } catch (_) {
            throw new Error("The server returned an invalid response.");
        }

        removeTypingIndicator();

        if (!response.ok) {
            throw new Error(
                data.error || data.message || "Request failed with status " + response.status
            );
        }

        updateLastUserMessage(data.safe_message || data.redacted_message || safeMessage);

        var answer =
            data.response || data.answer || data.reply || data.assistant_message || data.message;

        if (typeof answer !== "string" || !answer.trim()) {
            answer = "I couldn't generate a response. Please try again.";
        }

        addMessage(answer, "bot");

        updateDashboard(data);
        renderProducts(data.products || data.results || []);
        setText("activityStatus", "Ready");

    } catch (error) {
        removeTypingIndicator();
        addMessage(
            "Sorry, I couldn't complete that request. Please check your connection and try again.",
            "bot"
        );
        setText("activityStatus", "Last request failed");
        console.error("Chat error:", error);
    } finally {
        isSending = false;
        if (sendButton) {
            sendButton.disabled = false;
            sendButton.classList.remove("loading");
        }
        input.focus();
    }
}

function hideWelcome() {
    var panel = $("welcomePanel");
    if (panel) panel.hidden = true;

    var initial = document.querySelector("#chat .initial-message");
    if (initial) initial.remove();
}

/* ----------------------------- Chat rendering --------------------------- */
/* NOTE: CSS targets ".message.user" and ".message.bot" with ".message-bubble". */

function addMessage(message, role) {
    var chat = $("chat");
    if (!chat) return null;

    if (role === "assistant") role = "bot"; // backwards-compat

    var wrapper = document.createElement("div");
    wrapper.className = "message " + role;

    var bubble = document.createElement("div");
    bubble.className = "message-bubble";

    var text = String(message == null ? "" : message);

    if (role === "bot" && window.marked && window.DOMPurify) {
        try {
            bubble.innerHTML = DOMPurify.sanitize(marked.parse(text));
        } catch (error) {
            bubble.textContent = text;
        }
    } else {
        bubble.textContent = text;
    }

    wrapper.appendChild(bubble);
    chat.appendChild(wrapper);
    chat.scrollTop = chat.scrollHeight;

    return wrapper;
}

function updateLastUserMessage(message) {
    var chat = $("chat");
    if (!chat) return;

    var userMessages = chat.querySelectorAll(".message.user");
    if (!userMessages.length) return;

    var bubble = userMessages[userMessages.length - 1].querySelector(".message-bubble");
    if (bubble) bubble.textContent = String(message || "");
}

/* ----------------------------- Typing indicator ------------------------- */

function showTypingIndicator() {
    removeTypingIndicator();

    var chat = $("chat");
    if (!chat) return;

    var indicator = document.createElement("div");
    indicator.id = "typingIndicator";
    indicator.className = "message bot typing-indicator";

    var bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = "Verity AI is thinking…";

    indicator.appendChild(bubble);
    chat.appendChild(indicator);
    chat.scrollTop = chat.scrollHeight;
}

function removeTypingIndicator() {
    var indicator = $("typingIndicator");
    if (indicator) indicator.remove();
}

/* ----------------------------- Product rendering ------------------------ */

function renderProducts(products) {
    var section = $("productsSection");
    var container = $("products");
    if (!section || !container) return;

    container.replaceChildren();

    if (!Array.isArray(products) || products.length === 0) {
        section.hidden = true;
        return;
    }

    products.forEach(function (product) {
        if (!product || typeof product !== "object") return;

        var card = document.createElement("article");
        card.className = "product-card";

        var title = String(product.title || product.name || product.product_name || "Product");
        var price = String(product.price || product.displayed_price || product.cost || "");
        var description = String(product.description || product.summary || "");
        var imageUrl = safeHttpUrl(product.image || product.image_url || product.thumbnail || "");
        var productUrl = safeHttpUrl(product.url || product.link || product.product_url || "");

        if (imageUrl) {
            var imageContainer = document.createElement("div");
            imageContainer.className = "product-image-container";

            var image = document.createElement("img");
            image.src = imageUrl;
            image.alt = title;
            image.loading = "lazy";
            image.referrerPolicy = "no-referrer";
            image.addEventListener("error", function () { imageContainer.remove(); });

            imageContainer.appendChild(image);
            card.appendChild(imageContainer);
        }

        var details = document.createElement("div");
        details.className = "product-details";

        var heading = document.createElement("h3");
        heading.className = "product-title";
        heading.textContent = title;
        details.appendChild(heading);

        if (price) {
            var priceEl = document.createElement("p");
            priceEl.className = "product-price";
            priceEl.textContent = price;
            details.appendChild(priceEl);
        }

        if (description) {
            var descEl = document.createElement("p");
            descEl.className = "product-description";
            descEl.textContent = description;
            details.appendChild(descEl);
        }

        if (productUrl) {
            var link = document.createElement("a");
            link.className = "product-link";
            link.href = productUrl;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "View product";
            details.appendChild(link);
        }

        card.appendChild(details);
        container.appendChild(card);
    });

    section.hidden = container.children.length === 0;
}

function safeHttpUrl(value) {
    if (!value || typeof value !== "string") return "";
    try {
        var parsed = new URL(value, window.location.origin);
        return (parsed.protocol === "https:" || parsed.protocol === "http:") ? parsed.href : "";
    } catch (_) {
        return "";
    }
}

/* ----------------------------- Dashboard updates ------------------------ */

function updateDashboard(data, options) {
    if (!data || typeof data !== "object") return;
    options = options || {};

    setTextIfPresent("memory", firstDefined(
        data.memory, data.memory_status, data.context, data.context_status
    ));

    /* Tokens */
    var tokenValue = firstNumeric(
        data.tokens, data.total_tokens, data.token_count,
        data.usage && data.usage.total_tokens
    );

    var tokenPercent = firstNumeric(
        data.token_percent, data.tokenPercent, data.token_percentage,
        data.usage && data.usage.percent
    );

    if (tokenPercent === null && tokenValue !== null) {
        tokenPercent = (tokenValue / MAX_TOKENS) * 100;
    }

    if (tokenValue !== null) {
        setText("tokens", formatNumber(tokenValue) + " / " + formatNumber(MAX_TOKENS));
        setText("activityTokens", formatNumber(tokenValue) + " tokens used");
    }

    if (tokenPercent !== null) {
        tokenPercent = Math.max(0, Math.min(100, tokenPercent));
        setText("tokenPercent", Math.round(tokenPercent) + "%");

        var circle = $("tokenCircle");
        // CSS conic-gradient reads --usage; don't overwrite background inline.
        if (circle) circle.style.setProperty("--usage", tokenPercent + "%");

        var bar = $("tokenProgress");
        if (bar) bar.style.width = tokenPercent + "%";
    }

    var costValue = firstNumeric(
        data.token_cost, data.cost, data.estimated_cost,
        data.usage && data.usage.cost
    );
    if (costValue !== null) {
        setText("tokenCost", CURRENCY + costValue.toFixed(6));
    }

    /* PII */
    var piiValue = firstDefined(data.pii, data.pii_redacted, data.redactions, data.pii_count);
    if (piiValue !== undefined) {
        var piiText = typeof piiValue === "boolean"
            ? (piiValue ? "Protected" : "None detected")
            : (typeof piiValue === "object" ? JSON.stringify(piiValue) : String(piiValue));
        setText("pii", piiText);
        setText("activityPii", piiText);
    }

    /* Warnings */
    var warningValue = firstDefined(data.warn, data.warning, data.warnings);
    if (warningValue !== undefined) {
        setText("warn", Array.isArray(warningValue) ? warningValue.join(", ") : String(warningValue));
    }

    /* Filter changes */
    var filterValue = firstDefined(
        data.filter_changes, data.filterChanges, data.contextlock_changes, data.filters_applied
    );
    if (filterValue !== undefined) {
        setText("filterChanges", Array.isArray(filterValue) ? filterValue.join(", ") : String(filterValue));
    }

    /* Refined prompt */
    if (!options.skipRefined) {
        var refinedValue = firstDefined(data.refined_prompt, data.refinedPrompt, data.refined);
        if (typeof refinedValue === "string" && refinedValue.trim()) {
            setText("refinedPrompt", refinedValue);
        }
    }
}

function setText(id, value) {
    var el = $(id);
    if (el) el.textContent = String(value);
}

function setTextIfPresent(id, value) {
    if (value === undefined || value === null) return;
    setText(id, typeof value === "object" ? JSON.stringify(value) : value);
}

function firstDefined() {
    for (var i = 0; i < arguments.length; i++) {
        var v = arguments[i];
        if (v !== undefined && v !== null && v !== "") return v;
    }
    return undefined;
}

function firstNumeric() {
    for (var i = 0; i < arguments.length; i++) {
        var v = arguments[i];
        if (v === null || v === undefined || v === "") continue;
        var n = Number(v);
        if (Number.isFinite(n)) return n;
    }
    return null;
}

function formatNumber(number) {
    var value = Number(number);
    if (!Number.isFinite(value)) return "0";
    return Math.round(value).toLocaleString("en-IN");
}

/* ----------------------------- Dashboard drawer ------------------------- */

function setupDashboardResponsiveBehavior() {
    var overlay = $("dashboardOverlay");
    if (overlay) overlay.addEventListener("click", closeDashboard);

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeDashboard();
    });

    window.addEventListener("resize", function () {
        if (window.matchMedia("(min-width: 1251px)").matches) closeDashboard();
    });
}

function openDashboard() {
    var dashboard = $("dashboard");
    var overlay = $("dashboardOverlay");
    if (dashboard) dashboard.classList.add("open");
    if (overlay) overlay.classList.add("active");
}

function closeDashboard() {
    var dashboard = $("dashboard");
    var overlay = $("dashboardOverlay");
    if (dashboard) dashboard.classList.remove("open");
    if (overlay) overlay.classList.remove("active");
}

function toggleDashboard() {
    var dashboard = $("dashboard");
    if (!dashboard) return;
    if (dashboard.classList.contains("open")) closeDashboard();
    else openDashboard();
}

/* ----------------------------- Character counter ------------------------ */

function updateCharacterCounter() {
    var input = $("msg");
    var counter = $("composerCounter");
    if (!input || !counter) return;

    var length = input.value.length;
    counter.textContent = length ? length.toLocaleString("en-IN") + " characters" : "Ready";
}