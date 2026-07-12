"""
Generation router.

WILL CONTAIN (Phase 4):
- POST /api/v1/generate/cover-letter -> schemas.generate.CoverLetterResponse
- POST /api/v1/generate/interview    -> schemas.generate.InterviewResponse
Delegates to app.services.generate_service. Guarded by require_api_key.

Contract: BUILD_PLAN.md §4.4 / §4.5. NO LOGIC YET — placeholder.
"""
