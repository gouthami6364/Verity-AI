/* =========================================================
   VERITY AI
   Main JavaScript
   ========================================================= */


/* =========================================================
   GLOBAL STATE
   ========================================================= */

var chatId = Math.random()
    .toString(36)
    .substring(2);

var refinementTimer = null;
var refinementRequestId = 0;
var isSending = false;

var EMPTY_REFINED = "Start typing a prompt...";


/* =========================================================
   DOM READY
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    setupInput();
});


/* =========================================================
   INPUT SETUP
   ========================================================= */

function setupInput() {

    var messageInput = document.getElementById("msg");

    if (!messageInput) {
        return;
    }

    messageInput.addEventListener("input", function () {
        schedulePromptRefinement();
    });

    messageInput.addEventListener("keydown", function (event) {

        if (event.key === "Enter") {

            event.preventDefault();

            sendMessage();
        }

    });
}


/* =========================================================
   PROMPT REFINEMENT
   ========================================================= */

function schedulePromptRefinement() {

    clearTimeout(refinementTimer);

    refinementTimer = setTimeout(function () {
        refinePrompt();
    }, 800);
}


async function refinePrompt() {

    var input = document.getElementById("msg");
    var refinedBox = document.getElementById("refinedPrompt");

    if (!input || !refinedBox) {
        return;
    }

    var text = input.value.trim();

    if (!text) {

        refinementRequestId++;

        refinedBox.innerText = EMPTY_REFINED;

        return;
    }

    /*
     * Do not send obvious PII to /analyze in cleartext.
     *
     * The actual /chat request still sends the original
     * message to the backend where pii_redactor.py protects it.
     */

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

            throw new Error(
                "Prompt refinement failed: " +
                response.status
            );

        }

        var data = await response.json();

        /*
         * Ignore old requests.
         */

        if (requestId !== refinementRequestId) {
            return;
        }

        /*
         * Make sure the user didn't type again.
         */

        if (input.value.trim() !== text) {
            return;
        }

        refinedBox.innerText =
            data.refined_prompt ||
            safeForAnalysis;

    }
    catch (error) {

        console.error(
            "Prompt refinement error:",
            error
        );

        if (requestId === refinementRequestId) {

            refinedBox.innerText =
                safeForAnalysis;
        }
    }
}


/* =========================================================
   CLIENT-SIDE PII MASKING
   =========================================================

   This is NOT the security boundary.

   The real protection remains:

       pii_redactor.py

   This function simply prevents obvious PII from being sent
   to /analyze while the user is typing.

   ========================================================= */

function maskPIIForAnalysis(text) {

    if (!text) {
        return "";
    }

    var result = String(text);


    /* -----------------------------------------------------
       EMAIL
       ----------------------------------------------------- */

    result = result.replace(
        /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/gi,
        "[EMAIL_REDACTED]"
    );


    /* -----------------------------------------------------
       CREDIT CARD

       Handles:

       4111 1111 1111 1111
       4111-1111-1111-1111
       4111111111111111
       ----------------------------------------------------- */

    result = result.replace(
        /(?<!\d)(?:\d[ -]?){13,19}(?!\d)/g,
        function (match) {

            var digits = match.replace(/\D/g, "");

            if (
                digits.length < 13 ||
                digits.length > 19
            ) {
                return match;
            }

            if (luhnValid(digits)) {
                return "[CARD_REDACTED]";
            }

            return match;
        }
    );


    /* -----------------------------------------------------
       AADHAAR
       ----------------------------------------------------- */

    result = result.replace(
        /(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![ -]?\d)/g,
        "[AADHAAR_REDACTED]"
    );


    /* -----------------------------------------------------
       PAN
       ----------------------------------------------------- */

    result = result.replace(
        /\b[A-Z]{5}\d{4}[A-Z]\b/gi,
        "[PAN_REDACTED]"
    );


    /* -----------------------------------------------------
       INDIAN PHONE

       Supports:

       9876543210
       +91 9876543210
       +91-9876543210
       09876543210
       ----------------------------------------------------- */

    result = result.replace(
        /(?<!\d)(?:\+91[ -]?|91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)/g,
        "[PHONE_REDACTED]"
    );


    return result;
}


