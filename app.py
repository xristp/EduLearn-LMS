"""
Σύστημα Διαχείρισης Μάθησης (LMS)
Πανεπιστήμιο Πειραιώς - Τμήμα Πληροφορικής
Ακαδημαϊκό Έτος 2025-2026

Φοιτητής: Χρήστος Πολυπαθέλης (π24251)
Μάθημα: Λογισμικό Διαχείρισης Μάθησης

Τεχνολογίες: Python Flask, SQLite, HTML, CSS, Bootstrap 5, JavaScript
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass  # run without .env file; use system env or defaults

from flask import (
    Flask, render_template, request, redirect, url_for, jsonify,
    session, flash, send_from_directory, g
)
import sqlite3
import os
import json
from calendar import monthrange
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

# Greek month names for calendar (index 0 unused, 1–12 = Jan–Dec)
_CAL_MONTHS_EL = ('', 'Ιανουάριος', 'Φεβρουάριος', 'Μάρτιος', 'Απρίλιος', 'Μάιος', 'Ιούνιος',
                  'Ιούλιος', 'Αύγουστος', 'Σεπτέμβριος', 'Οκτώβριος', 'Νοέμβριος', 'Δεκέμβριος')

# --- Αρχικοποίηση εφαρμογής ---

app = Flask(__name__)
# Config: prefer environment variables (best practice for secrets and environments)
app.secret_key = os.environ.get('SECRET_KEY') or os.environ.get('FLASK_SECRET_KEY') or 'lms_unipi_2025_dev_fallback'
app.config['ENV'] = os.environ.get('FLASK_ENV', 'development')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
# Session security (best practices)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SECURE'] = True

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'zip'}

# Δημιουργία φακέλου uploads αν δεν υπάρχει
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_PATH = os.environ.get('DATABASE_URL') or os.environ.get('DB_PATH') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lms.db')


# Βοηθητικές συναρτήσεις για τη βάση δεδομένων

def get_db():
    """Σύνδεση με τη βάση δεδομένων SQLite"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def allowed_file(filename):
    """Έλεγχος αν η επέκταση αρχείου επιτρέπεται"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Decorators - ελεγχος προσβασης

def login_required(f):
    """Decorator: Απαιτεί ο χρήστης να είναι συνδεδεμένος"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Παρακαλώ συνδεθείτε πρώτα.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def instructor_required(f):
    """Decorator: Απαιτεί ο χρήστης να είναι εκπαιδευτής"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Παρακαλώ συνδεθείτε πρώτα.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'instructor':
            flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# Context processor - user data σε ολα τα templates

@app.context_processor
def inject_user():
    """Εισαγωγή δεδομένων χρήστη σε όλα τα templates"""
    if 'user_id' in session:
        return {
            'current_user': {
                'id': session['user_id'],
                'username': session.get('username', ''),
                'full_name': session.get('full_name', ''),
                'role': session.get('role', ''),
            }
        }
    return {'current_user': None}


@app.context_processor
def inject_sidebar_courses():
    """Λίστα μαθημάτων για το sidebar (φιλτραρισμένα ανά εξάμηνο). Μία query, filter και semesters στο Python."""
    if 'user_id' not in session:
        return {'sidebar_courses': [], 'current_course_id_nav': None, 'sidebar_semesters': [], 'current_semester_filter': None}
    db = get_db()
    role = session.get('role')
    sem_filter = session.get('semester_filter')
    if role == 'instructor':
        rows = db.execute('SELECT id, name, semester FROM courses WHERE instructor_id = ? ORDER BY name', (session['user_id'],)).fetchall()
    else:
        rows = db.execute('''SELECT c.id, c.name, c.semester FROM courses c
               JOIN enrollments e ON c.id = e.course_id WHERE e.student_id = ? ORDER BY c.name''', (session['user_id'],)).fetchall()
    db.close()
    all_courses = [dict(r) for r in rows]
    if sem_filter:
        courses = [c for c in all_courses if c.get('semester') == sem_filter or not c.get('semester')]
    else:
        courses = all_courses
    semesters = sorted({c.get('semester') for c in all_courses if c.get('semester')}, reverse=True)
    current_course_id_nav = getattr(g, 'current_course_id', None)
    return {'sidebar_courses': courses, 'current_course_id_nav': current_course_id_nav,
            'sidebar_semesters': semesters, 'current_semester_filter': sem_filter}


# Αρχικοποιηση βασης δεδομενων - δημιουργια tables και demo data

def init_db():
    """Δημιουργία πινάκων και εισαγωγή αρχικών δεδομένων"""
    db = get_db()

    # Δημιουργία πινάκων
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL CHECK(role IN ('instructor', 'student')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            instructor_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (instructor_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            UNIQUE(course_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            file_path TEXT,
            material_type TEXT DEFAULT 'document',
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (author_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            max_grade REAL DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );

        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            file_path TEXT,
            comment TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            grade REAL,
            feedback TEXT,
            graded_at TIMESTAMP,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            UNIQUE(assignment_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            duration_minutes INTEGER DEFAULT 30,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );

        CREATE TABLE IF NOT EXISTS test_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            question_type TEXT NOT NULL CHECK(question_type IN ('multiple_choice', 'true_false', 'short_answer')),
            options TEXT,
            correct_answer TEXT NOT NULL,
            points REAL DEFAULT 1,
            FOREIGN KEY (test_id) REFERENCES tests(id)
        );

        CREATE TABLE IF NOT EXISTS test_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            score REAL,
            max_score REAL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (test_id) REFERENCES tests(id),
            FOREIGN KEY (student_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS test_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            student_answer TEXT,
            is_correct INTEGER DEFAULT 0,
            FOREIGN KEY (attempt_id) REFERENCES test_attempts(id),
            FOREIGN KEY (question_id) REFERENCES test_questions(id)
        );

        CREATE TABLE IF NOT EXISTS discussions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            author_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (author_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS discussion_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discussion_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (discussion_id) REFERENCES discussions(id),
            FOREIGN KEY (author_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            event_type TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );
    ''')

    # Migration: add semester to courses if missing
    try:
        has_semester = db.execute("SELECT COUNT(*) FROM pragma_table_info('courses') WHERE name='semester'").fetchone()[0]
        if has_semester == 0:
            db.execute("ALTER TABLE courses ADD COLUMN semester TEXT DEFAULT 'Εαρινό 2025-2026'")
            db.commit()
    except Exception:
        pass

    # Έλεγχος αν υπάρχουν ήδη δεδομένα
    existing = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if existing > 0:
        db.close()
        return

    # Εισαγωγή demo δεδομένων

    # Χρήστες
    instructor_pw = generate_password_hash('teacher123')
    student_pw = generate_password_hash('student123')

    db.execute('''INSERT INTO users (username, password, full_name, email, role)
                  VALUES (?, ?, ?, ?, ?)''',
               ('teacher', instructor_pw, 'Δρ. Νίκος Παπαδόπουλος',
                'papadopoulos@unipi.gr', 'instructor'))

    db.execute('''INSERT INTO users (username, password, full_name, email, role)
                  VALUES (?, ?, ?, ?, ?)''',
               ('maria', student_pw, 'Μαρία Καραγιάννη',
                'maria.k@students.unipi.gr', 'student'))

    db.execute('''INSERT INTO users (username, password, full_name, email, role)
                  VALUES (?, ?, ?, ?, ?)''',
               ('giorgos', student_pw, 'Γιώργος Αντωνίου',
                'giorgos.a@students.unipi.gr', 'student'))

    db.execute('''INSERT INTO users (username, password, full_name, email, role)
                  VALUES (?, ?, ?, ?, ?)''',
               ('eleni', student_pw, 'Ελένη Μιχαλοπούλου',
                'eleni.m@students.unipi.gr', 'student'))

    # Μάθημα
    db.execute('''INSERT INTO courses (name, description, instructor_id, semester)
                  VALUES (?, ?, ?, ?)''',
               ('Εισαγωγή στην Πληροφορική',
                'Βασικές αρχές πληροφορικής, αλγόριθμοι, δομές δεδομένων και προγραμματισμός σε Python. '
                'Το μάθημα απευθύνεται σε φοιτητές πρώτου έτους.',
                1, 'Εαρινό 2025-2026'))

    # Εγγραφές φοιτητών στο μάθημα
    db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (1, 2)')
    db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (1, 3)')
    db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (1, 4)')

    # Δεύτερο μάθημα (διαφορετικό εξάμηνο) για δοκιμή φίλτρου
    db.execute('''INSERT INTO courses (name, description, instructor_id, semester)
                  VALUES (?, ?, ?, ?)''',
               ('Δομές Δεδομένων',
                'Δέντρα, γράφοι, στοίβες και ουρές. Αναλυτική και πειραματική ανάλυση αλγορίθμων.',
                1, 'Χειμερινό 2024-2025'))
    db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (2, 2)')
    db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (2, 3)')

    # Demo: Δομές Δεδομένων (course 2) – υλικό και ανακοινώσεις
    materials_c2 = [
        (2, 'Δέντρα Δυαδικής Αναζήτησης', 'BST: εισαγωγή, διάσχιση, διαγραφή', None, 'document', None),
        (2, 'Γράφοι – Βασικές Έννοιες', 'Πίνακας γειτνίασης, λίστα γειτνίασης, BFS/DFS', None, 'presentation', None),
        (2, 'Στοίβες και Ουρές', 'Υλοποίηση με λίστες, εφαρμογές', None, 'document', None),
    ]
    for m in materials_c2:
        db.execute('''INSERT INTO materials (course_id, title, description, file_path, material_type, url)
                      VALUES (?, ?, ?, ?, ?, ?)''', m)
    db.execute('''INSERT INTO announcements (course_id, title, content, author_id, created_at)
                  VALUES (?, ?, ?, ?, ?)''',
               (2, 'Καλωσορίσατε στο μάθημα Δομές Δεδομένων',
                'Αγαπητοί φοιτητές,\n\nΤο μάθημα ασχολείται με δέντρα, γράφους και δομές. '
                'Τα μαθήματα γίνονται κάθε Τετάρτη 14:00–16:00 στην αίθουσα Β205.\n\nΔρ. Παπαδόπουλος',
                1, '2026-02-10 09:00:00'))
    db.execute('''INSERT INTO announcements (course_id, title, content, author_id, created_at)
                  VALUES (?, ?, ?, ?, ?)''',
               (2, 'Εργασία 1 – Δέντρα',
                'Η πρώτη εργασία αφορά υλοποίηση δέντρων BST. Προθεσμία υποβολής: 15 Απριλίου 2026. '
                'Δείτε λεπτομέρειες στην ενότητα Εργασίες.',
                1, '2026-02-19 11:00:00'))
    db.execute('''INSERT INTO assignments (course_id, title, description, due_date, max_grade)
                  VALUES (?, ?, ?, ?, ?)''',
               (2, 'Εργασία 1: Δέντρα BST',
                'Υλοποιήστε δέντρο δυαδικής αναζήτησης με λειτουργίες εισαγωγής, αναζήτησης και διάσχισης.',
                '2026-04-15', 100))

    # Εκπαιδευτικό υλικό
    materials_data = [
        (1, 'Εισαγωγή στους Αλγορίθμους', 'Βασικές έννοιες αλγορίθμων και ψευδοκώδικα', None, 'document', None),
        (1, 'Βίντεο: Τι είναι η Πληροφορική;', 'Εισαγωγικό βίντεο για τον κλάδο της Πληροφορικής', None, 'video', 'https://www.youtube.com/watch?v=example'),
        (1, 'Python - Πρώτα Βήματα', 'Εγκατάσταση Python και πρώτο πρόγραμμα', None, 'document', None),
        (1, 'Δομές Δεδομένων - Παρουσίαση', 'Λίστες, πλειάδες, λεξικά στην Python', None, 'presentation', None),
    ]
    for m in materials_data:
        db.execute('''INSERT INTO materials (course_id, title, description, file_path, material_type, url)
                      VALUES (?, ?, ?, ?, ?, ?)''', m)

    # Ανακοινώσεις
    db.execute('''INSERT INTO announcements (course_id, title, content, author_id, created_at)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Καλωσορίσατε στο μάθημα!',
                'Αγαπητοί φοιτητές,\n\nΚαλωσορίσατε στο μάθημα "Εισαγωγή στην Πληροφορική". '
                'Τα μαθήματα ξεκινούν την Δευτέρα 3 Μαρτίου 2026 στην αίθουσα Α102.\n\n'
                'Καλή αρχή!\nΔρ. Παπαδόπουλος',
                1, '2026-02-15 10:00:00'))

    db.execute('''INSERT INTO announcements (course_id, title, content, author_id, created_at)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Ανάρτηση 1ης Εργασίας',
                'Η πρώτη εργασία έχει αναρτηθεί. Η προθεσμία υποβολής είναι στις 30 Μαρτίου 2026. '
                'Παρακαλώ ελέγξτε τις λεπτομέρειες στην ενότητα Εργασίες.',
                1, '2026-02-18 14:30:00'))

    # Εργασίες
    db.execute('''INSERT INTO assignments (course_id, title, description, due_date, max_grade)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Εργασία 0: Εγγραφή', 'Εγγραφή στην πλατφόρμα και γνωριμία με το μάθημα.', '2026-02-28', 10))
    db.execute('''INSERT INTO assignments (course_id, title, description, due_date, max_grade)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Εργασία 1: Αλγόριθμοι',
                'Γράψτε ψευδοκώδικα για τους παρακάτω αλγορίθμους:\n'
                '1. Εύρεση μέγιστου στοιχείου πίνακα\n'
                '2. Ταξινόμηση φυσαλίδας (Bubble Sort)\n'
                '3. Δυαδική αναζήτηση\n\n'
                'Η εργασία πρέπει να παραδοθεί σε μορφή PDF.',
                '2026-03-30', 100))

    db.execute('''INSERT INTO assignments (course_id, title, description, due_date, max_grade)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Εργασία 2: Προγραμματισμός Python',
                'Υλοποιήστε τα παρακάτω προγράμματα σε Python:\n'
                '1. Πρόγραμμα υπολογισμού παραγοντικού\n'
                '2. Πρόγραμμα εύρεσης πρώτων αριθμών\n'
                '3. Πρόγραμμα διαχείρισης λίστας επαφών\n\n'
                'Η εργασία πρέπει να παραδοθεί σε αρχείο .py ή .zip',
                '2026-04-15', 100))

    # Υποβολές εργασιών (demo)
    db.execute('''INSERT INTO assignment_submissions (assignment_id, student_id, comment, submitted_at, grade, feedback, graded_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?)''',
               (1, 2, 'Η εργασία μου για τους αλγορίθμους.', '2026-03-25 18:00:00',
                85, 'Πολύ καλή δουλειά! Μικρό λάθος στον ψευδοκώδικα της δυαδικής αναζήτησης.', '2026-03-28 10:00:00'))

    db.execute('''INSERT INTO assignment_submissions (assignment_id, student_id, comment, submitted_at, grade, feedback, graded_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?)''',
               (1, 3, 'Παραδίδω την εργασία 1.', '2026-03-28 22:00:00',
                72, 'Σωστή λογική αλλά ελλιπής τεκμηρίωση. Προσπάθησε να προσθέσεις σχόλια.', '2026-03-30 09:00:00'))

    db.execute('''INSERT INTO assignment_submissions (assignment_id, student_id, comment, submitted_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 4, 'Εργασία 1 - Ελένη Μιχαλοπούλου', '2026-03-29 15:00:00'))

    # Τεστ αξιολόγησης
    db.execute('''INSERT INTO tests (course_id, title, description, duration_minutes)
                  VALUES (?, ?, ?, ?)''',
               (1, 'Τεστ 1: Βασικές Έννοιες Πληροφορικής',
                'Τεστ αυτοαξιολόγησης στις βασικές έννοιες της πληροφορικής. '
                'Περιλαμβάνει ερωτήσεις πολλαπλής επιλογής, σωστό/λάθος και σύντομης απάντησης.',
                20))

    # Ερωτήσεις τεστ - Πολλαπλής Επιλογής
    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Ποια είναι η βασική μονάδα μέτρησης πληροφορίας;',
                'multiple_choice',
                json.dumps(['Byte', 'Bit', 'Kilobyte', 'Megabyte'], ensure_ascii=False),
                'Bit', 2))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Ποια γλώσσα προγραμματισμού χρησιμοποιείται ευρέως στην ανάλυση δεδομένων;',
                'multiple_choice',
                json.dumps(['Java', 'C++', 'Python', 'Assembly'], ensure_ascii=False),
                'Python', 2))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Τι σημαίνει η συντομογραφία CPU;',
                'multiple_choice',
                json.dumps(['Central Processing Unit', 'Computer Personal Unit', 'Central Program Utility', 'Core Processing Unit'], ensure_ascii=False),
                'Central Processing Unit', 2))

    # Ερωτήσεις Σωστού/Λάθους
    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Η RAM είναι μόνιμη μνήμη αποθήκευσης.',
                'true_false',
                json.dumps(['Σωστό', 'Λάθος'], ensure_ascii=False),
                'Λάθος', 2))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Ένα byte αποτελείται από 8 bits.',
                'true_false',
                json.dumps(['Σωστό', 'Λάθος'], ensure_ascii=False),
                'Σωστό', 2))

    # Ερωτήσεις Σύντομης Απάντησης
    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Πώς ονομάζεται η διαδικασία μετατροπής πηγαίου κώδικα σε εκτελέσιμο αρχείο;',
                'short_answer', None, 'μεταγλώττιση', 2))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (1, 'Ποιο λειτουργικό σύστημα ανοιχτού κώδικα βασίζεται στο UNIX;',
                'short_answer', None, 'linux', 2))

    # Δεύτερο τεστ
    db.execute('''INSERT INTO tests (course_id, title, description, duration_minutes)
                  VALUES (?, ?, ?, ?)''',
               (1, 'Τεστ 2: Αλγόριθμοι & Δομές Δεδομένων',
                'Τεστ αξιολόγησης στους αλγορίθμους ταξινόμησης και τις βασικές δομές δεδομένων.',
                25))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (2, 'Ποιος αλγόριθμος ταξινόμησης έχει πολυπλοκότητα O(n log n) στη μέση περίπτωση;',
                'multiple_choice',
                json.dumps(['Bubble Sort', 'Quick Sort', 'Selection Sort', 'Insertion Sort'], ensure_ascii=False),
                'Quick Sort', 3))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (2, 'Η στοίβα (stack) ακολουθεί τη λογική FIFO.',
                'true_false',
                json.dumps(['Σωστό', 'Λάθος'], ensure_ascii=False),
                'Λάθος', 3))

    db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (2, 'Ποια δομή δεδομένων χρησιμοποιεί κόμβους και δείκτες;',
                'short_answer', None, 'συνδεδεμένη λίστα', 3))

    # Απόπειρες τεστ (demo - φοιτητές έχουν δώσει τεστ)
    db.execute('''INSERT INTO test_attempts (test_id, student_id, score, max_score, completed_at)
                  VALUES (?, ?, ?, ?, ?)''', (1, 2, 12, 14, '2026-03-10 11:30:00'))

    db.execute('''INSERT INTO test_attempts (test_id, student_id, score, max_score, completed_at)
                  VALUES (?, ?, ?, ?, ?)''', (1, 3, 8, 14, '2026-03-10 12:00:00'))

    # Απαντήσεις τεστ για Μαρία (attempt 1)
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 1, ?, 1)', ('Bit',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 2, ?, 1)', ('Python',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 3, ?, 1)', ('Central Processing Unit',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 4, ?, 1)', ('Λάθος',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 5, ?, 1)', ('Σωστό',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 6, ?, 1)', ('μεταγλώττιση',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (1, 7, ?, 0)', ('windows',))

    # Απαντήσεις τεστ για Γιώργο (attempt 2)
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 1, ?, 0)', ('Byte',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 2, ?, 1)', ('Python',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 3, ?, 1)', ('Central Processing Unit',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 4, ?, 0)', ('Σωστό',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 5, ?, 1)', ('Σωστό',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 6, ?, 0)', ('compilation',))
    db.execute('INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct) VALUES (2, 7, ?, 1)', ('linux',))

    # Συζητήσεις (Forum)
    db.execute('''INSERT INTO discussions (course_id, title, author_id, created_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 'Απορίες για την Εργασία 1', 3, '2026-03-20 16:00:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 3, 'Καθηγητά, στο ερώτημα 2 της εργασίας πρέπει να χρησιμοποιήσουμε '
                'συγκεκριμένη μορφή ψευδοκώδικα ή μπορούμε να γράψουμε σε ελεύθερη μορφή;',
                '2026-03-20 16:00:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 1, 'Γιώργο, μπορείτε να χρησιμοποιήσετε ελεύθερη μορφή ψευδοκώδικα, '
                'αρκεί να είναι κατανοητή η λογική του αλγορίθμου σας. '
                'Φροντίστε να υπάρχουν σχόλια για κάθε βήμα.',
                '2026-03-20 18:30:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 2, 'Ευχαριστώ καθηγητά! Πολύ κατατοπιστικό. '
                'Θα ήθελα κι εγώ να ρωτήσω: πρέπει να συμπεριλάβουμε flowchart ή μόνο ψευδοκώδικα;',
                '2026-03-21 09:00:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 1, 'Μαρία, το flowchart δεν είναι υποχρεωτικό αλλά θα εκτιμηθεί θετικά ως bonus!',
                '2026-03-21 10:15:00'))

    # Δεύτερη συζήτηση
    db.execute('''INSERT INTO discussions (course_id, title, author_id, created_at)
                  VALUES (?, ?, ?, ?)''',
               (1, 'Προτάσεις για IDE Python', 2, '2026-03-15 12:00:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (2, 2, 'Ποιο IDE προτείνετε για Python; Χρησιμοποιώ VS Code αλλά θα ήθελα εναλλακτικές.',
                '2026-03-15 12:00:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (2, 4, 'Εγώ χρησιμοποιώ PyCharm, είναι εξαιρετικό για Python! Υπάρχει δωρεάν '
                'έκδοση Community.', '2026-03-15 14:00:00'))

    db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content, created_at)
                  VALUES (?, ?, ?, ?)''',
               (2, 1, 'Και τα δύο είναι πολύ καλές επιλογές. Για αρχάριους, θα πρότεινα το '
                'Thonny ή το IDLE που έρχεται μαζί με την Python.',
                '2026-03-15 17:00:00'))

    # Συμβάντα / Ημερολόγιο
    db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Προεπισκόπηση εξαμήνου', 'Διάλεξη προεπισκόπησης',
                '2026-02-25', 'lecture'))
    db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Έναρξη Μαθημάτων', 'Πρώτη διάλεξη εισαγωγή στο μάθημα',
                '2026-03-03', 'lecture'))

    db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Προθεσμία Εργασίας 1', 'Τελευταία ημέρα υποβολής Εργασίας 1',
                '2026-03-30', 'deadline'))

    db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Τεστ Αξιολόγησης 1', 'Online τεστ αυτοαξιολόγησης',
                '2026-03-10', 'exam'))

    db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Προθεσμία Εργασίας 2', 'Τελευταία ημέρα υποβολής Εργασίας 2',
                '2026-04-15', 'deadline'))

    db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                  VALUES (?, ?, ?, ?, ?)''',
               (1, 'Εξεταστική Περίοδος', 'Τελικές εξετάσεις μαθήματος',
                '2026-06-15', 'exam'))

    db.commit()
    db.close()
    print("Η βάση δεδομένων αρχικοποιήθηκε επιτυχώς με demo δεδομένα!")


# ---------- Routes ----------

@app.route('/')
def index():
    """Αρχική σελίδα - ανακατεύθυνση"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Σελίδα σύνδεσης"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()

        if user and check_password_hash(user['password'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash(f'Καλωσορίσατε, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Λάθος όνομα χρήστη ή κωδικός.', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Σελίδα εγγραφής νέου χρήστη"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role', 'student')

        # Validation
        if not username or not password or not full_name:
            flash('Παρακαλώ συμπληρώστε όλα τα υποχρεωτικά πεδία.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Οι κωδικοί δεν ταιριάζουν.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Ο κωδικός πρέπει να έχει τουλάχιστον 6 χαρακτήρες.', 'danger')
            return render_template('register.html')

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            flash('Το όνομα χρήστη υπάρχει ήδη.', 'danger')
            db.close()
            return render_template('register.html')

        hashed_pw = generate_password_hash(password)
        db.execute('''INSERT INTO users (username, password, full_name, email, role)
                      VALUES (?, ?, ?, ?, ?)''',
                   (username, hashed_pw, full_name, email, role))
        db.commit()
        db.close()

        flash('Η εγγραφή ολοκληρώθηκε! Μπορείτε τώρα να συνδεθείτε.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/set_semester')
@login_required
def set_semester():
    """Ορισμός φίλτρου εξαμήνου (session). AJAX: επιστρέφει JSON ώστε το client να φορτώσει partial dashboard."""
    semester = request.args.get('semester', '').strip() or None
    session['semester_filter'] = semester
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'redirect': url_for('dashboard')})
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    """Αποσύνδεση χρήστη"""
    session.clear()
    flash('Αποσυνδεθήκατε επιτυχώς.', 'info')
    return redirect(url_for('login'))


# --- Dashboard ---

def _is_partial_request():
    """True if client requested partial HTML (AJAX dashboard update)."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        and request.args.get('partial')
    )


def _ensure_calendar_demo_current_month(db, course_ids):
    """Βάζει 1 event + 1 assignment στον τρέχοντα μήνα αν δεν υπάρχει τίποτα, ώστε να φαίνονται κουκίδες."""
    if not course_ids:
        return
    today = date.today()
    y, m = today.year, today.month
    last_day = monthrange(y, m)[1]
    month_start = '{:04d}-{:02d}-01'.format(y, m)
    month_end = '{:04d}-{:02d}-{:02d}'.format(y, m, last_day)
    cid = course_ids[0]
    has_event = db.execute(
        'SELECT 1 FROM events WHERE course_id = ? AND event_date >= ? AND event_date <= ? LIMIT 1',
        (cid, month_start, month_end)
    ).fetchone()
    if not has_event:
        event_day = min(25, last_day)
        db.execute(
            '''INSERT INTO events (course_id, title, description, event_date, event_type)
               VALUES (?, ?, ?, ?, ?)''',
            (cid, 'Διάλεξη / Ενότητα', 'Δραστηριότητα μαθήματος', '{:04d}-{:02d}-{:02d}'.format(y, m, event_day), 'lecture')
        )
    has_assignment = db.execute(
        'SELECT 1 FROM assignments WHERE course_id = ? AND due_date >= ? AND due_date <= ? LIMIT 1',
        (cid, month_start, month_end)
    ).fetchone()
    if not has_assignment:
        due_day = min(28, last_day)
        db.execute(
            '''INSERT INTO assignments (course_id, title, description, due_date, max_grade)
               VALUES (?, ?, ?, ?, ?)''',
            (cid, 'Δραστηριότητα μήνα', 'Δραστηριότητα για το τρέχον μήνα.', '{:04d}-{:02d}-{:02d}'.format(y, m, due_day), 10)
        )
    db.commit()


def _dashboard_calendar_items(db, user_id, role, semester_filter=None):
    """Συλλογή γεγονότων και ληξιπρόθεσμων εργασιών για το ημερολόγιο."""
    today = date.today()
    end = today + timedelta(days=90)
    # Για το τρέχον μήνα: ξεκινάμε από την 1η ώστε να εμφανίζονται κουκίδες και για προηγούμενες μέρες
    first_of_month = date(today.year, today.month, 1)
    start_str = first_of_month.isoformat()
    end_str = end.isoformat()
    items = []

    if role == 'instructor':
        sql = 'SELECT id FROM courses WHERE instructor_id = ?'
        params = [user_id]
        if semester_filter:
            sql += ' AND (semester = ? OR semester IS NULL)'
            params.append(semester_filter)
        course_ids = [r[0] for r in db.execute(sql, params).fetchall()]
    else:
        sql = 'SELECT course_id FROM enrollments e JOIN courses c ON c.id = e.course_id WHERE e.student_id = ?'
        params = [user_id]
        if semester_filter:
            sql += ' AND (c.semester = ? OR c.semester IS NULL)'
            params.append(semester_filter)
        course_ids = [r[0] for r in db.execute(sql, params).fetchall()]

    if not course_ids:
        return [], {}, today.year, today.month, 0, 1

    _ensure_calendar_demo_current_month(db, course_ids)

    placeholders = ','.join('?' * len(course_ids))
    events = db.execute(
        '''SELECT ev.id, ev.title, ev.event_date, c.name as course_name, c.id as course_id
           FROM events ev JOIN courses c ON ev.course_id = c.id
           WHERE ev.course_id IN ({}) AND ev.event_date >= ? AND ev.event_date <= ?'''
        .format(placeholders), (*course_ids, start_str, end_str)
    ).fetchall()
    for r in events:
        items.append({
            'date': r['event_date'][:10] if r['event_date'] else None,
            'title': r['title'],
            'type': 'event',
            'course_name': r['course_name'],
            'course_id': r['course_id'],
            'url': None,
        })
    assignments = db.execute(
        '''SELECT a.id, a.title, a.due_date, c.name as course_name, c.id as course_id
           FROM assignments a JOIN courses c ON a.course_id = c.id
           WHERE a.course_id IN ({}) AND a.due_date >= ? AND a.due_date <= ?'''
        .format(placeholders), (*course_ids, start_str, end_str)
    ).fetchall()
    for r in assignments:
        items.append({
            'date': r['due_date'][:10] if r['due_date'] else None,
            'title': r['title'],
            'type': 'assignment',
            'course_name': r['course_name'],
            'course_id': r['course_id'],
            'url': None,
        })

    for it in items:
        if it['type'] == 'event':
            it['url'] = url_for('events', course_id=it['course_id'])
        else:
            it['url'] = url_for('assignments', course_id=it['course_id'])
    items.sort(key=lambda x: x.get('date') or '')

    # Calendar grid for current month
    y, m = today.year, today.month
    first = date(y, m, 1)
    days_in_month = monthrange(y, m)[1]
    first_weekday = first.weekday()  # 0 = Monday
    items_by_date = {}
    for it in items:
        d = it.get('date')
        if d:
            items_by_date.setdefault(d, []).append(it)
    calendar_days = [{'day': d, 'date_str': '{:04d}-{:02d}-{:02d}'.format(y, m, d)} for d in range(1, days_in_month + 1)]
    return items, items_by_date, y, m, days_in_month, first_weekday, calendar_days


@app.route('/dashboard')
@login_required
def dashboard():
    """Κεντρικός πίνακας ελέγχου"""
    db = get_db()

    semester_filter = session.get('semester_filter')
    if session['role'] == 'instructor':
        sql = 'SELECT * FROM courses WHERE instructor_id = ?'
        params = [session['user_id']]
        if semester_filter:
            sql += ' AND (semester = ? OR semester IS NULL)'
            params.append(semester_filter)
        sql += ' ORDER BY name'
        courses = db.execute(sql, params).fetchall()

        # Αθροιστικά στατιστικά
        total_students = 0
        total_materials = 0
        total_pending = 0
        total_submissions = 0

        stats = {}
        for course in courses:
            student_count = db.execute(
                'SELECT COUNT(*) FROM enrollments WHERE course_id = ?', (course['id'],)
            ).fetchone()[0]
            material_count = db.execute(
                'SELECT COUNT(*) FROM materials WHERE course_id = ?', (course['id'],)
            ).fetchone()[0]
            assignment_count = db.execute(
                'SELECT COUNT(*) FROM assignments WHERE course_id = ?', (course['id'],)
            ).fetchone()[0]
            pending_submissions = db.execute(
                '''SELECT COUNT(*) FROM assignment_submissions s
                   JOIN assignments a ON s.assignment_id = a.id
                   WHERE a.course_id = ? AND s.grade IS NULL''', (course['id'],)
            ).fetchone()[0]
            graded_submissions = db.execute(
                '''SELECT COUNT(*) FROM assignment_submissions s
                   JOIN assignments a ON s.assignment_id = a.id
                   WHERE a.course_id = ? AND s.grade IS NOT NULL''', (course['id'],)
            ).fetchone()[0]
            test_count = db.execute(
                'SELECT COUNT(*) FROM tests WHERE course_id = ?', (course['id'],)
            ).fetchone()[0]
            discussion_count = db.execute(
                'SELECT COUNT(*) FROM discussions WHERE course_id = ?', (course['id'],)
            ).fetchone()[0]
            avg_grade = db.execute(
                '''SELECT AVG(s.grade) FROM assignment_submissions s
                   JOIN assignments a ON s.assignment_id = a.id
                   WHERE a.course_id = ? AND s.grade IS NOT NULL''', (course['id'],)
            ).fetchone()[0]

            total_students += student_count
            total_materials += material_count
            total_pending += pending_submissions
            total_submissions += graded_submissions + pending_submissions

            stats[course['id']] = {
                'students': student_count,
                'materials': material_count,
                'assignments': assignment_count,
                'pending': pending_submissions,
                'graded': graded_submissions,
                'tests': test_count,
                'discussions': discussion_count,
                'avg_grade': round(avg_grade, 1) if avg_grade else None,
            }

        overview = {
            'total_courses': len(courses),
            'total_students': total_students,
            'total_materials': total_materials,
            'total_pending': total_pending,
            'total_submissions': total_submissions,
        }

        # Ανακοινώσεις: όταν έχει επιλεγεί εξάμηνο = μόνο από μαθήματα αυτού του εξαμήνου (overview)
        course_ids = [c['id'] for c in courses]
        if course_ids:
            placeholders = ','.join('?' * len(course_ids))
            recent_announcements = db.execute(
                '''SELECT a.*, c.name as course_name FROM announcements a
                   JOIN courses c ON a.course_id = c.id
                   WHERE a.course_id IN ({}) ORDER BY a.created_at DESC LIMIT 20'''.format(placeholders),
                course_ids
            ).fetchall()
        else:
            recent_announcements = []

        calendar_items, calendar_by_date, cal_year, cal_month, cal_days, cal_first_weekday, cal_days_list = _dashboard_calendar_items(
            db, session['user_id'], session['role'], semester_filter)
        cal_month_name = _CAL_MONTHS_EL[cal_month] if 1 <= cal_month <= 12 else ''
        db.close()
        _ctx = dict(courses=courses, stats=stats, overview=overview, announcements=recent_announcements,
                    calendar_items=calendar_items, calendar_by_date=calendar_by_date,
                    cal_year=cal_year, cal_month=cal_month, cal_month_name=cal_month_name,
                    cal_days=cal_days, cal_first_weekday=cal_first_weekday, cal_days_list=cal_days_list)
        if _is_partial_request():
            return render_template('dashboard_content.html', **_ctx)
        return render_template('dashboard.html', **_ctx)
    else:
        sql = '''SELECT c.* FROM courses c
               JOIN enrollments e ON c.id = e.course_id
               WHERE e.student_id = ?'''
        params = [session['user_id']]
        if semester_filter:
            sql += ' AND (c.semester = ? OR c.semester IS NULL)'
            params.append(semester_filter)
        sql += ' ORDER BY c.name'
        courses = db.execute(sql, params).fetchall()

        # Ανακοινώσεις από μαθήματα του τρέχοντος φίλτρου (Όλα ή συγκεκριμένο εξάμηνο)
        course_ids = [c['id'] for c in courses]
        if course_ids:
            placeholders = ','.join('?' * len(course_ids))
            recent_announcements = db.execute(
                '''SELECT a.*, c.name as course_name FROM announcements a
                   JOIN courses c ON a.course_id = c.id
                   WHERE a.course_id IN ({}) ORDER BY a.created_at DESC LIMIT 20'''.format(placeholders),
                course_ids
            ).fetchall()
        else:
            recent_announcements = []

        upcoming_events = db.execute(
            '''SELECT ev.*, c.name as course_name FROM events ev
               JOIN courses c ON ev.course_id = c.id
               JOIN enrollments e ON c.id = e.course_id
               WHERE e.student_id = ? AND ev.event_date >= date('now')
               ORDER BY ev.event_date ASC LIMIT 5''', (session['user_id'],)
        ).fetchall()

        pending_assignments = db.execute(
            '''SELECT a.*, c.name as course_name FROM assignments a
               JOIN courses c ON a.course_id = c.id
               JOIN enrollments e ON c.id = e.course_id
               WHERE e.student_id = ?
               AND a.id NOT IN (
                   SELECT assignment_id FROM assignment_submissions WHERE student_id = ?
               )
               ORDER BY a.due_date ASC''', (session['user_id'], session['user_id'])
        ).fetchall()

        # Στατιστικά φοιτητή
        total_submitted = db.execute(
            'SELECT COUNT(*) FROM assignment_submissions WHERE student_id = ?',
            (session['user_id'],)
        ).fetchone()[0]
        avg_grade = db.execute(
            '''SELECT AVG(s.grade * 100.0 / a.max_grade) FROM assignment_submissions s
               JOIN assignments a ON s.assignment_id = a.id
               WHERE s.student_id = ? AND s.grade IS NOT NULL''',
            (session['user_id'],)
        ).fetchone()[0]
        test_attempts = db.execute(
            'SELECT COUNT(*) FROM test_attempts WHERE student_id = ?',
            (session['user_id'],)
        ).fetchone()[0]
        avg_test = db.execute(
            '''SELECT AVG(score * 100.0 / max_score)
               FROM test_attempts WHERE student_id = ? AND max_score > 0''',
            (session['user_id'],)
        ).fetchone()[0]

        student_stats = {
            'enrolled_courses': len(courses),
            'pending_count': len(pending_assignments),
            'submitted_count': total_submitted,
            'avg_grade': round(avg_grade, 1) if avg_grade else None,
            'test_attempts': test_attempts,
            'avg_test': round(avg_test, 1) if avg_test else None,
            'upcoming_count': len(upcoming_events),
        }

        calendar_items, calendar_by_date, cal_year, cal_month, cal_days, cal_first_weekday, cal_days_list = _dashboard_calendar_items(
            db, session['user_id'], session['role'], semester_filter)
        cal_month_name = _CAL_MONTHS_EL[cal_month] if 1 <= cal_month <= 12 else ''
        db.close()
        _ctx = dict(courses=courses, announcements=recent_announcements, upcoming_events=upcoming_events,
                    pending_assignments=pending_assignments, student_stats=student_stats,
                    calendar_items=calendar_items, calendar_by_date=calendar_by_date,
                    cal_year=cal_year, cal_month=cal_month, cal_month_name=cal_month_name,
                    cal_days=cal_days, cal_first_weekday=cal_first_weekday, cal_days_list=cal_days_list)
        if _is_partial_request():
            return render_template('dashboard_content.html', **_ctx)
        return render_template('dashboard.html', **_ctx)


# --- Εκπαιδευτικο υλικο ---

@app.route('/course/<int:course_id>/materials')
@login_required
def materials(course_id):
    """Προβολή εκπαιδευτικού υλικού"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    materials_list = db.execute(
        'SELECT * FROM materials WHERE course_id = ? ORDER BY created_at DESC', (course_id,)
    ).fetchall()
    db.close()
    return render_template('materials.html', course=course, materials=materials_list)


