
/* =========================================================
   VERITY AI — Main JavaScript
   Flask routes: POST /chat and POST /analyze
   Supports Groq chat + SerpApi product cards.
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

function $(id) {
    return document.getElementById(id);
}

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

function safeHttpUrl(value) {
    if (!value || typeof value !== "string") return "";

    try {
        var parsed = new URL(value, window.location.origin);

        if (
            parsed.protocol === "https:" ||
            parsed.protocol === "http:"
        ) {
            return parsed.href;
        }
    } catch (_) {
        // Invalid URL.
    }

    return "";
}

function firstDefined() {
    for (var i = 0; i < arguments.length; i++) {
        var value = arguments[i];

        if (
            value !== undefined &&
            value !== null &&
            value !== ""
        ) {
            return value;
        }
    }

    return undefined;
}

/* ----------------------------- DOM ready -------------------------------- */

document.addEventListener("DOMContentLoaded", function () {
    setupSanitizer();
    setupInput();
    setupClicks();
    setupDashboardResponsiveBehavior();
    updateCharacterCounter();
});

/* ----------------------------- Sanitizer -------------------------------- */

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
            if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.isComposing
            ) {
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

/* ----------------------------- Click actions ---------------------------- */

function setupClicks() {
    document.addEventListener("click", function (event) {
        var target = event.target;

        if (
            !target ||
            typeof target.closest !== "function"
        ) {
            return;
        }

        var promptEl = target.closest("[data-prompt]");

        if (promptEl) {
            setInputValue(promptEl.getAttribute("data-prompt"));
            return;
        }

        var actionEl = target.closest("[data-action]");

        if (!actionEl) return;

        switch (actionEl.getAttribute("data-action")) {
            case "new-chat":
                window.location.reload();
                break;

            case "scroll-chat":
                var chat = $("chat");

                if (chat) {
                    chat.scrollIntoView({ behavior: "smooth" });
                }
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

    if (refinedBtn) {
        refinedBtn.addEventListener("click", useRefinedPrompt);
    }
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
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(
                Object.assign(
                    {
                        message: isChecked("piiToggle", true)
                            ? maskPIIForAnalysis(text)
                            : text
                    },
                    getToggles()
                )
            )
        });

        if (!response.ok) {
            throw new Error(
                "Prompt refinement failed: " + response.status
            );
        }

        var data = await response.json();

        if (requestId !== refinementRequestId) return;

        var refined = firstDefined(
            data.refined_prompt,
            data.refinedPrompt,
            data.refined
        );

        refinedBox.textContent =
            typeof refined === "string" && refined.trim()
                ? refined
                : "No refinement suggestion available.";

        updateDashboard(data, { skipRefined: true });

    } catch (error) {
        if (requestId !== refinementRequestId) return;

        refinedBox.textContent =
            "Prompt refinement is temporarily unavailable.";

        console.error("Prompt refinement error:", error);
    }
}

function useRefinedPrompt() {
    var refinedBox = $("refinedPrompt");

    if (!refinedBox) return;

    var refined = refinedBox.textContent.trim();

    if (
        !refined ||
        REFINE_STATES.indexOf(refined) !== -1
    ) {
        return;
    }

    setInputValue(refined);
}

/* ----------------------------- PII masking ------------------------------ */

function maskPIIForAnalysis(text) {
    if (!text) return "";

    var masked = String(text);

    // Email addresses.
    masked = masked.replace(
        /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
        "[EMAIL REDACTED]"
    );

    // Indian PAN.
    masked = masked.replace(
        /\b[A-Z]{5}[0-9]{4}[A-Z]\b/gi,
        "[PAN REDACTED]"
    );

    // Credit/debit card numbers: mask only if Luhn-valid.
    masked = masked.replace(
        /(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)/g,
        function (candidate) {
            return isLuhnValid(candidate.replace(/\D/g, ""))
                ? "[CARD NUMBER REDACTED]"
                : candidate;
        }
    );

    // Aadhaar-like 12-digit numbers.
    masked = masked.replace(
        /(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)/g,
        "[ID NUMBER REDACTED]"
    );

    // Indian mobile numbers.
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

    var safeMessage = isChecked("piiToggle", true)
        ? maskPIIForAnalysis(message)
        : message;

    addMessage(safeMessage, "user");

    input.value = "";
    autoResize(input);
    updateCharacterCounter();

    var refinedBox = $("refinedPrompt");

    if (refinedBox) {
        refinedBox.textContent = EMPTY_REFINED;
    }

    setText("activityStatus", "Processing…");
    showTypingIndicator();

    try {
        var response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(
                Object.assign(
                    {
                        message: message,
                        chat_id: chatId
                    },
                    getToggles()
                )
            )
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
                data.error ||
                data.message ||
                "Request failed with status " + response.status
            );
        }

        updateLastUserMessage(
            data.safe_message ||
            data.redacted_message ||
            safeMessage
        );

        var answer = firstDefined(
            data.response,
            data.answer,
            data.reply,
            data.assistant_message,
            data.message
        );

        if (
            typeof answer !== "string" ||
            !answer.trim()
        ) {
            answer = "I couldn't generate a response. Please try again.";
        }

        addMessage(answer, "bot");

        updateDashboard(data);

        // Accept either { items: [...] } or a direct product array.
        var productData = data.products || data.results || [];

        var productItems = Array.isArray(productData)
            ? productData
            : (
                productData &&
                Array.isArray(productData.items)
                    ? productData.items
                    : []
            );

        renderProducts(productItems);

        if (
            productItems.length === 0 &&
            productData &&
            productData.note
        ) {
            console.info("Product search:", productData.note);
        }

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

    var initial = document.querySelector(
        "#chat .initial-message"
    );

    if (initial) initial.remove();
}