/* =========================================================
   LUHN VALIDATION
   ========================================================= */

function luhnValid(number) {

    var digits = String(number)
        .replace(/\D/g, "");

    if (
        digits.length < 13 ||
        digits.length > 19
    ) {
        return false;
    }

    var total = 0;
    var shouldDouble = false;

    for (
        var i = digits.length - 1;
        i >= 0;
        i--
    ) {

        var digit =
            Number(digits.charAt(i));

        if (shouldDouble) {

            digit *= 2;

            if (digit > 9) {
                digit -= 9;
            }
        }

        total += digit;

        shouldDouble = !shouldDouble;
    }

    return total % 10 === 0;
}


/* =========================================================
   USE REFINED PROMPT
   ========================================================= */

function useRefinedPrompt() {

    var input =
        document.getElementById("msg");

    var refinedBox =
        document.getElementById("refinedPrompt");

    if (!input || !refinedBox) {
        return;
    }

    var refined =
        refinedBox.innerText.trim();

    if (
        !refined ||
        refined === EMPTY_REFINED ||
        refined === "REFINING..."
    ) {
        return;
    }

    input.value = refined;

    input.focus();

    clearTimeout(refinementTimer);
}


/* =========================================================
   SEND MESSAGE
   ========================================================= */

async function sendMessage() {

    if (isSending) {
        return;
    }

    var input =
        document.getElementById("msg");

    if (!input) {
        return;
    }

    var message =
        input.value.trim();

    if (!message) {
        return;
    }

    clearTimeout(refinementTimer);

    refinementRequestId++;

    isSending = true;


    /* -----------------------------------------------------
       SEND BUTTON
       ----------------------------------------------------- */

    var sendButton =
        document.getElementById("sendBtn");

    if (sendButton) {

        sendButton.disabled = true;

        sendButton.innerText = "SENDING...";
    }


    /* -----------------------------------------------------
       TEMPORARY PROTECTED MESSAGE

       NEVER display the original message directly.
       ----------------------------------------------------- */

    var userMessage = addMessage(
        "user",
        "PROTECTING MESSAGE..."
    );


    try {

        var response = await fetch(
            "/chat",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    session_id: chatId,
                    message: message
                })
            }
        );


        var data =
            await response.json().catch(
                function () {
                    return null;
                }
            );


        if (!response.ok) {

            throw new Error(
                (data && data.reply) ||
                (
                    "Chat request failed: " +
                    response.status
                )
            );
        }


        /* -------------------------------------------------
           REPLACE TEMPORARY USER MESSAGE

           Only safe_message from backend is displayed.

           NEVER use:

               data.safe_message || message
           ------------------------------------------------- */

        if (userMessage) {

            var bubble =
                userMessage.querySelector(
                    ".message-bubble"
                );

            if (bubble) {

                if (
                    data &&
                    data.safe_message !== undefined &&
                    data.safe_message !== null
                ) {

                    bubble.innerText =
                        data.safe_message;

                }
                else {

                    bubble.innerText =
                        "[MESSAGE PROTECTED]";
                }
            }
        }


        /* -------------------------------------------------
           BOT RESPONSE
           ------------------------------------------------- */

        addMessage(
            "bot",
            (data && data.reply) ||
            "No response received."
        );


        /* -------------------------------------------------
           DASHBOARD
           ------------------------------------------------- */

        updateDashboard(data);


        /* -------------------------------------------------
           PRODUCTS

           null means no new product result,
           so keep existing products visible.
           ------------------------------------------------- */

        if (
            data &&
            data.products !== null &&
            data.products !== undefined
        ) {

            showProducts(
                data.products
            );
        }


        /* -------------------------------------------------
           CLEAR INPUT
           ------------------------------------------------- */

        input.value = "";

    }
    catch (error) {

        console.error(
            "Chat error:",
            error
        );


        /*
         * Never reveal original message
         * in an error path.
         */

        if (userMessage) {

            var errorBubble =
                userMessage.querySelector(
                    ".message-bubble"
                );

            if (errorBubble) {

                errorBubble.innerText =
                    "[MESSAGE PROTECTED]";
            }
        }


        addMessage(
            "bot",
            "Unable to process your request right now."
        );
    }
    finally {

        isSending = false;

        if (sendButton) {

            sendButton.disabled = false;

            sendButton.innerText = "SEND";
        }

        input.focus();
    }
}