@app.route('/course/<int:course_id>/materials/upload', methods=['GET', 'POST'])
@instructor_required
def upload_material(course_id):
    """Ανάρτηση εκπαιδευτικού υλικού"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        material_type = request.form.get('material_type', 'document')
        url = request.form.get('url', '').strip()
        file_path = None

        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Προσθήκη timestamp για αποφυγή συγκρούσεων
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                file_path = filename

        db.execute('''INSERT INTO materials (course_id, title, description, file_path, material_type, url)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (course_id, title, description, file_path, material_type, url or None))
        db.commit()
        db.close()
        flash('Το υλικό αναρτήθηκε επιτυχώς!', 'success')
        return redirect(url_for('materials', course_id=course_id))

    db.close()
    return render_template('upload_material.html', course=course)


@app.route('/download/<filename>')
@login_required
def download_file(filename):
    """Λήψη αρχείου"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# Ανακοινωσεις

@app.route('/course/<int:course_id>/announcements')
@login_required
def announcements(course_id):
    """Προβολή ανακοινώσεων"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    announcements_list = db.execute(
        '''SELECT a.*, u.full_name as author_name FROM announcements a
           JOIN users u ON a.author_id = u.id
           WHERE a.course_id = ?
           ORDER BY a.created_at DESC''', (course_id,)
    ).fetchall()
    db.close()
    return render_template('announcements.html', course=course, announcements=announcements_list)


@app.route('/course/<int:course_id>/announcements/create', methods=['GET', 'POST'])
@instructor_required
def create_announcement(course_id):
    """Δημιουργία ανακοίνωσης"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()

        if title and content:
            db.execute('''INSERT INTO announcements (course_id, title, content, author_id)
                          VALUES (?, ?, ?, ?)''',
                       (course_id, title, content, session['user_id']))
            db.commit()
            flash('Η ανακοίνωση δημοσιεύτηκε!', 'success')
            db.close()
            return redirect(url_for('announcements', course_id=course_id))
        else:
            flash('Παρακαλώ συμπληρώστε τίτλο και περιεχόμενο.', 'danger')

    db.close()
    return render_template('create_announcement.html', course=course)


