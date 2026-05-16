"""Public service entrypoints for the story world runtime.

The package is intentionally split into service modules:

- WorldGenerator creates worlds and initializes time/space nodes.
- StoryContextBuilder reads storage into a compact world context.
- InformationCollector builds the story-agent context.
- CharacterManager owns protagonist/roster lifecycle.
- StorySessionManager advances interactive sessions.
"""

from .config import WorldGeneratorConfig
from .generator import WorldGenerator
from .agents import OpenAIJsonAgent
from .context import StoryContextBuilder
from .characters import CharacterManager
from .collector import InformationCollector
from .story import StorySessionManager

__all__ = [
    "WorldGeneratorConfig",
    "WorldGenerator",
    "OpenAIJsonAgent",
    "StoryContextBuilder",
    "CharacterManager",
    "InformationCollector",
    "StorySessionManager",
]
