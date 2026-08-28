# Backend container — FastAPI + PostgreSQL client.
#
# Two stages so the wheels are built with a compiler that the runtime image never
# ships. psycopg[binary] and bcrypt bring their own wheels, so the runtime needs no
# build toolchain at all.
#
# Deliberately no GTK/Cairo/Pango: PDF export is not implemented (export.py returns
# 501) and weasyprint is not a dependency. See backend/pyproject.toml.

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim AS build

WORKDIR /build

# Copy only what the dependency resolution needs first, so a code change does not
# invalidate the dependency layer.
COPY pyproject.toml ./
COPY app/__init__.py ./app/

RUN pip install --no-cache-dir --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels .

# -------------------------------------------------------------- runtime stage
FROM python:3.12-slim AS runtime

# postgresql-client supplies psql, which the start script uses to apply
# create_roles.sql. Without it the audit table's privilege model — the guarantee that
# the application role cannot UPDATE or DELETE an audit event — would silently not be
# applied, and the deployment would look healthy while missing its main control.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels

COPY . .

# Run as a non-root user. Nothing here needs to write to the image.
RUN useradd --create-home --uid 10001 warba && chown -R warba:warba /app
USER warba

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

EXPOSE 8000

# Railway injects $PORT. Default to 8000 so the image also runs locally unchanged.
CMD ["sh", "-c", "./scripts/start.sh"]
