from __future__ import annotations


WORLD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "world_overview": {"type": "string"},
        "world_rules": {"type": "array", "items": {"type": "string"}},
        "space_structure_summary": {"type": "string"},
        "history_summary": {"type": "string"},
    },
    "required": [
        "world_overview",
        "world_rules",
        "space_structure_summary",
        "history_summary",
    ],
}


SPACE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    "name": {"type": "string"},
                    "geography": {"type": "string"},
                    "summary": {"type": "string"},
                    "detail": {"type": ["string", "null"]},
                    "faction": {"type": ["string", "null"]},
                    "cities": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "summary": {"type": "string"},
                            },
                            "required": ["name", "summary"],
                        },
                    },
                    "creatures": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "summary": {"type": "string"},
                            },
                            "required": ["name", "summary"],
                        },
                    },
                    "population": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "count": {"type": "string"},
                            "distribution": {"type": "string"},
                        },
                        "required": ["count", "distribution"],
                    },
                },
                "required": [
                    "path",
                    "name",
                    "geography",
                    "summary",
                    "detail",
                    "faction",
                    "cities",
                    "creatures",
                    "population",
                ],
            },
        }
    },
    "required": ["nodes"],
}


HISTORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    "calendar": {"type": "string"},
                    "summary": {"type": "string"},
                    "detail": {"type": ["string", "null"]},
                    "ongoing_events": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "public_events": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "name": {"type": "string"},
                                        "summary": {"type": "string"},
                                    },
                                    "required": ["name", "summary"],
                                },
                            },
                            "personal_events": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "name": {"type": "string"},
                                        "summary": {"type": "string"},
                                    },
                                    "required": ["name", "summary"],
                                },
                            },
                        },
                        "required": ["public_events", "personal_events"],
                    },
                },
                "required": ["path", "calendar", "summary", "detail", "ongoing_events"],
            },
        }
    },
    "required": ["nodes"],
}


SPACE_ENRICH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "node": SPACE_SCHEMA["properties"]["nodes"]["items"],
    },
    "required": ["node"],
}


HISTORY_ENRICH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "node": HISTORY_SCHEMA["properties"]["nodes"]["items"],
    },
    "required": ["node"],
}


CHARACTER_INIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "role": {"type": "string", "enum": ["protagonist", "other"]},
                    "summary": {"type": "string"},
                    "detail": {"type": "string"},
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "target_id": {"type": "string"},
                                "type": {"type": "string"},
                                "closeness": {"type": "number", "minimum": 0, "maximum": 1},
                                "summary": {"type": "string"},
                            },
                            "required": ["target_id", "type", "closeness", "summary"],
                        },
                    },
                    "active": {"type": "boolean"},
                },
                "required": ["id", "name", "role", "summary", "detail", "relationships", "active"],
            },
        }
    },
    "required": ["characters"],
}


CHARACTER_ADDITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "characters": {
            "type": "array",
            "items": CHARACTER_INIT_SCHEMA["properties"]["characters"]["items"],
        }
    },
    "required": ["characters"],
}


INTRO_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intro": {"type": "string"},
        "known_world": {"type": "array", "items": {"type": "string"}},
        "mysteries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intro", "known_world", "mysteries"],
}


STORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "story": {"type": "string"},
        "choices": {
            "type": "array",
            "minItems": 0,
            "maxItems": 0,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "intent": {"type": "string"},
                },
                "required": ["id", "text", "intent"],
            },
        },
        "new_events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "summary": {"type": "string"},
                    "impact": {"type": "string"},
                },
                "required": ["name", "summary", "impact"],
            },
        },
        "state_notes": {"type": "string"},
    },
    "required": ["story", "choices", "new_events", "state_notes"],
}


ENDING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ending": {"type": "string"},
        "final_state": {"type": "string"},
        "resolved_events": {"type": "array", "items": {"type": "string"}},
        "open_mysteries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ending", "final_state", "resolved_events", "open_mysteries"],
}
