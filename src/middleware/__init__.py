# SPDX-License-Identifier: AGPL-3.0-or-later

"""Middleware package -- request-pipeline middleware modules.

Hosts spec 019's NetworkRateLimitMiddleware (per-IP token-bucket rate
limiter that runs BEFORE auth/bcrypt). Future request-pipeline
middleware lands here too.
"""
