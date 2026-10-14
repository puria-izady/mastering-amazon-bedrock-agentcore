from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import json

# Initialize AgentCore Runtime App
app = BedrockAgentCoreApp()

# Define travel tools
@tool
def get_travel_preferences():
    """Get user's travel preferences from memory"""
    return {
        "hotel_type": "mid-range",
        "food_preference": "vegetarian",
        "budget_range": "moderate"
    }

@tool
def calculate_budget(total_budget: int, days: int):
    """Calculate daily budget allocation for travel"""
    daily_budget = total_budget / days
    allocation = {
        "flights": total_budget * 0.24,
        "hotels": total_budget * 0.36,
        "food": total_budget * 0.20,
        "activities": total_budget * 0.16,
        "buffer": total_budget * 0.04
    }
    return {
        "daily_budget": daily_budget,
        "allocation": allocation
    }

@tool
def get_destination_info(destination: str):
    """Get basic information about a travel destination"""
    destinations = {
        "rome": {
            "country": "Italy",
            "currency": "EUR",
            "language": "Italian",
            "attractions": ["Colosseum", "Vatican", "Trevi Fountain"]
        },
        "florence": {
            "country": "Italy",
            "currency": "EUR",
            "language": "Italian",
            "attractions": ["Uffizi Gallery", "Ponte Vecchio", "Duomo"]
        },
        "venice": {
            "country": "Italy",
            "currency": "EUR",
            "language": "Italian",
            "attractions": ["St. Mark's Square", "Grand Canal", "Doge's Palace"]
        }
    }
    return destinations.get(destination.lower(), {"error": "Destination not found"})

# Initialize model and agent
model_id = "global.anthropic.claude-haiku-5-5"
model = BedrockModel(model_id=model_id)

system_prompt = """
You are an AI Travel Companion specializing in planning trips to Italy. 
Your expertise includes:
- Flight and hotel recommendations
- Budget optimization and allocation
- Destination information and attractions
- Personalized recommendations based on user preferences

Always ask clarifying questions to better understand the user's needs.
Be helpful, friendly, and provide detailed explanations for your recommendations.
Remember user preferences and reference them in future interactions.
"""

travel_agent = Agent(
    model=model,
    tools=[get_travel_preferences, calculate_budget, get_destination_info],
    system_prompt=system_prompt
)

@app.entrypoint
def invoke_travel_agent(payload):
    """AgentCore Runtime entrypoint for travel agent"""
    user_input = payload.get("prompt", "")
    print(f"User input: {user_input}")
    
    response = travel_agent(user_input)
    agent_response = response.message['content'][0]['text']
    
    return agent_response

if __name__ == "__main__":
    app.run()
