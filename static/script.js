/* =========================================================
   VERITY AI — Main JavaScript
   Compatible with Flask routes:
   POST /chat and POST /analyze
   ========================================================= */

"use strict";

/* ----------------------------- Global state ----------------------------- */

var chatId = Math.random().toString(36).substring(2);
var refinementTimer = null;
var refinementRequestId = 0;
var isSending = false;
var EMPTY_REFINED = "Start typing a prompt...";

/* ----------------------------- DOM ready -------------------------------- */

document.addEventListener("DOMContentLoaded", function () {
    setupInput();
    setupExamplePrompts();
    setupCharacterCounter();
    setupDashboardResponsiveBehavior();
});

/* ----------------------------- Input setup ------------------------------ */

function setupInput() {
    var input = document.getElementById("msg");
    var sendButton = document.getElementById("sendBtn");

    if (input) {
        input.addEventListener("input", function () {
            schedulePromptRefinement();
            updateCharacterCounter();
        });

        input.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        });
    }

    if (sendButton) {
        sendButton.addEventListener("click", sendMessage);
    }
}

/* ----------------------------- Prompt refinement ------------------------ */

function schedulePromptRefinement() {
    clearTimeout(refinementTimer);

    refinementTimer = setTimeout(function () {
        refinePrompt();
    }, 800);
}

async function refinePrompt() {
    var input = document.getElementById("msg");
    var refinedBox = document.getElementById("refinedPrompt");

    if (!input || !refinedBox) return;

    var text = input.value.trim();

    if (!text) {
        refinementRequestId++;
        refinedBox.innerText = EMPTY_REFINED;
        return;
    }

    // Mask obvious personal information before sending to /analyze.
    var safeForAnalysis = maskPIIForAnalysis(text);
    var requestId = ++refinementRequestId;

    refinedBox.innerText = "REFINING...";

    try {
        var response = await fetch("/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: safeForAnalysis
            })
        });

        if (!response.ok) {
            throw new Error("Prompt refinement failed: " + response.status);
        }

        var data = await response.json();

        // Ignore stale responses from earlier prompts.
        if (requestId !== refinementRequestId) return;

        var refined =
            data.refined_prompt ||
            data.refinedPrompt ||
            data.refined ||
            data.prompt ||
            data.message;

        refinedBox.innerText =
            typeof refined === "string" && refined.trim()
                ? refined
                : "No refinement suggestion available.";

        updateDashboard(data);
    } catch (error) {
        if (requestId !== refinementRequestId) return;

        refinedBox.innerText = "Prompt refinement is temporarily unavailable.";
        console.error("Prompt refinement error:", error);
    }
}

/* ----------------------------- Use refined prompt ----------------------- */

