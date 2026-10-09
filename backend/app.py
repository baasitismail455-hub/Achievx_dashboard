import os
import secrets
import hashlib
import json

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from backend.database import get_connection
from backend.auth import init_session, require_auth

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://achievx.pythonanywhere.com",
                "https://achievxdashboard.pythonanywhere.com",
                "http://127.0.0.1:5000",
                "http://localhost:5000",
                "http://10.112.25.60:5000"
            ]
        }
    }
)

init_session(app)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@app.get("/")
def home():
    return send_from_directory(PROJECT_ROOT, "index.html")

@app.get("/<path:path>")
def frontend(path):
    return send_from_directory(PROJECT_ROOT, path)

@app.get("/api/health")
def health():
    return jsonify({
        "status": "healthy"
    })


@app.get("/api/database-test")
def database_test():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                result = cur.fetchone()

        return jsonify({
            "database": "connected",
            "test": result[0]
        })

    except Exception as e:
        return jsonify({
            "database": "error",
            "message": str(e)
        }), 500

@app.post("/api/auth/login")
def auth_login():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email:
        return jsonify({"error": "email_required"}), 400

    if not password:
        return jsonify({"error": "password_required"}), 400

    from auth import authenticate_user, login_user

    user = authenticate_user(email, password)

    if not user:
        return jsonify({"error": "invalid_credentials"}), 401

    login_user(user["id"])

    return jsonify({
        "success": True,
        "user": user
    })

@app.get("/api/auth/me")
@require_auth
def auth_me(user):
    return jsonify({
        "authenticated": True,
        "user": user
    })


@app.post("/api/auth/logout")
def auth_logout():
    from auth import logout_user

    logout_user()

    return jsonify({
        "success": True
    })

@app.get("/api/organization")
@require_auth
def get_organization(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        o.id,
                        o.organization_code,
                        o.organization_name,
                        o.admin_name,
                        o.status,
                        o.device_limit,
                        o.created_at,
                        o.updated_at
                    FROM organizations o
                    WHERE o.admin_user_id = %s
                    """,
                    (user["id"],)
                )

                row = cur.fetchone()

        if not row:
            return jsonify({
                "error": "organization_not_found"
            }), 404

        return jsonify({
            "organization": {
                "id": str(row[0]),
                "organization_code": row[1],
                "organization_name": row[2],
                "admin_name": row[3],
                "status": row[4],
                "device_limit": row[5],
                "created_at": row[6].isoformat(),
                "updated_at": row[7].isoformat()
            }
        })

    except Exception as e:
        return jsonify({
            "error": "organization_load_failed",
            "message": str(e)
        }), 500

@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}

    organization_name = (data.get("organization_name") or "").strip()
    admin_name = (data.get("admin_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not organization_name:
        return jsonify({
            "error": "organization_name_required"
        }), 400

    if not admin_name:
        return jsonify({
            "error": "admin_name_required"
        }), 400

    if not email:
        return jsonify({
            "error": "email_required"
        }), 400

    if len(password) < 8:
        return jsonify({
            "error": "password_too_short"
        }), 400

    from auth import hash_password, login_user

    password_hash = hash_password(password)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # Check whether email already exists
                cur.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email,)
                )

                if cur.fetchone():
                    return jsonify({
                        "error": "email_already_registered"
                    }), 409

                # Create user
                cur.execute(
                    """
                    INSERT INTO users (
                        email,
                        password_hash,
                        full_name
                    )
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (email, password_hash, admin_name)
                )

                user_id = cur.fetchone()[0]

                # Generate organization code
                cur.execute(
                    "SELECT make_organization_code()"
                )

                organization_code = cur.fetchone()[0]

                # Create organization
                cur.execute(
                    """
                    INSERT INTO organizations (
                        organization_code,
                        organization_name,
                        admin_user_id,
                        admin_name
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        organization_code,
                        organization_name,
                        user_id,
                        admin_name
                    )
                )

                organization_id = cur.fetchone()[0]

                # Add admin as organization member
                cur.execute(
                    """
                    INSERT INTO organization_members (
                        organization_id,
                        user_id,
                        role,
                        full_name
                    )
                    VALUES (%s, %s, 'admin', %s)
                    """,
                    (
                        organization_id,
                        user_id,
                        admin_name
                    )
                )

                # Audit registration
                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'organization_created',
                        %s
                    )
                    """,
                    (
                        organization_id,
                        user_id,
                        admin_name,
                        "Organization created during registration"
                    )
                )

            conn.commit()

        # Log the user in immediately
        login_user(user_id)

        return jsonify({
            "success": True,
            "user": {
                "id": str(user_id),
                "email": email,
                "full_name": admin_name
            },
            "organization": {
                "id": str(organization_id),
                "organization_code": organization_code,
                "organization_name": organization_name
            }
        }), 201

    except Exception as e:
        return jsonify({
            "error": "registration_failed",
            "message": str(e)
        }), 500

