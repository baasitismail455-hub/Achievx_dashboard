# AchievX Admin Dashboard

A separate admin/control-plane project for AchievX organizations.

The dashboard manages organizations, administrators, workers/devices, invitations, studies, records, and audit activity through a Flask API backed by PostgreSQL.

## Architecture

- Frontend: vanilla HTML/CSS/JavaScript
- Backend: Python Flask
- Database: PostgreSQL
- Authentication: Flask session-based authentication
- Passwords: Werkzeug password hashing
- API: JSON REST-style endpoints under `/api`
- Database access: PostgreSQL through `psycopg`
- No direct database access from the browser
- No dependency on the existing AchievX Operations Suite codebase
- Designed to later connect to AchievX through a dedicated synchronization API
- White + AchievX blue visual system

### Request flow

```text
Browser
   │
   ▼
Vanilla HTML/CSS/JavaScript
   │
   │ HTTP / JSON
   ▼
Flask API
   │
   │ authenticated server-side queries
   ▼
PostgreSQL