function setupRefinedPromptButton() {
    var button = document.getElementById("useRefinedPrompt");
    if (!button) return;

    button.addEventListener("click", function () {
        var input = document.getElementById("msg");
        var refinedBox = document.getElementById("refinedPrompt");

        if (!input || !refinedBox) return;

        var refined = refinedBox.innerText.trim();

        if (
            refined &&
            refined !== EMPTY_REFINED &&
            refined !== "REFINING..." &&
            refined !== "No refinement suggestion available." &&
            refined !== "Prompt refinement is temporarily unavailable."
        ) {
            input.value = refined;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.focus();
            updateCharacterCounter();
        }
    });
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

    // Aadhaar-like 12 digit numbers.
    masked = masked.replace(
        /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/g,
        "[ID NUMBER REDACTED]"
    );

    // Indian phone numbers.
    masked = masked.replace(
        /(?:\+91[\s-]?)?[6-9]\d{9}\b/g,
        "[PHONE REDACTED]"
    );

    // Card-like number sequences: mask only if Luhn-valid.
    masked = masked.replace(
        /\b(?:\d[ -]?){13,19}\b/g,
        function (candidate) {
            var digits = candidate.replace(/\D/g, "");

            return isLuhnValid(digits)
                ? "[CARD NUMBER REDACTED]"
                : candidate;
        }
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
    var input = document.getElementById("msg");
    var sendButton = document.getElementById("sendBtn");

    if (!input || isSending) return;

    var message = input.value.trim();
    if (!message) return;

    isSending = true;

    if (sendButton) {
        sendButton.disabled = true;
        sendButton.classList.add("loading");
    }

    // Prevent pending analysis from overwriting the latest UI.
    clearTimeout(refinementTimer);
    refinementRequestId++;

    // Mask PII before displaying the user's message in the chat.
    var safeMessage = maskPIIForAnalysis(message);

    addMessage(safeMessage, "user");

    input.value = "";
    updateCharacterCounter();

    var refinedBox = document.getElementById("refinedPrompt");
    if (refinedBox) refinedBox.innerText = EMPTY_REFINED;

    showTypingIndicator();

    try {
        var response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                chat_id: chatId
            })
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

        // Prefer the backend's redacted safe message when provided.
        var visibleUserMessage =
            data.safe_message ||
            data.redacted_message ||
            safeMessage;

        updateLastUserMessage(visibleUserMessage);

        var answer =
            data.response ||
            data.answer ||
            data.reply ||
            data.assistant_message ||
            data.message;

        if (typeof answer !== "string" || !answer.trim()) {
            answer = "I couldn't generate a response. Please try again.";
        }

        addMessage(answer, "assistant");

        updateDashboard(data);
        renderProducts(data.products || data.results || []);

    } catch (error) {
        removeTypingIndicator();

        addMessage(
            "Sorry, I couldn't complete that request. " +
            "Please check your connection and try again.",
            "assistant"
        );

        console.error("Chat error:", error);
    } finally {
        isSending = false;

        if (sendButton) {
            sendButton.disabled = false;
            sendButton.classList.remove("loading");
        }

        if (input) input.focus();
    }
}

/* ----------------------------- Chat rendering --------------------------- */

function addMessage(message, role) {
    var chat = document.getElementById("chat");
    if (!chat) return;

    var wrapper = document.createElement("div");
    wrapper.className = "message " + role;

    var content = document.createElement("div");
    content.className = "message-content";

    var safeText = String(message == null ? "" : message);

    if (role === "assistant" && window.marked && window.DOMPurify) {
        try {
            content.innerHTML = DOMPurify.sanitize(
                marked.parse(safeText)
            );
        } catch (error) {
            content.textContent = safeText;
        }
    } else {
        content.textContent = safeText;
    }

    wrapper.appendChild(content);
    chat.appendChild(wrapper);

    chat.scrollTop = chat.scrollHeight;

    return wrapper;
}

function updateLastUserMessage(message) {
    var chat = document.getElementById("chat");
    if (!chat) return;

    var userMessages = chat.querySelectorAll(".message.user");
    if (!userMessages.length) return;

    var lastMessage = userMessages[userMessages.length - 1];
    var content = lastMessage.querySelector(".message-content");

    if (content) {
        // Use textContent to avoid rendering untrusted HTML.
        content.textContent = String(message || "");
    }
}

/* ----------------------------- Typing indicator ------------------------- */

function showTypingIndicator() {
    removeTypingIndicator();

    var chat = document.getElementById("chat");
    if (!chat) return;

    var indicator = document.createElement("div");
    indicator.id = "typingIndicator";
    indicator.className = "message assistant typing-indicator";

    var content = document.createElement("div");
    content.className = "message-content";
    content.textContent = "Verity AI is thinking…";

    indicator.appendChild(content);
    chat.appendChild(indicator);
    chat.scrollTop = chat.scrollHeight;
}

function removeTypingIndicator() {
    var indicator = document.getElementById("typingIndicator");
    if (indicator) indicator.remove();
}

/* ----------------------------- Product rendering ------------------------ */