@app.put("/api/organization")
@require_auth
def update_organization(user):
    data = request.get_json(silent=True) or {}

    organization_name = (data.get("organization_name") or "").strip()
    admin_name = (data.get("admin_name") or "").strip()

    if not organization_name:
        return jsonify({
            "error": "organization_name_required"
        }), 400

    if not admin_name:
        return jsonify({
            "error": "admin_name_required"
        }), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    UPDATE organizations
                    SET
                        organization_name = %s,
                        admin_name = %s
                    WHERE admin_user_id = %s
                    RETURNING
                        id,
                        organization_code,
                        organization_name,
                        admin_name,
                        status,
                        device_limit,
                        created_at,
                        updated_at
                    """,
                    (
                        organization_name,
                        admin_name,
                        user["id"]
                    )
                )

                row = cur.fetchone()

                if not row:
                    return jsonify({
                        "error": "organization_not_found"
                    }), 404

                # Keep the organization member's name synchronized
                cur.execute(
                    """
                    UPDATE organization_members
                    SET full_name = %s
                    WHERE user_id = %s
                    """,
                    (
                        admin_name,
                        user["id"]
                    )
                )

                # Keep the user's name synchronized
                cur.execute(
                    """
                    UPDATE users
                    SET full_name = %s
                    WHERE id = %s
                    """,
                    (
                        admin_name,
                        user["id"]
                    )
                )

                # Audit the change
                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'organization_updated',
                        %s
                    )
                    """,
                    (
                        row[0],
                        user["id"],
                        admin_name,
                        "Organization settings updated"
                    )
                )

            conn.commit()

        return jsonify({
            "success": True,
            "organization": {
                "id": str(row[0]),
                "organization_code": row[1],
                "organization_name": row[2],
                "admin_name": row[3],
                "status": row[4],
                "device_limit": row[5],
                "created_at": row[6].isoformat(),
                "updated_at": row[7].isoformat()
            }
        })

    except Exception as e:
        return jsonify({
            "error": "organization_update_failed",
            "message": str(e)
        }), 500