# Εργασιες

@app.route('/course/<int:course_id>/assignments')
@login_required
def assignments(course_id):
    """Προβολή εργασιών"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    assignments_list = db.execute(
        'SELECT * FROM assignments WHERE course_id = ? ORDER BY due_date ASC', (course_id,)
    ).fetchall()

    # Αν είναι φοιτητής, φέρε και τις υποβολές του
    submissions = {}
    if session['role'] == 'student':
        subs = db.execute(
            '''SELECT * FROM assignment_submissions
               WHERE student_id = ? AND assignment_id IN (
                   SELECT id FROM assignments WHERE course_id = ?
               )''', (session['user_id'], course_id)
        ).fetchall()
        for s in subs:
            submissions[s['assignment_id']] = s

    # Αν είναι εκπαιδευτής, φέρε τις υποβολές για κάθε εργασία
    all_submissions = {}
    if session['role'] == 'instructor':
        for a in assignments_list:
            subs = db.execute(
                '''SELECT s.*, u.full_name as student_name FROM assignment_submissions s
                   JOIN users u ON s.student_id = u.id
                   WHERE s.assignment_id = ?
                   ORDER BY s.submitted_at DESC''', (a['id'],)
            ).fetchall()
            all_submissions[a['id']] = subs

    db.close()
    return render_template('assignments.html', course=course,
                           assignments=assignments_list, submissions=submissions,
                           all_submissions=all_submissions)


@app.route('/course/<int:course_id>/assignments/create', methods=['GET', 'POST'])
@instructor_required
def create_assignment(course_id):
    """Δημιουργία εργασίας"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        due_date = request.form.get('due_date', '').strip()
        max_grade = request.form.get('max_grade', 100)

        if title:
            db.execute('''INSERT INTO assignments (course_id, title, description, due_date, max_grade)
                          VALUES (?, ?, ?, ?, ?)''',
                       (course_id, title, description, due_date or None, max_grade))
            db.commit()
            flash('Η εργασία δημιουργήθηκε!', 'success')
            db.close()
            return redirect(url_for('assignments', course_id=course_id))

    db.close()
    return render_template('create_assignment.html', course=course)


