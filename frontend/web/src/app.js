// ==========================================================================
// App — UI orchestration for "The Digital Curator"
// ==========================================================================

import { CONFIG, createThread, streamResearch, extractReport, wakeUpServer, freshToken, withRetry } from './api.js';
import { markdownToHtml } from './markdown.js';

// ── Sample Topics ──
const SAMPLE_TOPICS = [
    "What are the dangers that animal advocates face in India?",
    "Tell me about the state of pig farming in India",
    "What are key missing data for fish farming in India?",
    "Animal advocacy differences between southern and northern India",
    "How should cage-free campaigns be adapted to India?",
    "What is the current state of dairy welfare regulations in India?",
    "How does religious and cultural context affect animal advocacy in India?",
    "What are the biggest challenges for farmed animal sanctuaries in India?",
    "Tell me about the shrimp aquaculture industry in India",
    "What corporate campaigns have been most effective for animal welfare in India?"
];

let _topicIndex = -1;
let currentPercent = 0;

// ── DOM References ──
const $ = (id) => document.getElementById(id);

// ── Topic Randomizer ──
window.randomizeTopic = function () {
    _topicIndex = (_topicIndex + 1) % SAMPLE_TOPICS.length;
    $("topic").value = SAMPLE_TOPICS[_topicIndex];
    $("topic").focus();
};

// ── Progress Bar ──
function resetProgressBar() {
    currentPercent = 0;
    const fill = $("progress-fill");
    const pct = $("progress-percent");
    fill.style.width = "0%";
    fill.className = "progress-fill";
    pct.textContent = "0%";
    pct.className = "progress-percent";
    $("progress-status-text").textContent = "";
}

function updateProgress(percent, statusText) {
    if (percent <= currentPercent) return;
    currentPercent = percent;
    $("progress-fill").style.width = percent + "%";
    $("progress-percent").textContent = percent + "%";
    if (statusText) {
        $("progress-status-text").textContent = statusText;
    }
}

function abortProgress(statusText) {
    $("progress-fill").classList.add("aborted");
    $("progress-percent").classList.add("aborted");
    $("progress-percent").textContent = "Aborted";
    if (statusText) {
        $("progress-status-text").textContent = statusText;
    }
}

// ── UI Helpers ──
function showError(msg) {
    const el = $("error-banner");
    el.textContent = msg;
    el.classList.add("visible");
}

function hideError() {
    $("error-banner").classList.remove("visible");
}