@app.get("/api/workers")
@require_auth
def get_workers(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        d.id,
                        d.device_code,
                        d.worker_label,
                        d.status,
                        d.last_sync_at,
                        d.revoked_at,
                        d.created_at,
                        d.updated_at
                    FROM devices d
                    INNER JOIN organizations o
                        ON o.id = d.organization_id
                    WHERE o.admin_user_id = %s
                    ORDER BY d.created_at DESC
                    """,
                    (user["id"],)
                )

                rows = cur.fetchall()

        workers = []

        for row in rows:
            workers.append({
                "id": str(row[0]),
                "device_code": row[1],
                "worker_label": row[2],
                "status": row[3],
                "last_sync_at": (
                    row[4].isoformat()
                    if row[4] else None
                ),
                "revoked_at": (
                    row[5].isoformat()
                    if row[5] else None
                ),
                "created_at": row[6].isoformat(),
                "updated_at": row[7].isoformat()
            })

        return jsonify({
            "workers": workers
        })

    except Exception as e:
        return jsonify({
            "error": "workers_load_failed",
            "message": str(e)
        }), 500

@app.get("/api/invitations")
@require_auth
def get_invitations(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT id
                    FROM organizations
                    WHERE admin_user_id = %s
                    """,
                    (user["id"],)
                )

                organization = cur.fetchone()

                if not organization:
                    return jsonify({
                        "error": "organization_not_found"
                    }), 404

                organization_id = organization[0]

                cur.execute(
                    """
                    SELECT
                        id,
                        invitation_code,
                        worker_label,
                        status,
                        expires_at,
                        used_at,
                        created_at
                    FROM device_invitations
                    WHERE organization_id = %s
                    ORDER BY created_at DESC
                    """,
                    (organization_id,)
                )

                rows = cur.fetchall()

        invitations = [
            {
                "id": str(row[0]),
                "invitation_code": row[1],
                "worker_label": row[2],
                "status": row[3],
                "expires_at": row[4].isoformat() if row[4] else None,
                "used_at": row[5].isoformat() if row[5] else None,
                "created_at": row[6].isoformat() if row[6] else None
            }
            for row in rows
        ]

        return jsonify({
            "invitations": invitations
        })

    except Exception as e:
        return jsonify({
            "error": "invitations_load_failed",
            "message": str(e)
        }), 500

@app.post("/api/invitations")
@require_auth
def create_invitation(user):
    data = request.get_json(silent=True) or {}

    worker_label = (data.get("worker_label") or "").strip()
    expires_minutes = data.get("expires_minutes")

    if not worker_label:
        return jsonify({
            "error": "worker_label_required"
        }), 400

    # Validate expiration.
    try:
        expires_minutes = int(expires_minutes)
    except (TypeError, ValueError):
        return jsonify({
            "error": "invalid_expiration"
        }), 400

    # Only allow the expiration values offered by the dashboard.
    allowed_expirations = {30, 60, 240}

    if expires_minutes not in allowed_expirations:
        return jsonify({
            "error": "invalid_expiration",
            "message": "Expiration must be 30, 60, or 240 minutes."
        }), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # Get the authenticated user's organization
                cur.execute(
                    """
                    SELECT id
                    FROM organizations
                    WHERE admin_user_id = %s
                    """,
                    (user["id"],)
                )

                organization = cur.fetchone()

                if not organization:
                    return jsonify({
                        "error": "organization_not_found"
                    }), 404

                organization_id = organization[0]

                # Generate invitation code
                cur.execute(
                    "SELECT make_invitation_code()"
                )

                invitation_code = cur.fetchone()[0]

                # Create invitation with requested expiration.
                cur.execute(
                    """
                    INSERT INTO device_invitations (
                        organization_id,
                        invitation_code,
                        worker_label,
                        created_by,
                        expires_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        now() + (%s * INTERVAL '1 minute')
                    )
                    RETURNING
                        id,
                        invitation_code,
                        worker_label,
                        status,
                        expires_at,
                        created_at
                    """,
                    (
                        organization_id,
                        invitation_code,
                        worker_label,
                        user["id"],
                        expires_minutes
                    )
                )

                row = cur.fetchone()

                # Audit
                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'invitation_created',
                        %s
                    )
                    """,
                    (
                        organization_id,
                        user["id"],
                        user["full_name"],
                        "Device invitation created for "
                        + worker_label
                    )
                )

            conn.commit()

        return jsonify({
            "success": True,
            "invitation": {
                "id": str(row[0]),
                "invitation_code": row[1],
                "worker_label": row[2],
                "status": row[3],
                "expires_at": row[4].isoformat(),
                "created_at": row[5].isoformat()
            }
        }), 201

    except Exception as e:
        return jsonify({
            "error": "invitation_creation_failed",
            "message": str(e)
        }), 500

@app.post("/api/studies")
@require_auth
def create_study(user):
    data = request.get_json(silent=True) or {}

    study_name = (data.get("study_name") or "").strip()
    description = (data.get("description") or "").strip()

    if not study_name:
        return jsonify({
            "error": "study_name_required"
        }), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # Get organization
                cur.execute(
                    """
                    SELECT id
                    FROM organizations
                    WHERE admin_user_id = %s
                    """,
                    (user["id"],)
                )

                organization = cur.fetchone()

                if not organization:
                    return jsonify({
                        "error": "organization_not_found"
                    }), 404

                organization_id = organization[0]

                # Generate study code
                cur.execute(
                    """
                    SELECT
                        'STU-' ||
                        UPPER(
                            SUBSTRING(
                                REPLACE(gen_random_uuid()::text, '-', ''),
                                1,
                                8
                            )
                        )
                    """
                )

                study_code = cur.fetchone()[0]

                # Create study
                cur.execute(
                    """
                    INSERT INTO studies (
                        organization_id,
                        study_code,
                        study_name,
                        description
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING
                        id,
                        study_code,
                        study_name,
                        description,
                        status,
                        created_at,
                        updated_at
                    """,
                    (
                        organization_id,
                        study_code,
                        study_name,
                        description or None
                    )
                )

                row = cur.fetchone()

                # Audit
                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'study_created',
                        %s
                    )
                    """,
                    (
                        organization_id,
                        user["id"],
                        user["full_name"],
                        "Study created: " + study_code
                    )
                )

            conn.commit()

        return jsonify({
            "success": True,
            "study": {
                "id": str(row[0]),
                "study_code": row[1],
                "study_name": row[2],
                "description": row[3],
                "status": row[4],
                "created_at": row[5].isoformat(),
                "updated_at": row[6].isoformat()
            }
        }), 201

    except Exception as e:
        return jsonify({
            "error": "study_creation_failed",
            "message": str(e)
        }), 500