@app.route('/assignment/<int:assignment_id>/submit', methods=['GET', 'POST'])
@login_required
def submit_assignment(assignment_id):
    """Υποβολή εργασίας από φοιτητή"""
    db = get_db()
    assignment = db.execute(
        '''SELECT a.*, c.name as course_name FROM assignments a
           JOIN courses c ON a.course_id = c.id
           WHERE a.id = ?''', (assignment_id,)
    ).fetchone()

    if not assignment:
        flash('Η εργασία δεν βρέθηκε.', 'danger')
        db.close()
        return redirect(url_for('dashboard'))

    # Έλεγχος αν υπάρχει ήδη υποβολή
    existing = db.execute(
        'SELECT * FROM assignment_submissions WHERE assignment_id = ? AND student_id = ?',
        (assignment_id, session['user_id'])
    ).fetchone()

    if existing:
        flash('Έχετε ήδη υποβάλει αυτή την εργασία.', 'warning')
        db.close()
        return redirect(url_for('assignments', course_id=assignment['course_id']))

    if request.method == 'POST':
        comment = request.form.get('comment', '').strip()
        file_path = None

        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = f"sub_{session['user_id']}_{timestamp}{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                file_path = filename

        db.execute('''INSERT INTO assignment_submissions (assignment_id, student_id, file_path, comment)
                      VALUES (?, ?, ?, ?)''',
                   (assignment_id, session['user_id'], file_path, comment))
        db.commit()
        flash('Η εργασία υποβλήθηκε επιτυχώς!', 'success')
        db.close()
        return redirect(url_for('assignments', course_id=assignment['course_id']))

    db.close()
    return render_template('submit_assignment.html', assignment=assignment)