/* =========================================================
   ADD CHAT MESSAGE
   ========================================================= */

function addMessage(type, text) {

    var chat =
        document.getElementById("chat");

    if (!chat) {
        return null;
    }


    var message =
        document.createElement("div");

    message.className =
        "message " + type;


    var bubble =
        document.createElement("div");

    bubble.className =
        "message-bubble";


    /*
     * innerText is intentional.
     *
     * It prevents user/API text from being
     * interpreted as HTML.
     */

    bubble.innerText = text;


    message.appendChild(bubble);

    chat.appendChild(message);


    chat.scrollTop =
        chat.scrollHeight;


    return message;
}


/* =========================================================
   SHOW PRODUCTS
   ========================================================= */

function showProducts(products) {

    var section =
        document.getElementById(
            "productsSection"
        );

    var container =
        document.getElementById(
            "products"
        );

    if (!section || !container) {
        return;
    }


    container.innerHTML = "";


    /*
     * Backend may return:
     *
     * {
     *     items: [...],
     *     note: "..."
     * }
     */

    if (
        products &&
        !Array.isArray(products)
    ) {

        products =
            products.items || [];
    }


    if (
        !Array.isArray(products) ||
        products.length === 0
    ) {

        section.classList.remove(
            "visible"
        );

        return;
    }


    products.forEach(
        function (product) {

            var card =
                document.createElement(
                    "div"
                );

            card.className =
                "product-card";


            /* ---------------------------------------------
               IMAGE
               --------------------------------------------- */

            var imageUrl =
                safeUrl(
                    product.image ||
                    product.thumbnail ||
                    product.image_url ||
                    ""
                );


            var imageHTML = "";


            if (imageUrl) {

                imageHTML = `
                    <div class="product-image-container">
                        <img
                            class="product-image"
                            src="${escapeHtml(imageUrl)}"
                            alt="${escapeHtml(
                                product.title ||
                                "Product"
                            )}"
                            loading="lazy"
                            referrerpolicy="no-referrer"
                            onerror="this.parentElement.style.display='none';"
                        >
                    </div>
                `;
            }


            /* ---------------------------------------------
               TITLE
               --------------------------------------------- */

            var title =
                escapeHtml(
                    product.title ||
                    "Product"
                );


            /* ---------------------------------------------
               PRICE
               --------------------------------------------- */

            var price =
                escapeHtml(
                    product.price ||
                    product.price_text ||
                    "Price unavailable"
                );


            /* ---------------------------------------------
               SOURCE
               --------------------------------------------- */

            var source =
                escapeHtml(
                    product.source ||
                    ""
                );


            /* ---------------------------------------------
               PRODUCT LINK
               --------------------------------------------- */

            var link =
                safeUrl(product.link);


            var linkHTML = "";


            if (link) {

                linkHTML = `
                    <a
                        class="product-link"
                        href="${escapeHtml(link)}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        VIEW PRODUCT
                    </a>
                `;
            }


            /* ---------------------------------------------
               CARD
               --------------------------------------------- */

            card.innerHTML = `

                ${imageHTML}

                <div class="product-title">
                    ${title}
                </div>

                <div class="product-price">
                    ${price}
                </div>

                <div class="product-source">
                    ${source}
                </div>

                ${linkHTML}

            `;


            container.appendChild(card);
        }
    );


    section.classList.add("visible");
}


/* =========================================================
   SAFE URL
   ========================================================= */

function safeUrl(url) {

    if (!url) {
        return "";
    }

    try {

        var parsed =
            new URL(
                url,
                window.location.origin
            );


        /*
         * Only HTTP and HTTPS links.
         */

        if (
            parsed.protocol === "http:" ||
            parsed.protocol === "https:"
        ) {

            return parsed.href;
        }

    }
    catch (e) {

        /*
         * Invalid URL.
         */
    }

    return "";
}


/* =========================================================
   UPDATE DASHBOARD
   ========================================================= */

