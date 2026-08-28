#!/bin/sh
# Container entrypoint: provision roles, migrate, seed, serve.
#
# Ordering is not arbitrary. The audit privilege model — the application role holds
# INSERT and SELECT on audit_event and nothing else — is the system's strongest
# guarantee, and it is a database privilege rather than application code. So roles are
# created before migrations, and the audit grant is re-applied *after* migrations,
# because the table does not exist until then.
#
# The script fails closed. If roles cannot be provisioned, or the audit grant cannot be
# verified, it exits non-zero rather than starting an API whose audit trail is editable.
#
# Environment:
#   ADMIN_DATABASE_URL       superuser URL (Railway supplies this as DATABASE_URL)
#   MIGRATION_DATABASE_URL   warba_migrate — schema owner, runs Alembic
#   DATABASE_URL             warba_app — the API's own, least-privilege connection
#   WARBA_MIGRATE_PASSWORD   secret for warba_migrate
#   WARBA_APP_PASSWORD       secret for warba_app
#   SEED_ON_START            "true" to load synthetic fixtures when the DB is empty
#   PORT                     injected by the host; defaults to 8000

set -eu

log() { echo "[start] $*"; }
die() { echo "[start] FATAL: $*" >&2; exit 1; }

: "${PORT:=8000}"

[ -n "${ADMIN_DATABASE_URL:-}" ] || die "ADMIN_DATABASE_URL is unset. Set it to the database's superuser URL (on Railway, the Postgres service's DATABASE_URL)."
[ -n "${MIGRATION_DATABASE_URL:-}" ] || die "MIGRATION_DATABASE_URL is unset."
[ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL is unset."
[ -n "${WARBA_MIGRATE_PASSWORD:-}" ] || die "WARBA_MIGRATE_PASSWORD is unset."
[ -n "${WARBA_APP_PASSWORD:-}" ] || die "WARBA_APP_PASSWORD is unset."

# psql speaks postgresql://, SQLAlchemy wants postgresql+psycopg://. Strip the driver.
admin_url=$(printf '%s' "$ADMIN_DATABASE_URL" | sed 's|postgresql+psycopg://|postgresql://|')

admin_user=$(printf '%s' "$admin_url" | sed -n 's|^postgresql://\([^:/@]*\).*|\1|p')
admin_rest=${admin_url#*@}

# Restart safety.
#
# This script rotates the role passwords to the configured secrets. If the admin
# connection authenticates *as* one of those roles — the normal case when
# ADMIN_DATABASE_URL is the warba_migrate URL — then after the first successful run its
# own credentials are stale, and every later start would fail before doing anything.
#
# So: if the supplied admin URL does not authenticate, fall back to the same user with
# the configured password. One of the two is correct on any given start.
#
# On a managed host the admin is usually a separate superuser (Railway uses `postgres`)
# and this never triggers.
admin_password_for() {
    case "$1" in
        warba_migrate) printf '%s' "$WARBA_MIGRATE_PASSWORD" ;;
        warba_app)     printf '%s' "$WARBA_APP_PASSWORD" ;;
        *)             printf '' ;;
    esac
}

if ! psql "$admin_url" -q -c 'SELECT 1' >/dev/null 2>&1; then
    fallback_password=$(admin_password_for "$admin_user")
    if [ -n "$fallback_password" ]; then
        log "admin credentials rejected; retrying with the configured password for $admin_user"
        admin_url="postgresql://${admin_user}:${fallback_password}@${admin_rest}"
        psql "$admin_url" -q -c 'SELECT 1' >/dev/null 2>&1 \
            || die "cannot connect as $admin_user with either the supplied or configured password"
    else
        die "cannot connect using ADMIN_DATABASE_URL (user: ${admin_user:-unknown})"
    fi
fi

# ---------------------------------------------------------------- 1. roles
log "provisioning database roles"
psql "$admin_url" -v ON_ERROR_STOP=1 -q -f scripts/create_roles.sql \
    || die "could not create roles"

# Passwords come from the environment, never from the SQL file — create_roles.sql
# carries local development values and is committed.
#
# Passwords are expected to be URL-safe (generate with `secrets.token_urlsafe`), since
# they are substituted into connection URLs unencoded.
log "setting role passwords from environment"
printf '%s\n%s\n' \
    "ALTER ROLE warba_migrate WITH PASSWORD '${WARBA_MIGRATE_PASSWORD}';" \
    "ALTER ROLE warba_app     WITH PASSWORD '${WARBA_APP_PASSWORD}';" \
    | psql "$admin_url" -v ON_ERROR_STOP=1 -q \
    || die "could not set role passwords"

# The ALTER above may have invalidated this connection's own credentials — see the
# restart-safety note at the top. Re-point it at the password we just set.
fallback_password=$(admin_password_for "$admin_user")
[ -n "$fallback_password" ] && admin_url="postgresql://${admin_user}:${fallback_password}@${admin_rest}"

# ------------------------------------------------------------ 2. migrations
log "running migrations"
alembic upgrade head || die "migrations failed"

# ------------------------------------------------- 3. the audit grant, again
# create_roles.sql ran before audit_event existed, so its grant was a no-op. This is
# the call that actually applies it.
log "applying audit grants"
psql "$admin_url" -v ON_ERROR_STOP=1 -q -c "SELECT apply_audit_grants();" \
    || die "could not apply audit grants"

# Verify rather than assume. A deployment that merely *believes* its audit trail is
# append-only is the failure this whole design exists to prevent.
log "verifying audit immutability"
has_update=$(psql "$admin_url" -tAc \
    "SELECT count(*) FROM information_schema.table_privileges
      WHERE grantee = 'warba_app' AND table_name = 'audit_event'
        AND privilege_type IN ('UPDATE','DELETE','TRUNCATE');")

[ "$has_update" = "0" ] \
    || die "warba_app holds UPDATE/DELETE/TRUNCATE on audit_event ($has_update grant(s)). Refusing to start."
log "verified: warba_app cannot modify or delete audit records"

# ------------------------------------------------------------------ 4. seed
if [ "${SEED_ON_START:-false}" = "true" ]; then
    log "seeding synthetic fixtures (idempotent)"
    python -m app.fixtures.seed || log "seed skipped or already applied"
fi

# ----------------------------------------------------------------- 5. serve
log "starting API on :$PORT"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
