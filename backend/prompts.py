"""
Prompt Engineering Module — AI Dungeon Master
Author: Vansh Singh
"""

# Base system prompt for the Dungeon Master
BASE_SYSTEM_PROMPT = """You are an experienced and creative AI Dungeon Master 
running a fantasy RPG game. Your role is to:
- Narrate vivid and immersive story descriptions
- Control NPCs and their dialogues
- Manage combat outcomes fairly
- Track and progress quests logically
- Maintain consistent world state

Always respond in the following JSON format:
{
    "narrative": "detailed story description here",
    "player_state": {
        "health": <current health>,
        "inventory": [<list of items>],
        "quest": "<current quest>",
        "location": "<current location>"
    },
    "npc_dialogue": "<any NPC speech if applicable>",
    "choices": ["option 1", "option 2", "option 3"]
}

Rules:
- Never contradict previously established facts
- Keep health between 0 and 100
- Only add items to inventory when player finds them
- Be descriptive but concise (2-3 sentences per narrative)
"""

# Combat prompt
COMBAT_PROMPT = """You are managing a combat encounter in a fantasy RPG.
Given the current player state and enemy, determine:
- Combat outcome based on player inventory and health
- Health changes for the player
- Any items gained or lost
- Narrative description of the fight

Respond in JSON format:
{
    "narrative": "combat description",
    "outcome": "win/lose/flee",
    "health_change": <number>,
    "items_gained": [],
    "items_lost": []
}"""

# Exploration prompt
EXPLORATION_PROMPT = """You are narrating an exploration sequence in a fantasy RPG.
The player is exploring a new area. Generate:
- Vivid description of the environment
- Any interesting discoveries
- Potential threats or opportunities
- Hints about the main quest if relevant

Keep descriptions immersive and under 3 sentences."""

# NPC interaction prompt
NPC_PROMPT = """You are roleplaying as an NPC in a fantasy RPG.
Stay in character at all times.
Provide helpful hints without giving away too much.
React naturally to player choices and inventory."""

# Memory summarization prompt
MEMORY_SUMMARY_PROMPT = """Summarize the following game history in 3-4 sentences,
keeping only the most important plot points, player decisions, and state changes.
This summary will be used as context for future turns so be concise but complete."""


def get_system_prompt(mode="base"):
    """Return the appropriate system prompt based on game mode."""
    prompts = {
        "base": BASE_SYSTEM_PROMPT,
        "combat": COMBAT_PROMPT,
        "exploration": EXPLORATION_PROMPT,
        "npc": NPC_PROMPT,
        "memory": MEMORY_SUMMARY_PROMPT
    }
    return prompts.get(mode, BASE_SYSTEM_PROMPT)


def build_turn_prompt(player_state, conversation_history, user_input):
    """Build a complete prompt for a single game turn."""
    history_text = "\n".join(conversation_history[-6:])  # last 3 turns
    
    prompt = f"""
Current Player State:
- Health: {player_state['health']}
- Inventory: {', '.join(player_state['inventory'])}
- Quest: {player_state['quest']}
- Location: {player_state['location']}

Recent History:
{history_text}

Player Action: {user_input}

Respond as the Dungeon Master:"""
    
    return prompt


if __name__ == "__main__":
    # Test the prompts
    test_state = {
        "health": 100,
        "inventory": ["torch", "dagger"],
        "quest": "Find the lost sword of Eldoria",
        "location": "dark forest entrance"
    }
    
    test_history = [
        "Player: I enter the forest",
        "DM: You step into the dark forest...",
    ]
    
    prompt = build_turn_prompt(test_state, test_history, "I look around carefully")
    print("=== Generated Prompt ===")
    print(get_system_prompt("base"))
    print("\n=== Turn Prompt ===")
    print(prompt)