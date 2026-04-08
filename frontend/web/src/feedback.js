// ==========================================================================
// Feedback — slide-out panel for user testing feedback
// ==========================================================================

import { CONFIG, getHeaders } from './api.js';

let selectedType = 'general';
let panelOpen = false;

// ── Toggle Panel ──
window.toggleFeedback = function () {
    panelOpen = !panelOpen;
    document.getElementById('feedback-panel').classList.toggle('open', panelOpen);
    document.getElementById('feedback-backdrop').classList.toggle('visible', panelOpen);
    document.getElementById('feedback-fab').classList.toggle('hidden', panelOpen);
};

// ── Type Selector ──
function initTypeButtons() {
    document.querySelectorAll('.feedback-type-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.feedback-type-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedType = btn.dataset.type;
        });
    });
}

// ── Submit Feedback ──
window.submitFeedback = async function () {
    const textarea = document.getElementById('feedback-message');
    const message = textarea.value.trim();
    if (!message) {
        textarea.focus();
        return;
    }

    const submitBtn = document.getElementById('feedback-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';

    // Auto-capture page context
    const pageContext = {
        topic: document.getElementById('meta-topic')?.textContent
            || document.getElementById('topic')?.value
            || '',
        page_state: document.getElementById('report-surface')?.classList.contains('visible')
            ? 'viewing_report'
            : 'input',
        url: window.location.href,
    };

    try {
        const resp = await fetch(`${CONFIG.SERVER_URL}/api/feedback`, {
            method: 'POST',
            headers: await getHeaders(),
            body: JSON.stringify({
                message,
                feedback_type: selectedType,
                page_context: pageContext,
            }),
        });

        if (resp.ok) {
            document.getElementById('feedback-success').classList.add('visible');
            textarea.value = '';

            setTimeout(() => {
                document.getElementById('feedback-success').classList.remove('visible');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Send Feedback';
            }, 2500);
        } else {
            const err = await resp.text();
            console.error('Feedback submission failed:', err);
            submitBtn.disabled = false;
            submitBtn.textContent = 'Send Feedback';
        }
    } catch (e) {
        console.error('Feedback submission error:', e);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Send Feedback';
    }
};

// ── Init on DOM ready ──
document.addEventListener('DOMContentLoaded', () => {
    initTypeButtons();
});