@app.route('/submission/<int:submission_id>/grade', methods=['GET', 'POST'])
@instructor_required
def grade_submission(submission_id):
    """Βαθμολόγηση υποβολής εργασίας"""
    db = get_db()
    submission = db.execute(
        '''SELECT s.*, u.full_name as student_name, a.title as assignment_title,
                  a.max_grade, a.course_id
           FROM assignment_submissions s
           JOIN users u ON s.student_id = u.id
           JOIN assignments a ON s.assignment_id = a.id
           WHERE s.id = ?''', (submission_id,)
    ).fetchone()

    if not submission:
        flash('Η υποβολή δεν βρέθηκε.', 'danger')
        db.close()
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        grade = request.form.get('grade', type=float)
        feedback = request.form.get('feedback', '').strip()

        db.execute('''UPDATE assignment_submissions
                      SET grade = ?, feedback = ?, graded_at = ?
                      WHERE id = ?''',
                   (grade, feedback, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), submission_id))
        db.commit()
        flash('Η βαθμολογία καταχωρήθηκε!', 'success')
        db.close()
        return redirect(url_for('assignments', course_id=submission['course_id']))

    db.close()
    return render_template('grade_submission.html', submission=submission)


# Τεστ αξιολογησης

@app.route('/course/<int:course_id>/tests')
@login_required
def tests(course_id):
    """Προβολή διαθέσιμων τεστ"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    tests_list = db.execute(
        'SELECT * FROM tests WHERE course_id = ? ORDER BY created_at DESC', (course_id,)
    ).fetchall()

    # Αν είναι φοιτητής, φέρε τις απόπειρές του
    attempts = {}
    if session['role'] == 'student':
        for t in tests_list:
            attempt = db.execute(
                '''SELECT * FROM test_attempts
                   WHERE test_id = ? AND student_id = ?
                   ORDER BY completed_at DESC LIMIT 1''',
                (t['id'], session['user_id'])
            ).fetchone()
            if attempt:
                attempts[t['id']] = attempt

    # Αν είναι εκπαιδευτής, στατιστικά ανά τεστ
    test_stats = {}
    if session['role'] == 'instructor':
        for t in tests_list:
            total_attempts = db.execute(
                'SELECT COUNT(*) FROM test_attempts WHERE test_id = ?', (t['id'],)
            ).fetchone()[0]
            avg_score = db.execute(
                'SELECT AVG(score * 100.0 / max_score) FROM test_attempts WHERE test_id = ? AND completed_at IS NOT NULL',
                (t['id'],)
            ).fetchone()[0]
            question_count = db.execute(
                'SELECT COUNT(*) FROM test_questions WHERE test_id = ?', (t['id'],)
            ).fetchone()[0]
            test_stats[t['id']] = {
                'attempts': total_attempts,
                'avg_score': round(avg_score, 1) if avg_score else 0,
                'questions': question_count
            }

    db.close()
    return render_template('tests.html', course=course, tests=tests_list,
                           attempts=attempts, test_stats=test_stats)


@app.route('/course/<int:course_id>/tests/create', methods=['GET', 'POST'])
@instructor_required
def create_test(course_id):
    """Δημιουργία τεστ αξιολόγησης"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        duration = request.form.get('duration', 30, type=int)

        if title:
            cursor = db.execute(
                '''INSERT INTO tests (course_id, title, description, duration_minutes)
                   VALUES (?, ?, ?, ?)''',
                (course_id, title, description, duration))
            test_id = cursor.lastrowid

            # Επεξεργασία ερωτήσεων
            q_index = 1
            while True:
                q_text = request.form.get(f'question_{q_index}_text')
                if not q_text:
                    break

                q_type = request.form.get(f'question_{q_index}_type', 'multiple_choice')
                q_correct = request.form.get(f'question_{q_index}_correct', '')
                q_points = request.form.get(f'question_{q_index}_points', 1, type=float)

                options = None
                if q_type in ('multiple_choice', 'true_false'):
                    opts = []
                    o_index = 1
                    while True:
                        opt = request.form.get(f'question_{q_index}_option_{o_index}')
                        if not opt:
                            break
                        opts.append(opt)
                        o_index += 1
                    if opts:
                        options = json.dumps(opts, ensure_ascii=False)
                    elif q_type == 'true_false':
                        options = json.dumps(['Σωστό', 'Λάθος'], ensure_ascii=False)

                db.execute('''INSERT INTO test_questions (test_id, question_text, question_type, options, correct_answer, points)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (test_id, q_text, q_type, options, q_correct, q_points))
                q_index += 1

            db.commit()
            flash('Το τεστ δημιουργήθηκε επιτυχώς!', 'success')
            db.close()
            return redirect(url_for('tests', course_id=course_id))

    db.close()
    return render_template('create_test.html', course=course)


@app.route('/test/<int:test_id>/take', methods=['GET', 'POST'])
@login_required
def take_test(test_id):
    """Εκτέλεση τεστ από φοιτητή"""
    if session['role'] != 'student':
        flash('Μόνο φοιτητές μπορούν να δώσουν τεστ.', 'warning')
        return redirect(url_for('dashboard'))

    db = get_db()
    test = db.execute(
        '''SELECT t.*, c.name as course_name FROM tests t
           JOIN courses c ON t.course_id = c.id
           WHERE t.id = ?''', (test_id,)
    ).fetchone()

    if not test:
        flash('Το τεστ δεν βρέθηκε.', 'danger')
        db.close()
        return redirect(url_for('dashboard'))

    # Έλεγχος αν έχει ήδη δώσει
    existing_attempt = db.execute(
        'SELECT * FROM test_attempts WHERE test_id = ? AND student_id = ? AND completed_at IS NOT NULL',
        (test_id, session['user_id'])
    ).fetchone()

    if existing_attempt:
        flash('Έχετε ήδη ολοκληρώσει αυτό το τεστ.', 'warning')
        db.close()
        return redirect(url_for('test_result', attempt_id=existing_attempt['id']))

    questions = db.execute(
        'SELECT * FROM test_questions WHERE test_id = ? ORDER BY id', (test_id,)
    ).fetchall()

    if request.method == 'POST':
        # Δημιουργία attempt
        cursor = db.execute(
            'INSERT INTO test_attempts (test_id, student_id, max_score) VALUES (?, ?, ?)',
            (test_id, session['user_id'],
             sum(q['points'] for q in questions)))
        attempt_id = cursor.lastrowid

        total_score = 0
        max_score = 0

        for q in questions:
            student_answer = request.form.get(f'answer_{q["id"]}', '').strip()
            correct = q['correct_answer'].strip().lower()
            given = student_answer.strip().lower()
            is_correct = 1 if given == correct else 0

            if is_correct:
                total_score += q['points']
            max_score += q['points']

            db.execute('''INSERT INTO test_answers (attempt_id, question_id, student_answer, is_correct)
                          VALUES (?, ?, ?, ?)''',
                       (attempt_id, q['id'], student_answer, is_correct))

        # Ενημέρωση βαθμολογίας
        db.execute('''UPDATE test_attempts
                      SET score = ?, max_score = ?, completed_at = ?
                      WHERE id = ?''',
                   (total_score, max_score, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), attempt_id))

        db.commit()
        flash(f'Ολοκληρώσατε το τεστ! Βαθμός: {total_score}/{max_score}', 'success')
        db.close()
        return redirect(url_for('test_result', attempt_id=attempt_id))

    # Μετατροπή options σε λίστα
    questions_parsed = []
    for q in questions:
        q_dict = dict(q)
        if q['options']:
            q_dict['options_list'] = json.loads(q['options'])
        else:
            q_dict['options_list'] = []
        questions_parsed.append(q_dict)

    db.close()
    return render_template('take_test.html', test=test, questions=questions_parsed)


@app.route('/test/result/<int:attempt_id>')
@login_required
def test_result(attempt_id):
    """Αποτελέσματα τεστ"""
    db = get_db()
    attempt = db.execute(
        '''SELECT ta.*, t.title as test_title, t.course_id, c.name as course_name
           FROM test_attempts ta
           JOIN tests t ON ta.test_id = t.id
           JOIN courses c ON t.course_id = c.id
           WHERE ta.id = ?''', (attempt_id,)
    ).fetchone()

    if not attempt:
        flash('Τα αποτελέσματα δεν βρέθηκαν.', 'danger')
        db.close()
        return redirect(url_for('dashboard'))

    # Μόνο ο ίδιος ο φοιτητής ή ο εκπαιδευτής μπορεί να δει
    if session['role'] == 'student' and attempt['student_id'] != session['user_id']:
        flash('Δεν έχετε πρόσβαση σε αυτά τα αποτελέσματα.', 'danger')
        db.close()
        return redirect(url_for('dashboard'))

    answers = db.execute(
        '''SELECT ta.*, tq.question_text, tq.question_type, tq.options,
                  tq.correct_answer, tq.points
           FROM test_answers ta
           JOIN test_questions tq ON ta.question_id = tq.id
           WHERE ta.attempt_id = ?
           ORDER BY tq.id''', (attempt_id,)
    ).fetchall()

    # Parse options
    answers_parsed = []
    for a in answers:
        a_dict = dict(a)
        if a['options']:
            a_dict['options_list'] = json.loads(a['options'])
        answers_parsed.append(a_dict)

    db.close()
    return render_template('test_result.html', attempt=attempt, answers=answers_parsed)


# Συζητησεις (forum)

@app.route('/course/<int:course_id>/discussions')
@login_required
def discussions(course_id):
    """Προβολή συζητήσεων"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    discussions_list = db.execute(
        '''SELECT d.*, u.full_name as author_name,
                  (SELECT COUNT(*) FROM discussion_posts WHERE discussion_id = d.id) as post_count,
                  (SELECT MAX(created_at) FROM discussion_posts WHERE discussion_id = d.id) as last_post
           FROM discussions d
           JOIN users u ON d.author_id = u.id
           WHERE d.course_id = ?
           ORDER BY d.created_at DESC''', (course_id,)
    ).fetchall()
    db.close()
    return render_template('discussions.html', course=course, discussions=discussions_list)


@app.route('/discussion/<int:discussion_id>', methods=['GET', 'POST'])
@login_required
def discussion_thread(discussion_id):
    """Προβολή νήματος συζήτησης"""
    db = get_db()
    discussion = db.execute(
        '''SELECT d.*, u.full_name as author_name, c.name as course_name, c.id as course_id
           FROM discussions d
           JOIN users u ON d.author_id = u.id
           JOIN courses c ON d.course_id = c.id
           WHERE d.id = ?''', (discussion_id,)
    ).fetchone()

    if not discussion:
        flash('Η συζήτηση δεν βρέθηκε.', 'danger')
        db.close()
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content)
                          VALUES (?, ?, ?)''',
                       (discussion_id, session['user_id'], content))
            db.commit()
            flash('Η απάντησή σας δημοσιεύτηκε!', 'success')
        else:
            flash('Παρακαλώ γράψτε κάτι.', 'warning')

    posts = db.execute(
        '''SELECT p.*, u.full_name as author_name, u.role as author_role
           FROM discussion_posts p
           JOIN users u ON p.author_id = u.id
           WHERE p.discussion_id = ?
           ORDER BY p.created_at ASC''', (discussion_id,)
    ).fetchall()

    g.current_course_id = discussion['course_id']
    db.close()
    return render_template('discussion_thread.html', discussion=discussion, posts=posts)


