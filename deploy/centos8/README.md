# CentOS 8.2 deployment

This directory contains the production deployment files for the AI tutor project.

- `Containerfile` builds the backend and bundled frontend on Python 3.11.
- `ai-tutor.service` keeps the Podman container running with systemd.
- `nginx.conf` exposes the application through port 80.
- `app.env.example` documents the required runtime environment variables.

Runtime data is stored outside the container in `/opt/ai-tutor/data`.

