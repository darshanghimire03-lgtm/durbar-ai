"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI/WSGI object named `app` in this file.
All routes are forwarded here by the rewrite rule in vercel.json.
"""
from app.main import app  # noqa: F401