@app.get("/api/studies")
@require_auth
def get_studies(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        s.id,
                        s.study_code,
                        s.study_name,
                        s.description,
                        s.status,
                        s.created_at,
                        s.updated_at
                    FROM studies s
                    INNER JOIN organizations o
                        ON o.id = s.organization_id
                    WHERE o.admin_user_id = %s
                    ORDER BY s.created_at DESC
                    """,
                    (user["id"],)
                )

                rows = cur.fetchall()

        studies = []

        for row in rows:
            studies.append({
                "id": str(row[0]),
                "study_code": row[1],
                "study_name": row[2],
                "description": row[3],
                "status": row[4],
                "created_at": row[5].isoformat(),
                "updated_at": row[6].isoformat()
            })

        return jsonify({
            "studies": studies
        })

    except Exception as e:
        return jsonify({
            "error": "studies_load_failed",
            "message": str(e)
        }), 500

@app.get("/api/records")
@require_auth
def get_records(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        r.id,
                        r.record_code,
                        r.study_id,
                        s.study_code,
                        s.study_name,
                        r.device_id,
                        d.device_code,
                        d.worker_label,
                        r.worker_id,
                        r.collected_at,
                        r.latitude,
                        r.longitude,
                        r.gps_accuracy,
                        r.location_label,
                        r.payload_json,
                        r.source_version,
                        r.created_at,
                        r.updated_at
                    FROM records r
                    INNER JOIN organizations o
                        ON o.id = r.organization_id
                    LEFT JOIN studies s
                        ON s.id = r.study_id
                    LEFT JOIN devices d
                        ON d.id = r.device_id
                    WHERE o.admin_user_id = %s
                    ORDER BY r.collected_at DESC
                    LIMIT 500
                    """,
                    (user["id"],)
                )

                rows = cur.fetchall()

        records = []

        for row in rows:
            records.append({
                "id": str(row[0]),
                "record_code": row[1],
                "study_id": str(row[2]) if row[2] else None,
                "study_code": row[3],
                "study_name": row[4],
                "device_id": str(row[5]) if row[5] else None,
                "device_code": row[6],
                "worker_label": row[7],
                "worker_id": str(row[8]) if row[8] else None,
                "collected_at": row[9].isoformat() if row[9] else None,
                "latitude": float(row[10]) if row[10] is not None else None,
                "longitude": float(row[11]) if row[11] is not None else None,
                "gps_accuracy": float(row[12]) if row[12] is not None else None,
                "location_label": row[13],
                "payload_json": row[14],
                "source_version": row[15],
                "created_at": row[16].isoformat(),
                "updated_at": row[17].isoformat()
            })

        return jsonify({
            "records": records,
            "count": len(records)
        })

    except Exception as e:
        return jsonify({
            "error": "records_load_failed",
            "message": str(e)
        }), 500

