"""
Resume request/response schemas (pydantic v2).

WILL CONTAIN:
- ParseRequest { text, fileType }
- ParseResponse { fullName, email, phone, location, summary, skills[],
                  experiences[], educations[] }  (used to validate Qwen output)
- ScoreRequest { text, targetRole? }
- ScoreResponse { atsScore, qualityScore, breakdown, suggestions[] }

Contract: BUILD_PLAN.md §4.1 / §4.2. NO LOGIC YET — placeholder.
"""
