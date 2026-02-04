# Authentication System in excel_poller_teardown Branch

## Overview
The `excel_poller_teardown` branch includes a **complete user authentication system** with login, logout, session management, and protected routes.

---

## 🔐 Backend Components

### 1. **app/auth/routes.py** - Authentication Routes

#### Endpoints:

**POST `/api/auth/login`**
- Authenticates user with username/password
- Creates Flask session with `user_id` and `username`
- Updates `last_login` timestamp
- Returns user info (id, username, is_admin)
- **Security**: Checks if user exists, is active, and password matches
- **Logging**: Logs successful logins and failed attempts

**POST `/api/auth/logout`**
- Clears Flask session
- Logs logout event

**GET `/api/auth/me`**
- Returns current logged-in user information
- Returns 401 if not authenticated
- Includes: id, username, is_admin, is_active, last_login

---

### 2. **app/auth/utils.py** - Authentication Utilities

#### Functions:

**`hash_password(password: str) -> str`**
- Uses `werkzeug.security.generate_password_hash()`
- Method: `pbkdf2:sha256` (Python 3.9+ compatible)
- Note: Uses pbkdf2 instead of scrypt (scrypt requires Python 3.11+)

**`verify_password(password_hash: str, password: str) -> bool`**
- Verifies password against hash using `check_password_hash()`

**`get_current_user() -> User | None`**
- Gets current user from Flask session
- Returns `None` if not in request context or not logged in
- Only returns active users

**`get_current_username() -> str | None`**
- Convenience function to get username

**`format_source_with_user(source: str, user=None) -> str`**
- Formats source string with user info
- Example: `"Brain"` → `"Brain - Daniel"`
- Used for tracking who made changes

**`@login_required` Decorator**
- **Critical decorator** used throughout the app
- Checks if user is logged in
- Returns 401 Unauthorized if not authenticated
- Usage:
  ```python
  @brain_bp.route('/drafting-work-load')
  @login_required
  def drafting_work_load():
      # Route is protected
  ```

---

### 3. **app/models.py** - User Model

```python
class User(db.Model):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    job_events = db.relationship('JobEvents', backref='user', lazy='dynamic')
    submittal_events = db.relationship('SubmittalEvents', backref='user', lazy='dynamic')
```

**Features:**
- Unique username constraint
- Password hashing (not plain text)
- Active/inactive user flag
- Admin flag for role-based access
- Tracks last login time
- Relationships to `JobEvents` and `SubmittalEvents` for audit trail

---

### 4. **app/__init__.py** - Blueprint Registration

**Changes:**
```python
from app.auth.routes import auth_bp

# Register auth blueprint
app.register_blueprint(auth_bp)
```

**Note:** The auth blueprint uses `url_prefix='/api/auth'` defined in the blueprint itself.

---

### 5. **migrations/add_user_authentication.py** - Database Migration

**Purpose:** Creates the `users` table and adds `user_id` foreign keys to event tables.

**Features:**
- Idempotent (safe to run multiple times)
- Checks if tables/columns exist before creating
- Supports both SQLite and PostgreSQL
- Creates `users` table with all required columns
- Adds `user_id` columns to `job_events` and `submittal_events` tables

**Usage:**
```bash
python migrations/add_user_authentication.py
```

---

## 🎨 Frontend Components

### 1. **frontend/src/pages/Login.jsx** - Login Page

**Features:**
- Login/Signup toggle (though signup endpoint may not exist)
- Username and password input fields
- Error message display
- Loading state during authentication
- Auto-redirect if already logged in (checks `/api/auth/me`)
- Uses React Router for navigation
- Session-based (uses `credentials: 'include'` for cookies)

**UI:**
- Clean, centered login form
- Tailwind CSS styling
- Responsive design
- Error handling with user-friendly messages

---

### 2. **frontend/src/utils/auth.js** - Frontend Auth Utilities

**Functions:**

**`checkAuth() -> Promise<User | null>`**
- Checks if user is currently logged in
- Calls `/api/auth/me` endpoint
- Returns user object if authenticated, `null` otherwise
- Used for route protection and checking auth state

**`logout() -> Promise<void>`**
- Calls `/api/auth/logout` endpoint
- Clears server-side session
- Should be followed by client-side state cleanup

