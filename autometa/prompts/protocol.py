PROTOCOL_DRAFT_PROMPT = """\
You are a systematic review methodologist. Convert the user's natural-language
research question into a reviewable PICO protocol and recommended outcome list.

# User research question
{research_question}

# Task
Return a concise structured protocol draft that a human reviewer can edit.
- Population should describe eligible participants or units of analysis.
- Intervention / Exposure should describe the exposure, program, intervention, or index factor.
- Comparison should describe the comparator if inferable; otherwise propose a sensible comparator such as usual care, placebo, no intervention, or non-exposed control.
- Outcomes should include the most important primary and secondary outcomes.
- Recommended outcomes should be specific, measurable, and suitable for later data extraction/meta-analysis.
- Do not invent highly specific eligibility constraints that are not implied by the question.
- If the question is ambiguous, still provide a useful draft and note ambiguity in rationale.

Respond by calling the `submit_protocol_draft` function.
"""

PROTOCOL_DRAFT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_protocol_draft",
        "description": "Submit a reviewable PICO protocol draft and recommended outcomes.",
        "parameters": {
            "type": "object",
            "properties": {
                "pico": {
                    "type": "object",
                    "properties": {
                        "P": {"type": "string", "description": "Population / problem"},
                        "I": {
                            "type": "string",
                            "description": "Intervention / exposure",
                        },
                        "C": {"type": "string", "description": "Comparison / control"},
                        "O": {
                            "type": "string",
                            "description": "Primary and secondary outcomes",
                        },
                    },
                    "required": ["P", "I", "C", "O"],
                },
                "recommended_outcomes": {
                    "type": "array",
                    "description": "Specific recommended outcomes for human review.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "primary",
                                    "secondary",
                                    "safety",
                                    "exploratory",
                                ],
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["name", "type", "rationale"],
                    },
                },
                "rationale": {
                    "type": "string",
                    "description": "Brief explanation of the draft and any ambiguity.",
                },
            },
            "required": ["pico", "recommended_outcomes", "rationale"],
        },
    },
}