/* ----------------------------- Chat rendering --------------------------- */

function addMessage(message, role) {
    var chat = $("chat");

    if (!chat) return null;

    if (role === "assistant") role = "bot";

    var wrapper = document.createElement("div");
    wrapper.className = "message " + role;

    var bubble = document.createElement("div");
    bubble.className = "message-bubble";

    var text = String(message == null ? "" : message);

    if (
        role === "bot" &&
        window.marked &&
        window.DOMPurify
    ) {
        try {
            bubble.innerHTML = DOMPurify.sanitize(
                marked.parse(text)
            );
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

    var bubble = userMessages[userMessages.length - 1]
        .querySelector(".message-bubble");

    if (bubble) {
        bubble.textContent = String(message || "");
    }
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

    if (!section || !container) {
        console.warn(
            "Product display elements missing: expected #productsSection and #products."
        );
        return;
    }

    container.replaceChildren();

    if (!Array.isArray(products) || products.length === 0) {
        section.hidden = true;
        return;
    }

    products.forEach(function (product) {
        if (!product || typeof product !== "object") return;

        var title = String(
            product.title ||
            product.name ||
            product.product_name ||
            "Product"
        );

        var imageUrl = safeHttpUrl(
            product.image ||
            product.image_url ||
            product.thumbnail ||
            product.thumbnail_url ||
            ""
        );

        var productUrl = safeHttpUrl(
            product.link ||
            product.url ||
            product.product_url ||
            product.product_link ||
            ""
        );

        var price = firstDefined(
            product.price_text,
            product.price,
            product.displayed_price,
            product.cost
        );

        var source = firstDefined(
            product.source,
            product.merchant,
            product.seller,
            ""
        );

        var description = firstDefined(
            product.description,
            product.summary,
            ""
        );

        var card = document.createElement("article");
        card.className = "product-card";

        // Product photo.
        if (imageUrl) {
            var imageContainer = document.createElement("div");
            imageContainer.className = "product-image-container";

            var image = document.createElement("img");
            image.className = "product-image";
            image.src = imageUrl;
            image.alt = title;
            image.loading = "lazy";
            image.referrerPolicy = "no-referrer";

            image.addEventListener("error", function () {
                imageContainer.remove();
            });

            imageContainer.appendChild(image);
            card.appendChild(imageContainer);
        }

        var details = document.createElement("div");
        details.className = "product-details";

        var heading = document.createElement("h3");
        heading.className = "product-title";
        heading.textContent = title;
        details.appendChild(heading);

        // Price.
        if (
            price !== undefined &&
            price !== null &&
            String(price).trim()
        ) {
            var priceEl = document.createElement("p");
            priceEl.className = "product-price";

            var priceText = String(price).trim();

            if (/^\d[\d,.]*$/.test(priceText)) {
                priceText = CURRENCY + priceText;
            }

            priceEl.textContent = priceText;
            details.appendChild(priceEl);
        }

        // Seller.
        if (source) {
            var sourceEl = document.createElement("p");
            sourceEl.className = "product-source";
            sourceEl.textContent = "Seller: " + String(source);
            details.appendChild(sourceEl);
        }

        // Description.
        if (description) {
            var descEl = document.createElement("p");
            descEl.className = "product-description";
            descEl.textContent = String(description);
            details.appendChild(descEl);
        }

        // Listing link.
        if (productUrl) {
            var link = document.createElement("a");

            link.className = "product-link";
            link.href = productUrl;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "View product";

            details.appendChild(link);
        } else {
            var unavailable = document.createElement("p");

            unavailable.className = "product-unavailable";
            unavailable.textContent = "Product link unavailable";

            details.appendChild(unavailable);
        }

        card.appendChild(details);
        container.appendChild(card);
    });

    section.hidden = container.children.length === 0;
}

/* ----------------------------- Dashboard updates ------------------------ */

function updateDashboard(data, options) {
    if (!data || typeof data !== "object") return;

    options = options || {};

    // Context/memory status.
    setTextIfPresent(
        "memory",
        firstDefined(
            data.memory,
            data.memory_status,
            data.context,
            data.context_status
        )
    );

    // Token count.
    var tokenValue = firstNumeric(
        data.total_tokens,
        data.token_count,
        data.usage && data.usage.total_tokens
    );

    var tokenPercent = firstNumeric(
        data.token_percent,
        data.tokenPercent,
        data.token_percentage,
        data.usage && data.usage.percent
    );

    // pipeline.py returns tokens as an object.
    if (data.tokens && typeof data.tokens === "object") {
        var pipelineTokenValue = firstNumeric(
            data.tokens.total,
            data.tokens.total_tokens,
            data.tokens.used
        );

        if (pipelineTokenValue !== null) {
            tokenValue = pipelineTokenValue;
        }

        var pipelinePercent = firstNumeric(
            data.tokens.usage_percent,
            data.tokens.percent
        );

        if (pipelinePercent !== null) {
            tokenPercent = pipelinePercent;
        }
    } else if (tokenValue === null) {
        tokenValue = firstNumeric(data.tokens);
    }

    if (tokenPercent === null && tokenValue !== null) {
        tokenPercent = (tokenValue / MAX_TOKENS) * 100;
    }

    if (tokenValue !== null) {
        setText(
            "tokens",
            formatNumber(tokenValue) +
            " / " +
            formatNumber(MAX_TOKENS)
        );

        setText(
            "activityTokens",
            formatNumber(tokenValue) + " tokens used"
        );
    }

    if (tokenPercent !== null) {
        tokenPercent = Math.max(
            0,
            Math.min(100, tokenPercent)
        );

        setText("tokenPercent", Math.round(tokenPercent) + "%");

        var circle = $("tokenCircle");

        if (circle) {
            circle.style.setProperty(
                "--usage",
                tokenPercent + "%"
            );
        }

        var bar = $("tokenProgress");

        if (bar) {
            bar.style.width = tokenPercent + "%";
        }
    }

    // Estimated session cost.
    var costValue = firstNumeric(
        data.token_cost,
        data.cost,
        data.estimated_cost,
        data.usage && data.usage.cost
    );

    if (data.tokens && typeof data.tokens === "object") {
        var pipelineCost = firstNumeric(data.tokens.cost_inr);

        if (pipelineCost !== null) {
            costValue = pipelineCost;
        }
    }

    if (costValue !== null) {
        setText("tokenCost", CURRENCY + costValue.toFixed(6));
    }

    // PII status.
    var piiValue = firstDefined(
        data.pii,
        data.pii_redacted,
        data.redactions,
        data.pii_count,
        data.pii_found
    );

    if (piiValue !== undefined) {
        var piiText;

        if (typeof piiValue === "boolean") {
            piiText = piiValue ? "Protected" : "None detected";
        } else if (Array.isArray(piiValue)) {
            piiText = piiValue.length
                ? piiValue.length + " item(s) detected"
                : "None detected";
        } else if (typeof piiValue === "object") {
            piiText = JSON.stringify(piiValue);
        } else {
            piiText = String(piiValue);
        }

        setText("pii", piiText);
        setText("activityPii", piiText);
    }

    // Warnings.
    var warningValue = firstDefined(
        data.warn,
        data.warning,
        data.warnings,
        data.waste_warnings
    );

    if (warningValue !== undefined) {
        setText(
            "warn",
            Array.isArray(warningValue)
                ? warningValue.join(", ")
                : (
                    typeof warningValue === "object"
                        ? JSON.stringify(warningValue)
                        : String(warningValue)
                )
        );
    }

    // Context Lock status and filter changes.
    updateContextLockDashboard(data);

    // Prompt refinement.
    if (!options.skipRefined) {
        var refinedValue = firstDefined(
            data.refined_prompt,
            data.refinedPrompt,
            data.refined
        );

        if (
            typeof refinedValue === "string" &&
            refinedValue.trim()
        ) {
            setText("refinedPrompt", refinedValue);
        }
    }

    // Reflect feature switches instead of leaving stale dashboard values.
    var features = data.features || {};
    if (features.token_manager === false) {
        setText("tokens", "Disabled");
        setText("activityTokens", "Token tracking disabled");
        setText("tokenPercent", "—");
        setText("tokenCost", "—");
        var tokenCircle = $("tokenCircle");
        if (tokenCircle) tokenCircle.style.setProperty("--usage", "0%");
        var tokenProgress = $("tokenProgress");
        if (tokenProgress) tokenProgress.style.width = "0%";
    }
    if (features.pii_protection === false) {
        setText("pii", "Protection disabled");
        setText("activityPii", "Protection disabled");
    }
    if (features.context_lock === false) {
        setText("memory", "Context Lock disabled");
    }
}

/* ----------------------------- Context Lock dashboard ------------------- */

function formatFilterChange(change) {
    if (!change || typeof change !== "object") {
        return String(change);
    }

    var field = String(change.field || "filter");
    var newValue = change.new;

    if (newValue === null || newValue === undefined) {
        return field + " removed";
    }

    return field + " → " + String(newValue);
}

function updateContextLockDashboard(data) {
    // Shopping status comes from the backend pipeline.
    if (typeof data.shopping_active === "boolean") {
        setText(
            "memory",
            data.shopping_active
                ? "Shopping Context Active"
                : "General Chat"
        );
    }

    var filterValue = firstDefined(
        data.filter_changes,
        data.filterChanges,
        data.contextlock_changes,
        data.filters_applied
    );

    var changes = Array.isArray(filterValue)
        ? filterValue
        : [];

    if (filterValue !== undefined) {
        var filterText = "";

        if (Array.isArray(filterValue)) {
            filterText = filterValue
                .map(formatFilterChange)
                .join(", ");
        } else if (
            typeof filterValue === "object" &&
            filterValue !== null
        ) {
            filterText = JSON.stringify(filterValue);
        } else {
            filterText = String(filterValue);
        }

        setText(
            "filterChanges",
            filterText || "No filter changes"
        );
    }

    // Show "Live Filter Applied" only when the backend reports
    // that a shopping request actually changed one or more filters.
    if (
        data.shopping_active === true &&
        changes.length > 0
    ) {
        setText(
            "filterChanges",
            "Live Filter Applied: " +
            changes.map(formatFilterChange).join(", ")
        );
    } else if (
        data.shopping_active === true &&
        changes.length === 0
    ) {
        setText("filterChanges", "No filter changes");
    } else if (data.shopping_active === false) {
        setText("filterChanges", "Not applied to this message");
    }
}

/* ----------------------------- DOM helpers ------------------------------ */

function setText(id, value) {
    var el = $(id);

    if (el) {
        el.textContent = String(value);
    }
}

function setTextIfPresent(id, value) {
    if (value === undefined || value === null) return;

    setText(
        id,
        typeof value === "object"
            ? JSON.stringify(value)
            : value
    );
}

function firstNumeric() {
    for (var i = 0; i < arguments.length; i++) {
        var value = arguments[i];

        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            continue;
        }

        var number = Number(value);

        if (Number.isFinite(number)) {
            return number;
        }
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

    if (overlay) {
        overlay.addEventListener("click", closeDashboard);
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeDashboard();
        }
    });

    window.addEventListener("resize", function () {
        if (window.matchMedia("(min-width: 1251px)").matches) {
            closeDashboard();
        }
    });
}

function openDashboard() {
    var dashboard = $("dashboard");
    var overlay = $("dashboardOverlay");

    if (dashboard) {
        dashboard.classList.add("open");
    }

    if (overlay) {
        overlay.classList.add("active");
    }
}

function closeDashboard() {
    var dashboard = $("dashboard");
    var overlay = $("dashboardOverlay");

    if (dashboard) {
        dashboard.classList.remove("open");
    }

    if (overlay) {
        overlay.classList.remove("active");
    }
}

function toggleDashboard() {
    var dashboard = $("dashboard");

    if (!dashboard) return;

    if (dashboard.classList.contains("open")) {
        closeDashboard();
    } else {
        openDashboard();
    }
}

/* ----------------------------- Character counter ------------------------ */

function updateCharacterCounter() {
    var input = $("msg");
    var counter = $("composerCounter");

    if (!input || !counter) return;

    var length = input.value.length;

    counter.textContent = length
        ? length.toLocaleString("en-IN") + " characters"
        : "Ready";
}