function renderProducts(products) {
    var section = document.getElementById("productsSection");
    var container = document.getElementById("products");

    if (!section || !container) return;

    container.replaceChildren();

    if (!Array.isArray(products) || products.length === 0) {
        section.style.display = "none";
        return;
    }

    section.style.display = "";

    products.forEach(function (product) {
        if (!product || typeof product !== "object") return;

        var card = document.createElement("article");
        card.className = "product-card";

        var title = String(
            product.title ||
            product.name ||
            product.product_name ||
            "Product"
        );

        var price = String(
            product.price ||
            product.displayed_price ||
            product.cost ||
            ""
        );

        var description = String(
            product.description ||
            product.summary ||
            ""
        );

        var imageUrl = safeHttpUrl(
            product.image ||
            product.image_url ||
            product.thumbnail ||
            ""
        );

        var productUrl = safeHttpUrl(
            product.url ||
            product.link ||
            product.product_url ||
            ""
        );

        if (imageUrl) {
            var imageContainer = document.createElement("div");
            imageContainer.className = "product-image-container";

            var image = document.createElement("img");
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

        if (price) {
            var priceElement = document.createElement("p");
            priceElement.className = "product-price";
            priceElement.textContent = price;
            details.appendChild(priceElement);
        }

        if (description) {
            var descriptionElement = document.createElement("p");
            descriptionElement.className = "product-description";
            descriptionElement.textContent = description;
            details.appendChild(descriptionElement);
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

    if (!container.children.length) {
        section.style.display = "none";
    }
}

function safeHttpUrl(value) {
    if (!value || typeof value !== "string") return "";

    try {
        var parsed = new URL(value, window.location.origin);

        if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
            return "";
        }

        return parsed.href;
    } catch (_) {
        return "";
    }
}

/* ----------------------------- Dashboard updates ------------------------ */

function updateDashboard(data) {
    if (!data || typeof data !== "object") return;

    setTextIfPresent("memory", firstDefined(
        data.memory,
        data.memory_status,
        data.context,
        data.context_status
    ));

    var tokenValue = firstNumeric(
        data.tokens,
        data.total_tokens,
        data.token_count,
        data.usage && data.usage.total_tokens
    );

    if (tokenValue !== null) {
        setTextIfPresent("tokens", formatNumber(tokenValue));
    }

    var costValue = firstNumeric(
        data.token_cost,
        data.cost,
        data.estimated_cost,
        data.usage && data.usage.cost
    );

    if (costValue !== null) {
        setTextIfPresent("tokenCost", "$" + costValue.toFixed(6));
    }

    var piiValue = firstDefined(
        data.pii,
        data.pii_redacted,
        data.redactions,
        data.pii_count
    );

    if (piiValue !== undefined) {
        setTextIfPresent(
            "pii",
            typeof piiValue === "boolean"
                ? (piiValue ? "Protected" : "None detected")
                : String(piiValue)
        );
    }

    var warningValue = firstDefined(
        data.warn,
        data.warning,
        data.warnings
    );

    if (warningValue !== undefined) {
        setTextIfPresent(
            "warn",
            Array.isArray(warningValue)
                ? warningValue.join(", ")
                : String(warningValue)
        );
    }

    var filterValue = firstDefined(
        data.filter_changes,
        data.filterChanges,
        data.contextlock_changes,
        data.filters_applied
    );

    if (filterValue !== undefined) {
        setTextIfPresent(
            "filterChanges",
            Array.isArray(filterValue)
                ? filterValue.join(", ")
                : String(filterValue)
        );
    }

    var refinedValue = firstDefined(
        data.refined_prompt,
        data.refinedPrompt,
        data.refined
    );

    if (typeof refinedValue === "string" && refinedValue.trim()) {
        setTextIfPresent("refinedPrompt", refinedValue);
    }

    var tokenPercent = firstNumeric(
        data.token_percent,
        data.tokenPercent,
        data.token_percentage,
        data.usage && data.usage.percent
    );

    if (tokenPercent !== null) {
        tokenPercent = Math.max(0, Math.min(100, tokenPercent));

        setTextIfPresent("tokenPercent", tokenPercent.toFixed(0) + "%");

        var circle = document.getElementById("tokenCircle");
        if (circle) {
            circle.style.setProperty("--token-percent", tokenPercent + "%");
            circle.style.background =
                "conic-gradient(#8b5cf6 " +
                tokenPercent +
                "%, rgba(255,255,255,.08) 0)";
        }
    }
}

function setTextIfPresent(id, value) {
    if (value === undefined || value === null) return;

    var element = document.getElementById(id);
    if (element) element.textContent = String(value);
}

function firstDefined() {
    for (var i = 0; i < arguments.length; i++) {
        if (
            arguments[i] !== undefined &&
            arguments[i] !== null &&
            arguments[i] !== ""
        ) {
            return arguments[i];
        }
    }

    return undefined;
}

function firstNumeric() {
    for (var i = 0; i < arguments.length; i++) {
        if (arguments[i] === null || arguments[i] === undefined || arguments[i] === "") {
            continue;
        }

        var value = Number(arguments[i]);

        if (Number.isFinite(value)) return value;
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
    var dashboard = document.getElementById("dashboard");
    var overlay = document.getElementById("dashboardOverlay");

    /*
     * Important:
     * Do NOT add another click handler to #dashboardBtn here.
     * Your HTML already uses onclick="toggleDashboard()".
     * Registering both handlers can toggle the drawer twice.
     */

    if (overlay) {
        overlay.addEventListener("click", closeDashboard);
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeDashboard();
    });

    window.addEventListener("resize", function () {
        if (window.matchMedia("(min-width: 1251px)").matches) {
            closeDashboard();
        }
    });

    if (dashboard && window.matchMedia("(min-width: 1251px)").matches) {
        dashboard.classList.remove("open");
    }

    setupRefinedPromptButton();
}

function openDashboard() {
    var dashboard = document.getElementById("dashboard");
    var overlay = document.getElementById("dashboardOverlay");

    if (dashboard) dashboard.classList.add("open");
    if (overlay) overlay.classList.add("active");
}

function closeDashboard() {
    var dashboard = document.getElementById("dashboard");
    var overlay = document.getElementById("dashboardOverlay");

    if (dashboard) dashboard.classList.remove("open");
    if (overlay) overlay.classList.remove("active");
}

function toggleDashboard() {
    var dashboard = document.getElementById("dashboard");

    if (!dashboard) return;

    if (dashboard.classList.contains("open")) {
        closeDashboard();
    } else {
        openDashboard();
    }
}

/* ----------------------------- Example prompts -------------------------- */

function setupExamplePrompts() {
    var examples = document.querySelectorAll(
        "[data-prompt], .example-prompt, .prompt-suggestion"
    );

    examples.forEach(function (element) {
        element.addEventListener("click", function () {
            var input = document.getElementById("msg");
            if (!input) return;

            var prompt =
                element.getAttribute("data-prompt") ||
                element.textContent.trim();

            if (!prompt) return;

            input.value = prompt;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.focus();
            updateCharacterCounter();
        });
    });
}

/* ----------------------------- Character counter ------------------------ */

function setupCharacterCounter() {
    updateCharacterCounter();
}

function updateCharacterCounter() {
    var input = document.getElementById("msg");
    var counter = document.getElementById("characterCount");

    if (!counter) counter = document.getElementById("charCount");

    if (!input || !counter) return;

    counter.textContent = input.value.length.toLocaleString("en-IN");
}

/* ----------------------------- HTML escaping utility -------------------- */

function escapeHtml(value) {
    if (value === null || value === undefined) return "";

    var div = document.createElement("div");
    div.textContent = String(value);

    return div.innerHTML
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}