@app.route('/course/<int:course_id>/discussions/create', methods=['GET', 'POST'])
@login_required
def create_discussion(course_id):
    """Δημιουργία νέας συζήτησης"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()

        if title and content:
            cursor = db.execute(
                '''INSERT INTO discussions (course_id, title, author_id)
                   VALUES (?, ?, ?)''',
                (course_id, title, session['user_id']))
            discussion_id = cursor.lastrowid

            db.execute('''INSERT INTO discussion_posts (discussion_id, author_id, content)
                          VALUES (?, ?, ?)''',
                       (discussion_id, session['user_id'], content))
            db.commit()
            flash('Η συζήτηση δημιουργήθηκε!', 'success')
            db.close()
            return redirect(url_for('discussions', course_id=course_id))

    db.close()
    return render_template('create_discussion.html', course=course)


# Ημερολογιο / Συμβαντα

@app.route('/course/<int:course_id>/events')
@login_required
def events(course_id):
    """Προβολή συμβάντων"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    events_list = db.execute(
        'SELECT * FROM events WHERE course_id = ? ORDER BY event_date ASC', (course_id,)
    ).fetchall()
    db.close()
    return render_template('events.html', course=course, events=events_list)


@app.route('/course/<int:course_id>/events/create', methods=['GET', 'POST'])
@instructor_required
def create_event(course_id):
    """Δημιουργία συμβάντος"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        event_date = request.form.get('event_date', '').strip()
        event_type = request.form.get('event_type', 'general')

        if title and event_date:
            db.execute('''INSERT INTO events (course_id, title, description, event_date, event_type)
                          VALUES (?, ?, ?, ?, ?)''',
                       (course_id, title, description, event_date, event_type))
            db.commit()
            flash('Το συμβάν δημιουργήθηκε!', 'success')
            db.close()
            return redirect(url_for('events', course_id=course_id))

    db.close()
    return render_template('create_event.html', course=course)


# Βαθμολογιες & προοδος

@app.route('/course/<int:course_id>/grades')
@login_required
def grades(course_id):
    """Προβολή βαθμολογιών φοιτητή"""
    if session['role'] != 'student':
        return redirect(url_for('progress', course_id=course_id))

    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    # Βαθμοί εργασιών
    assignment_grades = db.execute(
        '''SELECT a.title, a.max_grade, s.grade, s.feedback, s.submitted_at, s.graded_at
           FROM assignment_submissions s
           JOIN assignments a ON s.assignment_id = a.id
           WHERE a.course_id = ? AND s.student_id = ?
           ORDER BY s.submitted_at ASC''',
        (course_id, session['user_id'])
    ).fetchall()

    # Βαθμοί τεστ
    test_grades = db.execute(
        '''SELECT t.title, ta.score, ta.max_score, ta.completed_at
           FROM test_attempts ta
           JOIN tests t ON ta.test_id = t.id
           WHERE t.course_id = ? AND ta.student_id = ? AND ta.completed_at IS NOT NULL
           ORDER BY ta.completed_at ASC''',
        (course_id, session['user_id'])
    ).fetchall()

    db.close()
    return render_template('grades.html', course=course,
                           assignment_grades=assignment_grades, test_grades=test_grades)


@app.route('/course/<int:course_id>/progress')
@instructor_required
def progress(course_id):
    """Παρακολούθηση προόδου φοιτητών (Εκπαιδευτής)"""
    db = get_db()
    course = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()

    # Εγγεγραμμένοι φοιτητές
    students = db.execute(
        '''SELECT u.id, u.full_name, u.email FROM users u
           JOIN enrollments e ON u.id = e.student_id
           WHERE e.course_id = ?
           ORDER BY u.full_name''', (course_id,)
    ).fetchall()

    student_progress = []
    for student in students:
        # Εργασίες
        total_assignments = db.execute(
            'SELECT COUNT(*) FROM assignments WHERE course_id = ?', (course_id,)
        ).fetchone()[0]
        submitted_assignments = db.execute(
            '''SELECT COUNT(*) FROM assignment_submissions s
               JOIN assignments a ON s.assignment_id = a.id
               WHERE a.course_id = ? AND s.student_id = ?''',
            (course_id, student['id'])
        ).fetchone()[0]
        avg_assignment_grade = db.execute(
            '''SELECT AVG(s.grade) FROM assignment_submissions s
               JOIN assignments a ON s.assignment_id = a.id
               WHERE a.course_id = ? AND s.student_id = ? AND s.grade IS NOT NULL''',
            (course_id, student['id'])
        ).fetchone()[0]

        # Τεστ
        total_tests = db.execute(
            'SELECT COUNT(*) FROM tests WHERE course_id = ?', (course_id,)
        ).fetchone()[0]
        completed_tests = db.execute(
            '''SELECT COUNT(*) FROM test_attempts ta
               JOIN tests t ON ta.test_id = t.id
               WHERE t.course_id = ? AND ta.student_id = ? AND ta.completed_at IS NOT NULL''',
            (course_id, student['id'])
        ).fetchone()[0]
        avg_test_score = db.execute(
            '''SELECT AVG(ta.score * 100.0 / ta.max_score) FROM test_attempts ta
               JOIN tests t ON ta.test_id = t.id
               WHERE t.course_id = ? AND ta.student_id = ? AND ta.completed_at IS NOT NULL''',
            (course_id, student['id'])
        ).fetchone()[0]

        # Συμμετοχή σε συζητήσεις
        discussion_posts = db.execute(
            '''SELECT COUNT(*) FROM discussion_posts dp
               JOIN discussions d ON dp.discussion_id = d.id
               WHERE d.course_id = ? AND dp.author_id = ?''',
            (course_id, student['id'])
        ).fetchone()[0]

        student_progress.append({
            'student': student,
            'total_assignments': total_assignments,
            'submitted_assignments': submitted_assignments,
            'avg_assignment_grade': round(avg_assignment_grade, 1) if avg_assignment_grade else None,
            'total_tests': total_tests,
            'completed_tests': completed_tests,
            'avg_test_score': round(avg_test_score, 1) if avg_test_score else None,
            'discussion_posts': discussion_posts
        })

    db.close()
    return render_template('progress.html', course=course, student_progress=student_progress)


# Διαχειριση μαθηματος

@app.route('/course/<int:course_id>/enroll', methods=['POST'])
@login_required
def enroll(course_id):
    """Εγγραφή φοιτητή σε μάθημα"""
    if session['role'] != 'student':
        flash('Μόνο φοιτητές μπορούν να εγγραφούν σε μάθημα.', 'warning')
        return redirect(url_for('dashboard'))

    db = get_db()
    existing = db.execute(
        'SELECT id FROM enrollments WHERE course_id = ? AND student_id = ?',
        (course_id, session['user_id'])
    ).fetchone()

    if existing:
        flash('Είστε ήδη εγγεγραμμένος σε αυτό το μάθημα.', 'info')
    else:
        db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (?, ?)',
                   (course_id, session['user_id']))
        db.commit()
        flash('Εγγραφήκατε στο μάθημα επιτυχώς!', 'success')

    db.close()
    return redirect(url_for('dashboard'))


@app.route('/courses')
@login_required
def all_courses():
    """Λίστα όλων των μαθημάτων"""
    db = get_db()
    courses = db.execute(
        '''SELECT c.*, u.full_name as instructor_name,
                  (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as student_count
           FROM courses c
           JOIN users u ON c.instructor_id = u.id
           ORDER BY c.name'''
    ).fetchall()

    # Μαθήματα που ο φοιτητής είναι εγγεγραμμένος
    enrolled_ids = set()
    if session['role'] == 'student':
        enrolled = db.execute(
            'SELECT course_id FROM enrollments WHERE student_id = ?', (session['user_id'],)
        ).fetchall()
        enrolled_ids = {e['course_id'] for e in enrolled}

    db.close()
    return render_template('courses.html', courses=courses, enrolled_ids=enrolled_ids)


@app.route('/course/create', methods=['GET', 'POST'])
@instructor_required
def create_course():
    """Δημιουργία νέου μαθήματος"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if name:
            semester = request.form.get('semester', '').strip() or None
            db = get_db()
            db.execute('INSERT INTO courses (name, description, instructor_id, semester) VALUES (?, ?, ?, ?)',
                       (name, description, session['user_id'], semester))
            db.commit()
            db.close()
            flash('Το μάθημα δημιουργήθηκε!', 'success')
            return redirect(url_for('dashboard'))

    return render_template('create_course.html')


