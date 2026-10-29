from __future__ import annotations

import os

from quilrai_assessment.task2_security_gateway.auth import issue_demo_token

secret = os.getenv("JWT_SECRET", "dev-only-change-me-please")
print("viewer:")
print(issue_demo_token("demo-viewer", "viewer", secret))
print("\nadmin:")
print(issue_demo_token("demo-admin", "admin", secret))
