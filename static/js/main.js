// main.js - UniPi LMS: sidebar, AJAX nav, prefetch, alerts

(function() {
    'use strict';

    var XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/html' };
    var DASHBOARD_TITLE_SUFFIX = ' | Πίνακας Ελέγχου';
    var prefetched = Object.create(null);

    function buildDashboardPartialUrl(redirectPath) {
        var base = redirectPath.indexOf('/') === 0 ? window.location.origin + redirectPath : redirectPath;
        var sep = base.indexOf('?') >= 0 ? '&' : '?';
        return base + sep + 'partial=1';
    }

    function setSemesterLinksActive(currentSemester) {
        var current = currentSemester || '';
        document.querySelectorAll('.sidebar-dropdown-item[data-semester], .dashboard-semester-link[data-semester]').forEach(function(link) {
            link.classList.toggle('active', (link.getAttribute('data-semester') || '') === current);
        });
    }

    document.addEventListener('DOMContentLoaded', function() {

        // Sidebar collapse toggle (persisted)
        var sidebar = document.getElementById('app-sidebar');
        var sidebarToggle = document.getElementById('sidebar-toggle');
        if (sidebar && sidebarToggle) {
            if (localStorage.getItem('lms-sidebar-collapsed') === 'true') sidebar.classList.add('sidebar-collapsed');
            sidebarToggle.addEventListener('click', function() {
                sidebar.classList.toggle('sidebar-collapsed');
                localStorage.setItem('lms-sidebar-collapsed', sidebar.classList.contains('sidebar-collapsed'));
            });
        }

        // AJAX semester switch: intercept set_semester links, fetch partial dashboard, replace content
        document.addEventListener('click', function(e) {
            var a = e.target.closest('a[href*="set_semester"]');
            if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
            var href = a.getAttribute('href');
            if (!href || href.charAt(0) === '#') return;
            if (href.indexOf('//') === 0 || (href.indexOf('http') === 0 && href.indexOf(window.location.origin) !== 0)) return;

            e.preventDefault();
            var wrap = document.getElementById('app-content');
            if (!wrap) return;

            wrap.classList.add('app-content-loading');
            fetch(href, { headers: XHR_HEADERS, credentials: 'same-origin' })
                .then(function(res) {
                    if (!res.ok) throw new Error('set_semester failed');
                    return res.json();
                })
                .then(function(data) {
                    if (!data || !data.redirect) throw new Error('no redirect');
                    return fetch(buildDashboardPartialUrl(data.redirect), { headers: XHR_HEADERS, credentials: 'same-origin' });
                })
                .then(function(res) { return res.ok ? res.text() : Promise.reject(new Error('partial failed')); })
                .then(function(html) {
                    wrap.innerHTML = html;
                    wrap.classList.remove('app-content-loading');
                    var partial = wrap.querySelector('.dashboard-partial');
                    setSemesterLinksActive(partial ? partial.getAttribute('data-current-semester') : null);
                    var dashboardLink = document.querySelector('a[href*="/dashboard"]');
                    if (dashboardLink) history.replaceState(null, '', dashboardLink.href);
                    document.title = (document.title.replace(/\s*\|.*$/, '') || 'UniPi LMS') + DASHBOARD_TITLE_SUFFIX;
                })
                .catch(function() {
                    wrap.classList.remove('app-content-loading');
                    window.location.href = href;
                });
        }, true);

        // Prefetch on hover (course and semester links)
        document.addEventListener('mouseenter', function(e) {
            var a = e.target.closest('a[data-prefetch], a[href*="set_semester"], a[href*="/course/"]');
            if (!a) return;
            var href = a.getAttribute('href');
            if (!href || href.charAt(0) === '#' || prefetched[href]) return;
            prefetched[href] = true;
            var link = document.createElement('link');
            link.rel = 'prefetch';
            link.href = href;
            document.head.appendChild(link);
        }, true);

        // Navbar shadow on scroll
        var nav = document.querySelector('.navbar');
        if (nav) {
            var ticking = false;
            window.addEventListener('scroll', function() {
                if (!ticking) {
                    requestAnimationFrame(function() {
                        nav.classList.toggle('scrolled', window.scrollY > 8);
                        ticking = false;
                    });
                    ticking = true;
                }
            }, { passive: true });
        }

        // Auto-dismiss alerts after 5s
        document.querySelectorAll('.alert-dismissible').forEach(function(el) {
        setTimeout(function() {
            el.style.transition = 'opacity .35s ease, transform .35s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateY(-8px)';
            setTimeout(function() {
                var bsAlert = bootstrap.Alert.getOrCreateInstance(el);
                bsAlert.close();
            }, 350);
        }, 5000);
        });

        // File size validation (max 16MB)
        document.querySelectorAll('input[type="file"]').forEach(function(input) {
            input.addEventListener('change', function(e) {
                var file = e.target.files[0];
                if (file && file.size > 16 * 1024 * 1024) {
                    alert('Το αρχείο είναι πολύ μεγάλο! Μέγιστο μέγεθος: 16MB');
                    input.value = '';
                }
            });
        });
    });

    window.confirmDelete = function(message) {
        return confirm(message || 'Είστε σίγουρος/η ότι θέλετε να διαγράψετε αυτό το στοιχείο;');
    };
})();
