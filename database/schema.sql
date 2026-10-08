-- ============================================================
-- ACHIEVX ADMIN DASHBOARD
-- Self-hosted PostgreSQL schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- USERS
-- Replaces Supabase auth.users
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- ORGANIZATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_code TEXT NOT NULL UNIQUE,
    organization_name TEXT NOT NULL,
    admin_user_id UUID NOT NULL UNIQUE
        REFERENCES users(id) ON DELETE CASCADE,
    admin_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended')),
    device_limit INTEGER NOT NULL DEFAULT 10
        CHECK (device_limit > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- ORGANIZATION MEMBERS
-- ============================================================

CREATE TABLE IF NOT EXISTS organization_members (
    organization_id UUID NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'admin'
        CHECK (role IN ('admin', 'manager', 'viewer')),
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (organization_id, user_id)
);

-- ============================================================
-- STUDIES
-- ============================================================

CREATE TABLE IF NOT EXISTS studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    study_code TEXT NOT NULL,
    study_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN (
            'active',
            'paused',
            'completed',
            'archived'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (organization_id, study_code)
);

-- ============================================================
-- DEVICES / WORKERS
-- ============================================================

CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    device_code TEXT NOT NULL,
    worker_label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'offline', 'revoked')),
    registered_by UUID
        REFERENCES users(id) ON DELETE SET NULL,
    last_sync_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (organization_id, device_code)
);

-- ============================================================
-- DEVICE INVITATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS device_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    invitation_code TEXT NOT NULL UNIQUE,
    worker_label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'used',
            'expired',
            'revoked'
        )),
    created_by UUID
        REFERENCES users(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- RECORDS
-- ============================================================

CREATE TABLE IF NOT EXISTS records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    record_code TEXT NOT NULL,

    study_id UUID
        REFERENCES studies(id) ON DELETE SET NULL,

    device_id UUID
        REFERENCES devices(id) ON DELETE SET NULL,

    worker_id UUID
        REFERENCES devices(id) ON DELETE SET NULL,

    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    latitude NUMERIC,
    longitude NUMERIC,
    gps_accuracy NUMERIC,
    location_label TEXT,

    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    source_version TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (organization_id, record_code)
);

-- ============================================================
-- AUDIT LOGS
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id UUID NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,

    actor_user_id UUID
        REFERENCES users(id) ON DELETE SET NULL,

    actor_name TEXT,

    action TEXT NOT NULL,

    details TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_members_user
    ON organization_members(user_id);

CREATE INDEX IF NOT EXISTS idx_studies_org
    ON studies(organization_id);

CREATE INDEX IF NOT EXISTS idx_devices_org
    ON devices(organization_id);

CREATE INDEX IF NOT EXISTS idx_records_org
    ON records(organization_id);

CREATE INDEX IF NOT EXISTS idx_records_study
    ON records(study_id);

CREATE INDEX IF NOT EXISTS idx_records_worker
    ON records(worker_id);

CREATE INDEX IF NOT EXISTS idx_records_collected
    ON records(collected_at);

CREATE INDEX IF NOT EXISTS idx_invites_org
    ON device_invitations(organization_id);

CREATE INDEX IF NOT EXISTS idx_audit_org
    ON audit_logs(organization_id);

CREATE INDEX IF NOT EXISTS idx_audit_created
    ON audit_logs(created_at);

-- ============================================================
-- CODE GENERATORS
-- ============================================================

CREATE OR REPLACE FUNCTION make_organization_code()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    candidate TEXT;
BEGIN
    LOOP
        candidate :=
            'ORG-' ||
            upper(substr(encode(gen_random_bytes(8), 'hex'), 1, 10));

        EXIT WHEN NOT EXISTS (
            SELECT 1
            FROM organizations
            WHERE organization_code = candidate
        );
    END LOOP;

    RETURN candidate;
END;
$$;

CREATE OR REPLACE FUNCTION make_invitation_code()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    candidate TEXT;
BEGIN
    LOOP
        candidate := upper(
            substr(encode(gen_random_bytes(2), 'hex'), 1, 3)
            || '-'
            || substr(encode(gen_random_bytes(3), 'hex'), 1, 3)
            || '-'
            || substr(encode(gen_random_bytes(2), 'hex'), 1, 3)
        );

        EXIT WHEN NOT EXISTS (
            SELECT 1
            FROM device_invitations
            WHERE invitation_code = candidate
        );
    END LOOP;

    RETURN candidate;
END;
$$;

CREATE OR REPLACE FUNCTION make_device_code()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN
        'DEV-' ||
        upper(substr(encode(gen_random_bytes(6), 'hex'), 1, 8));
END;
$$;

-- ============================================================
-- TIMESTAMP TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_updated_at ON users;

CREATE TRIGGER users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS organizations_updated_at ON organizations;

CREATE TRIGGER organizations_updated_at
BEFORE UPDATE ON organizations
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS studies_updated_at ON studies;

CREATE TRIGGER studies_updated_at
BEFORE UPDATE ON studies
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS devices_updated_at ON devices;

CREATE TRIGGER devices_updated_at
BEFORE UPDATE ON devices
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS records_updated_at ON records;

CREATE TRIGGER records_updated_at
BEFORE UPDATE ON records
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- END
-- ============================================================