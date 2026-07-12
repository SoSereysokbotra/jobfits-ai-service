"""
Resume parsing + scoring logic.

WILL CONTAIN:
- parse(text, file_type): load prompts/resume_parse.txt -> ollama.chat(json=True)
  -> json_repair -> validate against schemas.resume.ParseResponse.
- score(text, target_role): load prompts/resume_score.txt -> ollama.chat(json=True)
  -> validate against schemas.resume.ScoreResponse.

NO LOGIC YET — placeholder. See BUILD_PLAN.md §6 Phases 2-3.
"""