# API - JSON για events (χρησιμοποιειται απο AJAX)

@app.route('/api/events/<int:course_id>')
@login_required
def api_events(course_id):
    """API: Επιστροφή συμβάντων σε JSON για ημερολόγιο"""
    db = get_db()
    events_list = db.execute(
        'SELECT * FROM events WHERE course_id = ?', (course_id,)
    ).fetchall()

    events_json = []
    color_map = {
        'lecture': '#0d6efd',
        'deadline': '#dc3545',
        'exam': '#ffc107',
        'general': '#198754'
    }
    for e in events_list:
        events_json.append({
            'id': e['id'],
            'title': e['title'],
            'start': e['event_date'],
            'description': e['description'] or '',
            'color': color_map.get(e['event_type'], '#6c757d')
        })

    db.close()
    return jsonify(events_json)


# Migration: ensure second semester exists (for DBs created before we added it)
def ensure_second_semester_course():
    """Αν υπάρχει μόνο ένα μάθημα, πρόσθεσε δεύτερο με άλλο εξάμηνο ώστε να δουλεύει το φίλτρο."""
    try:
        db = get_db()
        n = db.execute('SELECT COUNT(*) FROM courses').fetchone()[0]
        if n == 1:
            row = db.execute('SELECT id, instructor_id FROM courses LIMIT 1').fetchone()
            if row:
                db.execute('''INSERT INTO courses (name, description, instructor_id, semester)
                              VALUES (?, ?, ?, ?)''',
                           ('Δομές Δεδομένων',
                            'Δέντρα, γράφοι, στοίβες και ουρές. Αναλυτική και πειραματική ανάλυση αλγορίθμων.',
                            row['instructor_id'], 'Χειμερινό 2024-2025'))
                new_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
                for sid in db.execute('SELECT id FROM users WHERE role = ? LIMIT 2', ('student',)).fetchall():
                    db.execute('INSERT INTO enrollments (course_id, student_id) VALUES (?, ?)', (new_id, sid['id']))
            db.commit()
        db.close()
    except Exception:
        pass


