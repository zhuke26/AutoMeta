"""
Direct PICO ranking prompt for fast screening.

The model evaluates a candidate record directly against the review PICO in one
function call. Missing abstract information should be scored as uncertain, not
as a mismatch. The downstream system ranks records by auditable P/I/C/O scores
and does not exclude records during this stage.
"""

PICO_SCORING_PROMPT = """\
# ROLE
You are a fast systematic-review ranking assistant.

# TASK
Score how well the candidate article matches the review PICO. Use only the
title and abstract. Do not make an include/exclude decision.

# REVIEW PICO
- Population / Problem: {P}
- Intervention / Exposure: {I}
- Comparator / Control: {C}
- Outcome: {O}

# CANDIDATE ARTICLE
Title: {title}
Abstract: {abstract}
Publication type: {publication_type}
Year: {year}
Journal: {journal}

# SCORING RULES
For each dimension P, I, C, and O, assign:
- 1 when the candidate clearly matches the review dimension.
- 0 when the evidence is absent, incomplete, ambiguous, or only partially related.
- -1 only when there is a clear and explicit contradiction.

Critical recall safeguards:
- Missing information in the title/abstract is 0, not -1.
- Comparator and outcome are often underreported in abstracts; do not mark C
  or O as -1 unless the abstract explicitly contradicts the review.
- Prefer 0 over -1 when evidence is borderline.
- Do not provide a free-form relevance score. The system will compute ranking
  from your P/I/C/O scores using equal weights.
- Keep evidence short. Do not write chain-of-thought. State only the observable
  title/abstract signal or "not reported".

# OUTPUT FORMAT
Call `submit_pico_score` with concise dimension evidence and the score.
"""


_SCORE_ENUM = {"type": "integer", "enum": [-1, 0, 1]}

PICO_SCORING_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_pico_score",
        "description": "Submit direct PICO dimension scores for one candidate article.",
        "parameters": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "description": "Dimension scores using 1, 0, or -1.",
                    "properties": {
                        "P": _SCORE_ENUM,
                        "I": _SCORE_ENUM,
                        "C": _SCORE_ENUM,
                        "O": _SCORE_ENUM,
                    },
                    "required": ["P", "I", "C", "O"],
                },
                "confidence": {
                    "type": "object",
                    "description": "Per-dimension confidence from 0.0 to 1.0.",
                    "properties": {
                        "P": {"type": "number", "minimum": 0, "maximum": 1},
                        "I": {"type": "number", "minimum": 0, "maximum": 1},
                        "C": {"type": "number", "minimum": 0, "maximum": 1},
                        "O": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["P", "I", "C", "O"],
                },
                "evidence": {
                    "type": "object",
                    "description": "Short evidence or missing-information note per dimension.",
                    "properties": {
                        "P": {"type": "string"},
                        "I": {"type": "string"},
                        "C": {"type": "string"},
                        "O": {"type": "string"},
                    },
                    "required": ["P", "I", "C", "O"],
                },
                "reasoning": {
                    "type": "string",
                    "description": "One short sentence summarizing the PICO match signals.",
                },
            },
            "required": ["scores", "confidence", "evidence", "reasoning"],
        },
    },
}