function updateDashboard(data) {

    if (!data) {
        return;
    }


    /* =====================================================
       CONTEXT
       ===================================================== */

    var memory =
        document.getElementById(
            "memory"
        );


    if (memory) {

        var filters =
            data.filters;


        if (
            filters &&
            Object.keys(filters).length > 0
        ) {

            memory.innerText =
                formatFilters(filters);

        }
        else {

            memory.innerText =
                "No active context";
        }
    }


    /* =====================================================
       PII
       ===================================================== */

    var pii =
        document.getElementById(
            "pii"
        );


    if (pii) {

        if (
            Array.isArray(
                data.pii_found
            ) &&
            data.pii_found.length > 0
        ) {

            var types =
                data.pii_found
                    .map(
                        function (p) {
                            return p.type;
                        }
                    )
                    .join(", ");


            pii.innerText =
                "PII detected and protected: " +
                types;


            pii.className =
                "panel-value security-warning";

        }
        else {

            pii.innerText =
                "No PII detected";


            pii.className =
                "panel-value";
        }
    }


    /* =====================================================
       WARNINGS
       ===================================================== */

    var warning =
        document.getElementById(
            "warn"
        );


    if (warning) {

        var warnings =
            data.waste_warnings;


        if (
            Array.isArray(warnings) &&
            warnings.length > 0
        ) {

            warning.innerText =
                warnings.join("\n");

        }
        else {

            warning.innerText =
                "No warnings";
        }
    }


    /* =====================================================
       FILTER CHANGES
       ===================================================== */

    var filterChanges =
        document.getElementById(
            "filterChanges"
        );


    if (filterChanges) {

        var changes =
            data.filter_changes;


        if (
            Array.isArray(changes) &&
            changes.length > 0
        ) {

            filterChanges.innerText =
                changes
                    .map(
                        function (c) {

                            var oldValue =
                                (
                                    c.old === null ||
                                    c.old === undefined
                                )
                                    ? "none"
                                    : c.old;


                            var newValue =
                                (
                                    c.new === null ||
                                    c.new === undefined
                                )
                                    ? "removed"
                                    : c.new;


                            return (
                                c.field +
                                ": " +
                                oldValue +
                                " → " +
                                newValue
                            );
                        }
                    )
                    .join("\n");

        }
        else {

            filterChanges.innerText =
                "No changes";
        }
    }


    /* =====================================================
       TOKENS
       ===================================================== */

    updateTokenMeter(
        data.tokens
    );
}


/* =========================================================
   FORMAT FILTERS
   ========================================================= */

function formatFilters(filters) {

    if (!filters) {
        return "No active context";
    }


    var parts = [];


    if (filters.category) {

        parts.push(
            "Category: " +
            filters.category
        );
    }


    if (filters.brand) {

        parts.push(
            "Brand: " +
            filters.brand
        );
    }


    if (filters.color) {

        parts.push(
            "Color: " +
            filters.color
        );
    }


    if (filters.material) {

        parts.push(
            "Material: " +
            filters.material
        );
    }


    if (filters.size) {

        parts.push(
            "Size: " +
            filters.size
        );
    }


    if (
        filters.min_price !== null &&
        filters.min_price !== undefined
    ) {

        parts.push(
            "Min ₹" +
            filters.min_price
        );
    }


    if (
        filters.max_price !== null &&
        filters.max_price !== undefined
    ) {

        parts.push(
            "Max ₹" +
            filters.max_price
        );
    }


    if (parts.length === 0) {

        return "No active context";
    }


    return parts.join("\n");
}


/* =========================================================
   TOKEN METER
   ========================================================= */