function addLog(text) {
    const log = $("progress-log");
    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.textContent = text;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function setStatus(text) {
    $("progress-status").textContent = text;
}

// ── Layers Panel ──
const LAYERS_PLACEHOLDER = {
    headline: "Enter a research topic to see how change moves through the macro, meso, and micro layers.",
    macro: "Policy, legal, and regulatory forces that shape the national landscape. Enter a topic to see the structural levers at play.",
    meso: "Institutional actors \u2014 industry bodies, retailers, cooperatives, NGOs \u2014 that translate policy into practice. Enter a topic to see who holds power at this level.",
    micro: "Cultural, economic, and behavioral dynamics at the level of producers, consumers, and communities. Enter a topic to see the on-the-ground realities."
};

function showLayersShimmer() {
    $("layers-headline").classList.add("loading");
    ["layer-macro-body", "layer-meso-body", "layer-micro-body"].forEach(id => {
        $(id).innerHTML =
            '<div class="layer-shimmer"><span></span><span></span><span></span></div>';
    });
}

function populateLayers(jsonStr) {
    try {
        const data = JSON.parse(jsonStr);
        $("layers-headline").textContent = data.synthesis || "";
        $("layers-headline").classList.remove("loading");

        const boldify = (text) => text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        fadeIn("layer-macro-body", boldify(data.macro || ""));
        fadeIn("layer-meso-body", boldify(data.meso || ""));
        fadeIn("layer-micro-body", boldify(data.micro || ""));
    } catch (e) {
        console.error("Failed to parse layers briefing:", e);
        // On parse failure, remove shimmer and show a fallback
        $("layers-headline").classList.remove("loading");
        $("layers-headline").textContent = "Layers briefing could not be parsed.";
    }
}

function fadeIn(elementId, html) {
    const el = $(elementId);
    el.style.opacity = "0";
    el.innerHTML = html;
    requestAnimationFrame(() => {
        el.style.transition = "opacity 250ms ease";
        el.style.opacity = "1";
    });
}

function resetLayers() {
    $("layers-headline").classList.remove("loading");
    $("layers-headline").textContent = LAYERS_PLACEHOLDER.headline;
    $("layer-macro-body").style.opacity = "1";
    $("layer-macro-body").innerHTML = LAYERS_PLACEHOLDER.macro;
    $("layer-meso-body").style.opacity = "1";
    $("layer-meso-body").innerHTML = LAYERS_PLACEHOLDER.meso;
    $("layer-micro-body").style.opacity = "1";
    $("layer-micro-body").innerHTML = LAYERS_PLACEHOLDER.micro;
}

// ── State Transitions ──
// Layers panel is always visible — no show/hide needed for it.
// Only loading spinner and report surface toggle.

function showLoading() {
    $("report-loading").classList.add("visible");
    $("report-surface").classList.remove("visible");
}

function hideLoading() {
    $("report-loading").classList.remove("visible");
}

function showReport() {
    $("report-loading").classList.remove("visible");
    $("report-surface").classList.add("visible");
}

function activateSidePanel() {
    $("panel-empty").style.display = "none";
    $("progress-container").classList.add("active");
    $("meta-card").classList.add("visible");
}

function resetSidePanel() {
    $("panel-empty").style.display = "flex";
    $("progress-container").classList.remove("active");
    $("meta-card").classList.remove("visible");
    $("progress-log").innerHTML = "";
}

// ── Side Panel Toggle (mobile) ──
window.toggleSidePanel = function () {
    const panel = document.querySelector(".side-panel");
    panel.classList.toggle("open");
};

// ── Reset Form ──
window.resetForm = function () {
    resetLayers();
    hideLoading();
    $("report-surface").classList.remove("visible");
    resetSidePanel();
    resetProgressBar();
    $("report-content").innerHTML = "";
    $("generate-btn").disabled = false;
    $("topic").value = "";
    $("topic").disabled = false;
    $("max-analysts").disabled = false;
};

// ── Main Research Flow ──
window.startResearch = async function () {
    hideError();

    const topic = $("topic").value.trim();
    const maxAnalysts = parseInt($("max-analysts").value, 10);

    if (!topic) {
        showError("Please enter a research topic.");
        return;
    }
    if (isNaN(maxAnalysts) || maxAnalysts < 1 || maxAnalysts > 6) {
        showError("Number of analysts must be between 1 and 6.");
        return;
    }

    // Disable inputs
    $("generate-btn").disabled = true;
    $("topic").disabled = true;
    $("max-analysts").disabled = true;

    // Update metadata card
    $("meta-topic").textContent = topic;
    $("meta-analysts").textContent = maxAnalysts;

    // Transition UI — shimmer cards + show loading below + activate side panel
    showLayersShimmer();
    showLoading();
    activateSidePanel();
    resetProgressBar();
    setStatus("Creating research thread...");
    addLog("Topic: " + topic);
    addLog("Analysts: " + maxAnalysts);

    try {
        // ── Pre-flight: verify Clerk session before waking server ──
        if (typeof clerk === 'undefined' || !clerk.session) {
            throw new Error('Your session has expired. Please sign in again.');
        }
        try {
            await clerk.session.getToken();
        } catch {
            throw new Error('Your session has expired. Please sign in again.');
        }

        // ── Wake up server if Render has spun down ──
        const serverReady = await wakeUpServer((statusText) => {
            setStatus(statusText);
            addLog(statusText);
        });

        if (!serverReady) {
            throw new Error(
                'Server did not respond after 90 seconds. ' +
                'It may be experiencing issues. Please try again in a moment.'
            );
        }

        // ── Fresh token now that server is warm ──
        const token = await freshToken();
        if (!token) {
            throw new Error('Your session has expired. Please sign in again.');
        }

        // ── Create thread with retry ──
        setStatus('Creating research thread...');
        const threadId = await withRetry(() => createThread());
        addLog('Thread created: ' + threadId.slice(0, 8) + '...');

        // ── Stream research with retry ──
        setStatus('Running research pipeline...');
        const fullContent = await withRetry(
            () => streamResearch(threadId, topic, maxAnalysts, {
                onProgress: updateProgress,
                onAbort: abortProgress,
                onLog: addLog,
                onStatus: setStatus,
                onLayersBriefing: populateLayers,
                onContent: () => {}
            }),
            { maxRetries: 1, retryDelay: 5000 }
        );
    } catch (err) {
        console.error(err);
        setStatus("Error occurred");
        addLog('Error: ' + err.message);
        $("spinner").style.display = "none";

        if (err.message.includes("401") || err.message.includes("session has expired")) {
            showError("Your session has expired. Please sign in again.");
            $("sign-in").style.display = "flex";
            if (typeof clerk !== "undefined") {
                clerk.mountSignIn($("sign-in"));
            }
        } else {
            showError(err.message);
        }

        $("generate-btn").disabled = false;
        $("topic").disabled = false;
        $("max-analysts").disabled = false;
        hideLoading();
    }
};

// Make CONFIG accessible globally for main.js Clerk integration
window.CONFIG = CONFIG;
