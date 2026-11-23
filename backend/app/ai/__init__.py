"""Optional generative-AI assistant (Claude) that drafts plain-language text for staff and students.

Design rules (see docs/ai_integration_plan.md):
- Off by default; with AI disabled or failing, the rest of SAEWS works exactly as before.
- Only pseudonymized data reaches the model (``privacy.py`` is the single gateway).
- Everything generated is a *draft* for a human to review; nothing is sent or applied automatically.
- Every call is audited and stored in ``ai_outputs``.
"""
