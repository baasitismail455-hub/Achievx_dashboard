import os
import secrets
from functools import wraps

from flask import session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from backend.database import get_connection


def init_session(app):
    app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    if os.getenv("FLASK_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True

    from flask_session import Session

    Session(app)


def login_user(user_id):
    session.clear()
    session["user_id"] = str(user_id)


def logout_user():
    session.clear()


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    email,
                    full_name,
                    is_active
                FROM users
                WHERE id = %s
                """,
                (user_id,)
            )

            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": str(row[0]),
        "email": row[1],
        "full_name": row[2],
        "is_active": row[3],
    }


def authenticate_user(email, password):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    email,
                    password_hash,
                    full_name,
                    is_active
                FROM users
                WHERE LOWER(email) = LOWER(%s)
                """,
                (email,)
            )

            row = cur.fetchone()

    if not row:
        return None

    user_id, user_email, password_hash, full_name, is_active = row

    if not is_active:
        return None

    if not check_password_hash(password_hash, password):
        return None

    return {
        "id": str(user_id),
        "email": user_email,
        "full_name": full_name,
        "is_active": is_active,
    }


def hash_password(password):
    return generate_password_hash(password)


def require_auth(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            return jsonify({
                "error": "authentication_required"
            }), 401

        return route_function(user, *args, **kwargs)

    return wrapper