@app.get("/api/audit")
@require_auth
def get_audit_logs(user):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        a.id,
                        a.actor_user_id,
                        a.actor_name,
                        a.action,
                        a.details,
                        a.created_at
                    FROM audit_logs a
                    INNER JOIN organizations o
                        ON o.id = a.organization_id
                    WHERE o.admin_user_id = %s
                    ORDER BY a.created_at DESC
                    LIMIT 100
                    """,
                    (user["id"],)
                )

                rows = cur.fetchall()

        audit = []

        for row in rows:
            audit.append({
                "id": row[0],
                "actor_user_id": str(row[1]) if row[1] else None,
                "actor_name": row[2],
                "action": row[3],
                "details": row[4],
                "created_at": row[5].isoformat()
            })

        return jsonify({
            "audit": audit,
            "count": len(audit)
        })

    except Exception as e:
        return jsonify({
            "error": "audit_load_failed",
            "message": str(e)
        }), 500

@app.post("/api/workers/<worker_id>/revoke")
@require_auth
def revoke_worker(user, worker_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT
                        d.id,
                        d.device_code,
                        d.worker_label,
                        d.status,
                        d.organization_id
                    FROM devices d
                    INNER JOIN organizations o
                        ON o.id = d.organization_id
                    WHERE d.id = %s
                      AND o.admin_user_id = %s
                    """,
                    (worker_id, user["id"])
                )

                device = cur.fetchone()

                if not device:
                    return jsonify({
                        "error": "worker_not_found"
                    }), 404

                device_id = device[0]
                device_code = device[1]
                worker_label = device[2]
                organization_id = device[4]

                cur.execute(
                    """
                    UPDATE devices
                    SET
                        status = 'revoked',
                        revoked_at = now()
                    WHERE id = %s
                    RETURNING
                        id,
                        device_code,
                        worker_label,
                        status,
                        revoked_at,
                        updated_at
                    """,
                    (device_id,)
                )

                row = cur.fetchone()

                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'device_revoked',
                        %s
                    )
                    """,
                    (
                        organization_id,
                        user["id"],
                        user["full_name"],
                        "Device revoked: " + device_code +
                        " (" + worker_label + ")"
                    )
                )

            conn.commit()

        return jsonify({
            "success": True,
            "worker": {
                "id": str(row[0]),
                "device_code": row[1],
                "worker_label": row[2],
                "status": row[3],
                "revoked_at": row[4].isoformat() if row[4] else None,
                "updated_at": row[5].isoformat()
            }
        })

    except Exception as e:
        return jsonify({
            "error": "worker_revoke_failed",
            "message": str(e)
        }), 500

@app.post("/api/workers")
@require_auth
def create_worker(user):
    data = request.get_json(silent=True) or {}

    worker_label = (data.get("worker_label") or "").strip()

    if not worker_label:
        return jsonify({"error": "worker_label_required"}), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT id, device_limit
                    FROM organizations
                    WHERE admin_user_id = %s
                    """,
                    (user["id"],)
                )

                organization = cur.fetchone()

                if not organization:
                    return jsonify({
                        "error": "organization_not_found"
                    }), 404

                organization_id = organization[0]
                device_limit = organization[1]

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM devices
                    WHERE organization_id = %s
                      AND status <> 'revoked'
                    """,
                    (organization_id,)
                )

                active_device_count = cur.fetchone()[0]

                if active_device_count >= device_limit:
                    return jsonify({
                        "error": "device_limit_reached"
                    }), 409

                cur.execute("SELECT make_device_code()")
                device_code = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO devices (
                        organization_id,
                        device_code,
                        worker_label,
                        status,
                        registered_by,
                        last_sync_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'active',
                        %s,
                        NULL
                    )
                    RETURNING
                        id,
                        device_code,
                        worker_label,
                        status,
                        last_sync_at,
                        revoked_at,
                        created_at,
                        updated_at
                    """,
                    (
                        organization_id,
                        device_code,
                        worker_label,
                        user["id"]
                    )
                )

                row = cur.fetchone()

                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'device_created',
                        %s
                    )
                    """,
                    (
                        organization_id,
                        user["id"],
                        user["full_name"],
                        "Device created: " + device_code +
                        " (" + worker_label + ")"
                    )
                )

            conn.commit()

        return jsonify({
            "success": True,
            "worker": {
                "id": str(row[0]),
                "device_code": row[1],
                "worker_label": row[2],
                "status": row[3],
                "last_sync_at": row[4].isoformat()
                    if row[4] else None,
                "revoked_at": row[5].isoformat()
                    if row[5] else None,
                "created_at": row[6].isoformat(),
                "updated_at": row[7].isoformat()
            }
        }), 201

    except Exception as e:
        return jsonify({
            "error": "worker_creation_failed",
            "message": str(e)
        }), 500

@app.post("/api/device/enroll")
def enroll_device():
    data = request.get_json(silent=True) or {}

    invitation_code = (
        data.get("invitation_code") or ""
    ).strip()

    if not invitation_code:
        return jsonify({
            "error": "invitation_code_required"
        }), 400

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                # -------------------------------------------------
                # 1. Find invitation
                # -------------------------------------------------

                cur.execute(
                    """
                    SELECT
                        id,
                        organization_id,
                        worker_label,
                        status,
                        expires_at
                    FROM device_invitations
                    WHERE invitation_code = %s
                    """,
                    (invitation_code,)
                )

                invitation = cur.fetchone()

                if not invitation:
                    return jsonify({
                        "error": "invalid_invitation"
                    }), 404

                invitation_id = invitation[0]
                organization_id = invitation[1]
                worker_label = invitation[2]
                invitation_status = invitation[3]
                expires_at = invitation[4]

                # -------------------------------------------------
                # 2. Validate invitation status
                # -------------------------------------------------

                if invitation_status != "pending":
                    return jsonify({
                        "error": "invitation_not_available"
                    }), 409

                # -------------------------------------------------
                # 3. Validate expiration
                # -------------------------------------------------

                cur.execute(
                    "SELECT now()"
                )

                current_time = cur.fetchone()[0]

                if expires_at <= current_time:

                    cur.execute(
                        """
                        UPDATE device_invitations
                        SET status = 'expired'
                        WHERE id = %s
                        """,
                        (invitation_id,)
                    )

                    conn.commit()

                    return jsonify({
                        "error": "invitation_expired"
                    }), 410

                # -------------------------------------------------
                # 4. Check organization device limit
                # -------------------------------------------------

                cur.execute(
                    """
                    SELECT device_limit
                    FROM organizations
                    WHERE id = %s
                    """,
                    (organization_id,)
                )

                organization = cur.fetchone()

                if not organization:
                    return jsonify({
                        "error": "organization_not_found"
                    }), 404

                device_limit = organization[0]

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM devices
                    WHERE organization_id = %s
                      AND status <> 'revoked'
                    """,
                    (organization_id,)
                )

                active_device_count = cur.fetchone()[0]

                if active_device_count >= device_limit:
                    return jsonify({
                        "error": "device_limit_reached"
                    }), 409

                # -------------------------------------------------
                # 5. Generate device identity
                # -------------------------------------------------

                cur.execute(
                    "SELECT make_device_code()"
                )

                device_code = cur.fetchone()[0]

                device_token = secrets.token_urlsafe(32)

                device_token_hash = hashlib.sha256(
                    device_token.encode("utf-8")
                ).hexdigest()

                # -------------------------------------------------
                # 6. Create the device/worker
                # -------------------------------------------------

                cur.execute(
                    """
                    INSERT INTO devices (
                        organization_id,
                        device_code,
                        worker_label,
                        status,
                        registered_by,
                        last_sync_at,
                        device_token_hash,
                        device_token_created_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'active',
                        NULL,
                        now(),
                        %s,
                        now()
                    )
                    RETURNING
                        id,
                        device_code,
                        worker_label,
                        status
                    """,
                    (
                        organization_id,
                        device_code,
                        worker_label,
                        device_token_hash
                    )
                )

                device = cur.fetchone()

                device_id = device[0]
                device_code = device[1]
                worker_label = device[2]

                # -------------------------------------------------
                # 7. Consume invitation
                # -------------------------------------------------

                cur.execute(
                    """
                    UPDATE device_invitations
                    SET
                        status = 'used',
                        used_at = now()
                    WHERE id = %s
                    """,
                    (invitation_id,)
                )

                # -------------------------------------------------
                # 8. Audit enrollment
                # -------------------------------------------------

                cur.execute(
                    """
                    INSERT INTO audit_logs (
                        organization_id,
                        actor_user_id,
                        actor_name,
                        action,
                        details
                    )
                    VALUES (
                        %s,
                        NULL,
                        %s,
                        'device_enrolled',
                        %s
                    )
                    """,
                    (
                        organization_id,
                        worker_label,
                        "Device enrolled: " + device_code
                    )
                )

                conn.commit()

                # -------------------------------------------------
                # 9. Return enrollment credentials
                # -------------------------------------------------

                return jsonify({
                    "device_id": str(device_id),
                    "device_token": device_token,
                    "organization_id": str(organization_id),
                    "device_code": device_code,
                    "worker_label": worker_label
                }), 200

    except Exception as e:
        print("DEVICE ENROLLMENT ERROR:", e)

        return jsonify({
            "error": "device_enrollment_failed"
        }), 500

