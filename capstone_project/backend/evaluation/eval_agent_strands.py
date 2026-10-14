from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands_tools import calculator
import json

MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

@tool
def get_weather(location: str) -> dict:
    """Get current weather for a location. Returns a mock response for this demo."""
    # Simplified mock — real implementation would call a weather API
    weather_data = {
        "location": location,
        "temperature": "22°C",
        "condition": "Partly cloudy",
        "humidity": "65%"
    }
    return weather_data

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=MODEL_ID)

agent = Agent(
    model=model,
    tools=[calculator, get_weather],
    system_prompt=(
        "You are a helpful assistant. You can perform math calculations "
        "and check the weather. Stay focused on these topics only."
    )
)

@app.entrypoint
def invoke_agent(payload):
    prompt = payload.get("prompt", "")
    result = agent(prompt)
    return str(result)

if __name__ == "__main__":
    app.run()
