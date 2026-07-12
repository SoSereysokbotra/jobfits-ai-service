"""
Resume router.

WILL CONTAIN:
- POST /api/v1/resume/parse  (Phase 2) -> schemas.resume.ParseResponse
- POST /api/v1/resume/score  (Phase 3) -> schemas.resume.ScoreResponse
Delegates to app.services.resume_service. Guarded by require_api_key.

Contract: BUILD_PLAN.md §4.1 / §4.2. NO LOGIC YET — placeholder.
"""