def ensure_semesters_earino_ximerino():
    """Βεβαιώνει ότι υπάρχουν 2 μαθήματα: 1 Εαρινό, 1 Χειμερινό (για δοκιμή φίλτρου)."""
    try:
        db = get_db()
        courses = db.execute('SELECT id, name, semester FROM courses ORDER BY id').fetchall()
        if len(courses) >= 1:
            db.execute("UPDATE courses SET semester = ? WHERE id = ?", ('Εαρινό 2025-2026', courses[0]['id']))
        if len(courses) >= 2:
            db.execute("UPDATE courses SET semester = ? WHERE id = ?", ('Χειμερινό 2024-2025', courses[1]['id']))
        db.commit()
        db.close()
    except Exception:
        pass


# --- Security headers (best practice: harden responses) ---

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Cache static assets so logo/images don't reload on every nav (reduces lag)
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


# --- Error handlers (consistent UX; no stack traces or sensitive data to client) ---

@app.errorhandler(403)
def forbidden(e):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Forbidden'}), 403
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found(e):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Not found'}), 404
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def server_error(e):
    if app.config.get('DEBUG'):
        raise e
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('errors/500.html'), 500


# Εκκινηση

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if os.environ.get('FLASK_ENV') == 'production' and (not os.environ.get('SECRET_KEY') and not os.environ.get('FLASK_SECRET_KEY')):
        print("  WARNING: FLASK_ENV=production but SECRET_KEY not set. Set SECRET_KEY in .env for production!")
    init_db()
    ensure_second_semester_course()
    ensure_semesters_earino_ximerino()
    print("\n" + "=" * 60)
    print("  LMS - Learning Management System")
    print("  UniPi")
    print("=" * 60)
    print("\n  Demo: teacher/teacher123  |  maria/giorgos/eleni / student123")
    print("\n  Open: http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', debug=app.config['DEBUG'], port=port)
