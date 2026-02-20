# UniPi LMS — Κανόνες και Best Practices

Αυτό το έγγραφο περιγράφει συμβάσεις, ασφάλεια και best practices για το έργο.

---

## 1. Περιβάλλον και ρυθμίσεις (Env)

- **Όλες οι ευαίσθητες ή εναλλασσόμενες ρυθμίσεις** (κλειδί συνεδρίας, DB path, port) πρέπει να διαβάζονται από μεταβλητές περιβάλλοντος· το `app` φορτώνει το `.env` μέσω `python-dotenv`.
- **Παραγωγή:** Ορίστε πάντα `SECRET_KEY` (π.χ. `python -c "import secrets; print(secrets.token_hex(32))"`), `FLASK_ENV=production`, `FLASK_DEBUG=0`. Προαιρετικά `DB_PATH` και `PORT`.
- Χρησιμοποιήστε το **`.env.example`** ως πρότυπο· αντιγράψτε σε `.env` και μην κάνετε commit το `.env`.

---

## 2. Ασφάλεια συνεδρίας (Session)

- **HttpOnly & SameSite:** Τα session cookies έχουν `SESSION_COOKIE_HTTPONLY = True` και `SESSION_COOKIE_SAMESITE = 'Lax'`.
- **Secure cookie:** Στην παραγωγή (`FLASK_ENV=production`) χρησιμοποιείται `SESSION_COOKIE_SECURE = True` (HTTPS only).
- **Διάρκεια:** Μετά την επιτυχή σύνδεση ορίζεται `session.permanent = True` ώστε να ισχύει το `PERMANENT_SESSION_LIFETIME` (π.χ. 24 ώρες).

---

## 3. Security headers

Όλες οι απαντήσεις περνούν από `@app.after_request` και παίρνουν:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

---

## 4. Error handlers

- **403:** Σελίδα «Απαγορεύεται η πρόσβαση» (`errors/403.html`). Για AJAX: JSON `{ "error": "Forbidden" }`.
- **404:** Σελίδα «Δεν βρέθηκε» (`errors/404.html`). Για AJAX: JSON `{ "error": "Not found" }`.
- **500:** Σελίδα «Σφάλμα διακομιστή» (`errors/500.html`). Σε production **δεν** επιστρέφονται stack traces ή ευαίσθητα δεδομένα· σε DEBUG το σφάλμα ξανα-πετιέται για ανάπτυξη.

---

## 5. Brand & UI (εικονίδια, κουμπιά)

- **Χρώμα brand:** `#8B2332` (κόκκινο). Ορίζεται στο `style.css` ως `--brand-icon`, `--brand-icon-border`, `--brand-icon-bg`.
- **Εικονίδια:** `.metric-icon` (dashboard κάρτες), `.card-header-icon` (κεφαλίδες κάρτων), `.icon-box-brand` (γενική χρήση): λευκό φόντο, κόκκινο εικονίδιο, κόκκινο περίγραμμα.
- **Κουμπιά:** `.btn-primary` = κόκκινο φόντο, λευκό κείμενο· `.btn-outline-primary` = διαφανές, κόκκινο κείμενο/περίγραμμα, στο hover γεμίζει κόκκινο με λευκό κείμενο. Τα semantic (success, danger, warning) παραμένουν ως έχουν.

---

## 6. SEO

- **Τίτλος:** Κάθε σελίδα ορίζει `{% block title %}` στο `base.html` (π.χ. «Πίνακας Ελέγχου», «Σύνδεση»).
- **Περιγραφή:** Default `meta name="description"` στο `base.html`· οι σελίδες μπορούν να κάνουν override το `{% block meta_description %}`.
- **Robots / Canonical:** Προαιρετικά `{% block meta_robots %}` και `{% block canonical %}` όπου χρειάζεται.
- **Open Graph:** Default `og:title`, `og:description`, `og:type`, `og:url`· override μέσω `{% block og_meta %}` ή `og_title` / `og_description` αν χρειάζεται σελίδα-ειδική τιμή.

---

## 7. Κώδικας και συμβάσεις

- Χρήση **Jinja templates** με επαναχρησιμοποιήσιμα blocks· στατιστικά (π.χ. sidebar) να περνούν από context (inject) αντί για πολλές queries ανά request όπου είναι εφικτό.
- **DB:** Πρόσβαση στη βάση μέσω helpers που χρησιμοποιούν το `DB_PATH` από config· καμία σκληρή διαδρομή σε production χωρίς env.
- **CSRF:** Αν προστεθούν φόρμες που αλλάζουν κατάσταση (π.χ. POST) εκτός από login/register, να εξεταστεί προστασία CSRF (π.χ. Flask-WTF).

---

## 8. Τι να μην γίνεται

- Μην τοποθετείτε μυστικά (SECRET_KEY, κωδικοί DB) μέσα στον κώδικα ή σε committed αρχεία.
- Μην επιστρέφετε stack traces ή εσωτερικά μηνύματα σφαλμάτων στο client σε production.
- Μην απενεργοποιείτε τα security headers για ολόκληρο το site χωρίς αιτιολόγηση.

---

## 9. Production & SEO checklist

Πριν το deploy, βεβαιωθείτε:

- **`.env`** από `.env.example`, με **SECRET_KEY** (π.χ. `python -c "import secrets; print(secrets.token_hex(32))"`), **FLASK_ENV=production**, **FLASK_DEBUG=0**.
- **HTTPS** στο production (απαιτείται για SESSION_COOKIE_SECURE).
- **SEO:** Κάθε σελίδα έχει μοναδικό `title`, default `meta description` και Open Graph (og:title, og:description, og:url, og:image). Σελίδες σφάλματος (403, 404, 500) έχουν `noindex, nofollow`.
- **Ασφάλεια:** Security headers, session HttpOnly/SameSite/Secure, 500 χωρίς stack trace στο client.

---

*Τελευταία ενημέρωση: production checklist, SEO (og:image, theme-color, noindex σε errors).*