---

## 🔒 Protected Routes

### Routes Using `@login_required`:

All Drafting Work Load routes are protected:
- `GET /brain/drafting-work-load`
- `PUT /brain/drafting-work-load/order`
- `PUT /brain/drafting-work-load/notes`
- `PUT /brain/drafting-work-load/submittal-drafting-status`

**Behavior:**
- Returns `401 Unauthorized` with JSON: `{"error": "Authentication required"}`
- Frontend should redirect to login page on 401

---

## 📋 Session Management

### Flask Sessions:
- Uses Flask's built-in session management
- Session stored server-side (cookie-based)
- `session.permanent = True` - makes session persistent
- Session keys:
  - `session['user_id']` - User ID
  - `session['username']` - Username (for logging)

### Security:
- Passwords are hashed (never stored in plain text)
- Session-based authentication (no JWT tokens)
- Password verification uses werkzeug's secure comparison
- Inactive users cannot log in

---

## 🔗 Integration Points

### 1. **Event Tracking**
- `JobEvents` and `SubmittalEvents` have `user_id` foreign key
- Tracks which user made changes
- `format_source_with_user()` adds username to source strings

### 2. **Route Protection**
- Decorator pattern: `@login_required`
- Applied to sensitive routes
- Returns consistent 401 response

### 3. **Frontend Integration**
- Login page at `/login` route
- Auth check on app load
- Redirect to login if not authenticated
- Logout functionality

---

## 🚀 Implementation Checklist

If cherry-picking the authentication system:

### Backend:
- [ ] Add `User` model to `models.py`
- [ ] Create `app/auth/` directory
- [ ] Add `app/auth/routes.py` with login/logout/me endpoints
- [ ] Add `app/auth/utils.py` with utilities and decorator
- [ ] Register `auth_bp` blueprint in `app/__init__.py`
- [ ] Run migration: `python migrations/add_user_authentication.py`
- [ ] Add `@login_required` to protected routes

### Frontend:
- [ ] Create `frontend/src/pages/Login.jsx`
- [ ] Create `frontend/src/utils/auth.js`
- [ ] Add login route to React Router
- [ ] Add auth check in App.jsx or main component
- [ ] Handle 401 responses (redirect to login)
- [ ] Add logout button/functionality

### Testing:
- [ ] Test login with valid credentials
- [ ] Test login with invalid credentials
- [ ] Test logout
- [ ] Test protected routes (should require login)
- [ ] Test session persistence
- [ ] Test inactive user cannot log in

---

## ⚠️ Important Notes

1. **No Registration Endpoint**: The frontend has a signup form, but the backend only has `/login`. You'll need to either:
   - Add a registration endpoint
   - Remove signup UI
   - Create users manually via migration/script

2. **Session Security**: Flask sessions use signed cookies. For production:
   - Set `SECRET_KEY` in Flask config
   - Consider using `SESSION_COOKIE_SECURE=True` for HTTPS
   - Consider `SESSION_COOKIE_HTTPONLY=True` for XSS protection

3. **Password Hashing**: Uses `pbkdf2:sha256` for Python 3.9+ compatibility. If you're on Python 3.11+, you could use `scrypt` for better security.

4. **Database Migration**: The migration script is idempotent, but you should:
   - Backup database before running
   - Test on staging first
   - Verify foreign key constraints work correctly

5. **Frontend Route Protection**: The frontend should check auth state and redirect to login. This may require:
   - Auth context/provider
   - Protected route wrapper component
   - Auto-redirect on 401 responses

---

## 📊 Summary

**Complete Authentication System Includes:**
- ✅ User model with password hashing
- ✅ Login/logout endpoints
- ✅ Session management
- ✅ `@login_required` decorator
- ✅ Frontend login page
- ✅ Auth utilities (frontend & backend)
- ✅ Database migration
- ✅ Integration with event tracking

**Security Features:**
- Password hashing (pbkdf2:sha256)
- Session-based authentication
- Active user checking
- Failed login attempt logging

**Missing/Incomplete:**
- ❌ User registration endpoint (frontend has UI but no backend)
- ❌ Password reset functionality
- ❌ Role-based access control (has `is_admin` flag but no RBAC implementation)
- ❌ Frontend route protection (needs implementation)

