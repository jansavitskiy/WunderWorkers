# WunderWorkers — Employee Work Tracking System

A Flask web app for tracking employee work reports, managing organizations, and admin oversight of staff activity.

## Run & Operate
- **Dev**: `python app.py` (runs on 0.0.0.0:5000)
- **Production**: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app`
- **Default admin**: `admin` / `admin123` (created on first run if no users exist)

## Stack
- Python 3.12
- Flask 3.1.3 + Flask-SQLAlchemy + Flask-Bcrypt + Flask-WTF
- SQLite (file: `instance/workers.db`)
- Jinja2 templates, vanilla JS/CSS

## Where things live
- `app.py` — main app, all routes, forms, migration logic
- `models/` — SQLAlchemy models (User, Organization, Task, Report via app.py)
- `templates/` — Jinja2 HTML templates
- `static/` — CSS and JS assets

## Architecture decisions
- Report model lives in `app.py` (not in `models/`) alongside its migration logic
- Migration function `migrate_reports_organization_fk()` runs on startup to handle schema evolution
- SQLite used for simplicity; no external DB required
- Role-based access: `admin` vs `employee` checked via Flask session

## Product
- Employee registration and login with role separation
- Employees submit work reports (hours, organization, description)
- Admin panel: view all staff, filter reports by date range, export CSV
- Organization management (add/delete) by admin
- Reports tied to organizations (foreign key, not free text)

## User preferences
_Populate as you build_

## Gotchas
- The `organization` text column was migrated to `organization_id` FK; migration runs on every startup safely
- SQLite `.db` file is in `instance/` directory (Flask default)

## Pointers
- Deployment skill: `.local/skills/deployment/SKILL.md`
- Workflows skill: `.local/skills/workflows/SKILL.md`