function updateTokenMeter(tokens) {

    if (!tokens) {
        return;
    }


    var percentElement =
        document.getElementById(
            "tokenPercent"
        );


    var circle =
        document.getElementById(
            "tokenCircle"
        );


    var tokenText =
        document.getElementById(
            "tokens"
        );


    var costText =
        document.getElementById(
            "tokenCost"
        );


    /* -----------------------------------------------------
       CALCULATE PERCENTAGE
       ----------------------------------------------------- */

    var percent =
        Number(tokens.usage_percent);


    if (!Number.isFinite(percent)) {
        percent = 0;
    }


    percent =
        Math.max(
            0,
            Math.min(
                100,
                percent
            )
        );


    /* -----------------------------------------------------
       TOKEN CIRCLE
       -----------------------------------------------------

       This directly controls the circular progress ring.

       0%   = empty ring
       50%  = half ring
       100% = full ring
       ----------------------------------------------------- */

    if (circle) {

        circle.style.setProperty(
            "--usage",
            percent + "%"
        );


        /*
         * Keep the background explicitly controlled
         * by JavaScript so it works even if the CSS
         * default is different.
         */

        if (percent >= 90) {

            circle.style.background =
                "conic-gradient(" +
                "#ff4d6d 0% " +
                percent +
                "%, " +
                "#24202b " +
                percent +
                "% 100%)";

        }
        else {

            circle.style.background =
                "conic-gradient(" +
                "#a855f7 0% " +
                percent +
                "%, " +
                "#24202b " +
                percent +
                "% 100%)";
        }
    }


    /* -----------------------------------------------------
       PERCENTAGE TEXT INSIDE CIRCLE
       ----------------------------------------------------- */

    if (percentElement) {

        percentElement.innerText =
            formatPercent(percent);


        /*
         * Purple normally.
         *
         * Red when context usage reaches 90%.
         */

        percentElement.style.color =
            percent >= 90
                ? "#ff4d6d"
                : "#c084fc";
    }


    /* -----------------------------------------------------
       TOKEN COUNT
       ----------------------------------------------------- */

    if (tokenText) {

        var total =
            tokens.total;


        var contextLimit =
            tokens.context_limit ||
            131072;


        if (
            total !== undefined &&
            total !== null
        ) {

            tokenText.innerText =
                formatNumber(total) +
                " / " +
                formatNumber(contextLimit) +
                " tokens";
        }
    }


    /* -----------------------------------------------------
       COST
       ----------------------------------------------------- */

    if (costText) {

        var cost =
            Number(tokens.cost_inr);


        if (Number.isFinite(cost)) {

            costText.innerText =
                "₹" +
                cost.toFixed(6);
        }
    }
}


/* =========================================================
   FORMAT NUMBER
   ========================================================= */

function formatNumber(number) {

    var value =
        Number(number);


    if (!Number.isFinite(value)) {
        return "0";
    }


    return Math.round(value)
        .toLocaleString("en-IN");
}


/* =========================================================
   FORMAT PERCENT
   ========================================================= */

function formatPercent(number) {

    var value =
        Number(number);


    if (!Number.isFinite(value)) {
        return "0%";
    }


    if (value < 0.01) {
        return "0%";
    }


    return value.toFixed(2) + "%";
}


/* =========================================================
   DASHBOARD OPEN
   ========================================================= */

function openDashboard() {

    var dashboard =
        document.getElementById(
            "dashboard"
        );


    var overlay =
        document.getElementById(
            "dashboardOverlay"
        );


    if (dashboard) {

        dashboard.classList.add(
            "open"
        );
    }


    if (overlay) {

        overlay.classList.add(
            "active"
        );
    }
}


/* =========================================================
   DASHBOARD CLOSE
   ========================================================= */

function closeDashboard() {

    var dashboard =
        document.getElementById(
            "dashboard"
        );


    var overlay =
        document.getElementById(
            "dashboardOverlay"
        );


    if (dashboard) {

        dashboard.classList.remove(
            "open"
        );
    }


    if (overlay) {

        overlay.classList.remove(
            "active"
        );
    }
}


/* =========================================================
   DASHBOARD TOGGLE
   ========================================================= */

function toggleDashboard() {

    var dashboard =
        document.getElementById(
            "dashboard"
        );


    if (!dashboard) {
        return;
    }


    if (
        dashboard.classList.contains(
            "open"
        )
    ) {

        closeDashboard();

    }
    else {

        openDashboard();
    }
}


/* =========================================================
   ESCAPE HTML
   ========================================================= */

function escapeHtml(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";
    }


    var div =
        document.createElement(
            "div"
        );


    div.textContent =
        String(value);


    /*
     * textContent -> HTML escaping
     *
     * Also escape quotes because these
     * values can appear inside attributes.
     */

    return div.innerHTML
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}


/* =========================================================
   ESC KEY
   ========================================================= */

document.addEventListener(
    "keydown",
    function (event) {

        if (event.key === "Escape") {

            closeDashboard();
        }

    }
);