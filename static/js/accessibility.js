// accessibility.js — UniPi LMS Accessibility Toolkit
// Features: font scaling, high contrast, dyslexia font, grayscale,
// underline links, large cursor, reading guide, reduce motion.
// Persists all preferences in localStorage.

(function () {
    'use strict';

    var STORAGE_KEY = 'lms-a11y';
    var FONT_MIN = -2;
    var FONT_MAX = 4;

    // Default accessibility state
    var defaults = {
        fontLevel: 0,
        highContrast: false,
        dyslexiaFont: false,
        grayscale: false,
        underlineLinks: false,
        largeCursor: false,
        readingGuide: false,
        reduceMotion: false
    };

    // Load persisted preferences
    function loadPrefs() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                var parsed = JSON.parse(raw);
                var prefs = {};
                for (var key in defaults) {
                    prefs[key] = parsed.hasOwnProperty(key) ? parsed[key] : defaults[key];
                }
                return prefs;
            }
        } catch (e) { /* ignore */ }
        return Object.assign({}, defaults);
    }

    function savePrefs(prefs) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (e) { /* ignore */ }
    }

    var state = loadPrefs();

    // Apply a single class toggle
    function toggleBodyClass(className, on) {
        document.body.classList.toggle(className, on);
    }

    // Apply font level classes
    function applyFontLevel(level) {
        // Remove all font level classes
        for (var i = FONT_MIN; i <= FONT_MAX; i++) {
            if (i !== 0) document.body.classList.remove('a11y-font-' + i);
        }
        if (level !== 0) {
            document.body.classList.add('a11y-font-' + level);
        }
    }

    // Apply all preferences to the DOM
    function applyAll() {
        applyFontLevel(state.fontLevel);
        toggleBodyClass('a11y-high-contrast', state.highContrast);
        toggleBodyClass('a11y-dyslexia-font', state.dyslexiaFont);
        toggleBodyClass('a11y-grayscale', state.grayscale);
        toggleBodyClass('a11y-underline-links', state.underlineLinks);
        toggleBodyClass('a11y-large-cursor', state.largeCursor);
        toggleBodyClass('a11y-reading-guide-on', state.readingGuide);
        toggleBodyClass('a11y-reduce-motion', state.reduceMotion);
        updateButtonStates();
    }

    // Update aria-pressed on toggle buttons
    function updateButtonStates() {
        var map = {
            'high-contrast': state.highContrast,
            'dyslexia-font': state.dyslexiaFont,
            'grayscale': state.grayscale,
            'underline-links': state.underlineLinks,
            'large-cursor': state.largeCursor,
            'reading-guide': state.readingGuide,
            'reduce-motion': state.reduceMotion
        };
        document.querySelectorAll('[data-a11y]').forEach(function (btn) {
            var action = btn.getAttribute('data-a11y');
            if (map.hasOwnProperty(action)) {
                var isActive = map[action];
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                btn.classList.toggle('active', isActive);
            }
        });
    }

    // Panel open/close
    function openPanel() {
        var panel = document.getElementById('a11y-panel');
        var toggle = document.getElementById('a11y-toolbar-toggle');
        if (panel) {
            panel.classList.add('a11y-panel--open');
            panel.setAttribute('aria-hidden', 'false');
        }
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
        // Focus first interactive element in panel
        setTimeout(function () {
            var firstBtn = panel && panel.querySelector('.a11y-panel-close, .a11y-btn');
            if (firstBtn) firstBtn.focus();
        }, 250);
    }

    function closePanel() {
        var panel = document.getElementById('a11y-panel');
        var toggle = document.getElementById('a11y-toolbar-toggle');
        if (panel) {
            panel.classList.remove('a11y-panel--open');
            panel.setAttribute('aria-hidden', 'true');
        }
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
            toggle.focus();
        }
    }

    function isPanelOpen() {
        var panel = document.getElementById('a11y-panel');
        return panel && panel.classList.contains('a11y-panel--open');
    }

    // Reading guide: follows mouse
    function handleReadingGuide(e) {
        var guide = document.getElementById('a11y-reading-guide');
        if (guide && state.readingGuide) {
            guide.style.top = (e.clientY - 6) + 'px';
        }
    }

    // Handle button actions
    function handleAction(action) {
        switch (action) {
            case 'font-increase':
                if (state.fontLevel < FONT_MAX) {
                    state.fontLevel++;
                    applyFontLevel(state.fontLevel);
                    savePrefs(state);
                }
                break;
            case 'font-decrease':
                if (state.fontLevel > FONT_MIN) {
                    state.fontLevel--;
                    applyFontLevel(state.fontLevel);
                    savePrefs(state);
                }
                break;
            case 'font-reset':
                state.fontLevel = 0;
                applyFontLevel(0);
                savePrefs(state);
                break;
            case 'high-contrast':
                state.highContrast = !state.highContrast;
                break;
            case 'dyslexia-font':
                state.dyslexiaFont = !state.dyslexiaFont;
                break;
            case 'grayscale':
                state.grayscale = !state.grayscale;
                break;
            case 'underline-links':
                state.underlineLinks = !state.underlineLinks;
                break;
            case 'large-cursor':
                state.largeCursor = !state.largeCursor;
                break;
            case 'reading-guide':
                state.readingGuide = !state.readingGuide;
                break;
            case 'reduce-motion':
                state.reduceMotion = !state.reduceMotion;
                break;
            case 'reset-all':
                state = Object.assign({}, defaults);
                break;
            default:
                return;
        }
        applyAll();
        savePrefs(state);
    }

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function () {
        // Apply saved preferences immediately
        applyAll();

        // Toggle button opens/closes panel
        var toggleBtn = document.getElementById('a11y-toolbar-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                if (isPanelOpen()) {
                    closePanel();
                } else {
                    openPanel();
                }
            });
        }

        // Close button
        var closeBtn = document.getElementById('a11y-panel-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', closePanel);
        }

        // Handle clicks on a11y action buttons
        document.querySelectorAll('[data-a11y]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                handleAction(btn.getAttribute('data-a11y'));
            });
        });

        // Close panel on Escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isPanelOpen()) {
                closePanel();
            }
        });

        // Close panel when clicking outside
        document.addEventListener('click', function (e) {
            var toolbar = document.getElementById('a11y-toolbar');
            if (isPanelOpen() && toolbar && !toolbar.contains(e.target)) {
                closePanel();
            }
        });

        // Reading guide follows mouse
        document.addEventListener('mousemove', handleReadingGuide);

        // Keyboard focus trap inside panel when open
        var panel = document.getElementById('a11y-panel');
        if (panel) {
            panel.addEventListener('keydown', function (e) {
                if (e.key !== 'Tab') return;
                var focusable = panel.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
                if (focusable.length === 0) return;
                var first = focusable[0];
                var last = focusable[focusable.length - 1];
                if (e.shiftKey) {
                    if (document.activeElement === first) {
                        e.preventDefault();
                        last.focus();
                    }
                } else {
                    if (document.activeElement === last) {
                        e.preventDefault();
                        first.focus();
                    }
                }
            });
        }

        // Respect prefers-reduced-motion on first load
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            if (!state.reduceMotion) {
                state.reduceMotion = true;
                applyAll();
                savePrefs(state);
            }
        }

        // Announce accessibility toolbar presence to screen readers
        var liveRegion = document.createElement('div');
        liveRegion.setAttribute('aria-live', 'polite');
        liveRegion.setAttribute('aria-atomic', 'true');
        liveRegion.className = 'sr-only';
        liveRegion.id = 'a11y-live-region';
        document.body.appendChild(liveRegion);
    });

    // Apply font level before DOMContentLoaded to prevent FOUC
    try {
        var earlyState = loadPrefs();
        if (earlyState.fontLevel !== 0) {
            document.documentElement.classList.add('a11y-font-' + earlyState.fontLevel);
        }
        if (earlyState.highContrast) {
            document.documentElement.classList.add('a11y-high-contrast');
        }
        if (earlyState.dyslexiaFont) {
            document.documentElement.classList.add('a11y-dyslexia-font');
        }
    } catch (e) { /* ignore */ }
})();