@app.post("/api/device/studies")
def get_device_studies():
    data = request.get_json(silent=True) or {}

    device_token = (
        data.get("device_token") or ""
    ).strip()

    if not device_token:
        return jsonify({
            "error": "device_token_required"
        }), 400

    try:
        device_token_hash = hashlib.sha256(
            device_token.encode("utf-8")
        ).hexdigest()

        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT organization_id
                    FROM devices
                    WHERE device_token_hash = %s
                      AND status = 'active'
                    """,
                    (device_token_hash,)
                )

                device = cur.fetchone()

                if not device:
                    return jsonify({
                        "error": "invalid_device_token"
                    }), 401

                organization_id = device[0]

                cur.execute(
                    """
                    SELECT
                        id,
                        study_code,
                        study_name
                    FROM studies
                    WHERE organization_id = %s
                      AND status = 'active'
                    ORDER BY created_at DESC
                    """,
                    (organization_id,)
                )

                rows = cur.fetchall()

                studies = [
                    {
                        "id": str(row[0]),
                        "study_code": row[1],
                        "study_name": row[2]
                    }
                    for row in rows
                ]

                return jsonify(studies), 200

    except Exception as e:
        print("DEVICE STUDIES ERROR:", e)

        return jsonify({
            "error": "device_studies_failed"
        }), 500

@app.post("/api/device/sync")
def sync_device_records():
    data = request.get_json(silent=True) or {}

    device_token = (
        data.get("device_token") or ""
    ).strip()

    records = data.get("records")

    if not device_token:
        return jsonify({
            "error": "device_token_required"
        }), 400

    if not isinstance(records, list):
        return jsonify({
            "error": "records_must_be_array"
        }), 400

    try:
        device_token_hash = hashlib.sha256(
            device_token.encode("utf-8")
        ).hexdigest()

        with get_connection() as conn:
            with conn.cursor() as cur:

                # -------------------------------------------------
                # 1. Authenticate device
                # -------------------------------------------------
                cur.execute(
                    """
                    SELECT
                        id,
                        organization_id,
                        status
                    FROM devices
                    WHERE device_token_hash = %s
                    """,
                    (device_token_hash,)
                )

                device = cur.fetchone()

                if not device:
                    return jsonify({
                        "error": "invalid_device_token"
                    }), 401

                device_id = device[0]
                organization_id = device[1]
                device_status = device[2]

                if device_status != "active":
                    return jsonify({
                        "error": "device_not_active"
                    }), 403

                results = []

                # -------------------------------------------------
                # 2. Process each record
                # -------------------------------------------------
                for record in records:

                    if not isinstance(record, dict):
                        results.append({
                            "record_code": None,
                            "status": "failed",
                            "error": "invalid_record"
                        })
                        continue

                    record_code = (
                        record.get("record_code") or ""
                    ).strip()

                    study_id = record.get("study_id")

                    if not record_code:
                        results.append({
                            "record_code": None,
                            "status": "failed",
                            "error": "record_code_required"
                        })
                        continue

                    if not study_id:
                        results.append({
                            "record_code": record_code,
                            "status": "failed",
                            "error": "study_id_required"
                        })
                        continue

                    # -------------------------------------------------
                    # 3. Verify study belongs to this organization
                    # -------------------------------------------------
                    cur.execute(
                        """
                        SELECT id
                        FROM studies
                        WHERE id = %s
                          AND organization_id = %s
                        """,
                        (
                            study_id,
                            organization_id
                        )
                    )

                    study = cur.fetchone()

                    if not study:
                        results.append({
                            "record_code": record_code,
                            "status": "failed",
                            "error": "invalid_study"
                        })
                        continue

                    # -------------------------------------------------
                    # 4. Check whether record already exists
                    # -------------------------------------------------
                    cur.execute(
                        """
                        SELECT id
                        FROM records
                        WHERE organization_id = %s
                          AND record_code = %s
                        """,
                        (
                            organization_id,
                            record_code
                        )
                    )

                    existing_record = cur.fetchone()

                    if existing_record:

                        results.append({
                            "record_code": record_code,
                            "status": "already_synced"
                        })

                        continue

                    # -------------------------------------------------
                    # 5. Insert record
                    # -------------------------------------------------
                    cur.execute(
                        """
                        INSERT INTO records (
                            organization_id,
                            record_code,
                            study_id,
                            device_id,
                            worker_id,
                            latitude,
                            longitude,
                            gps_accuracy,
                            location_label,
                            payload_json,
                            source_version
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        """,
                        (
                            organization_id,
                            record_code,
                            study_id,
                            device_id,
                            device_id,
                            record.get("latitude"),
                            record.get("longitude"),
                            record.get("gps_accuracy"),
                            record.get("location_label"),
                            json.dumps(
                                record.get("payload_json") or {}
                            ),
                            record.get(
                                "source_version",
                                "achievx-main"
                            )
                        )
                    )

                    results.append({
                        "record_code": record_code,
                        "status": "synced"
                    })

                # -------------------------------------------------
                # 6. Update device sync timestamp
                # -------------------------------------------------
                cur.execute(
                    """
                    UPDATE devices
                    SET
                        last_sync_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (device_id,)
                )

                conn.commit()

                return jsonify(results), 200

    except Exception as e:
        print("DEVICE SYNC ERROR:", e)

        return jsonify({
            "error": "device_sync_failed"
        }), 500

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )
