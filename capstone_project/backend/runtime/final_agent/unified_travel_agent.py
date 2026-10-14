#!/usr/bin/env python3
"""
Unified Travel Agent - Combines all AgentCore components
Integrates Gateway MCP, Memory, Code Interpreter, Browser Tools, and OAuth
Uses environment variables for configuration (set during runtime deployment)
"""

import os
import json
import requests
from typing import Dict, Any

from strands import Agent, tool
from strands.models import BedrockModel
from strands_tools.code_interpreter import AgentCoreCodeInterpreter
from strands_tools.browser import AgentCoreBrowser
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from identity_helper import IdentityHelper

# Configuration from environment variables
REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-haiku-5-5")

# Gateway configuration from environment
GATEWAY_ID = os.environ.get("GATEWAY_ID")
GATEWAY_MCP_ENDPOINT = os.environ.get("GATEWAY_MCP_ENDPOINT")
GATEWAY_TOKEN_ENDPOINT = os.environ.get("GATEWAY_TOKEN_ENDPOINT")
GATEWAY_OAUTH_CLIENT_ID = os.environ.get("GATEWAY_OAUTH_CLIENT_ID")
GATEWAY_OAUTH_CLIENT_SECRET = os.environ.get("GATEWAY_OAUTH_CLIENT_SECRET")
GATEWAY_OAUTH_SCOPE = os.environ.get("GATEWAY_OAUTH_SCOPE")

# Memory configuration from environment
MEMORY_ID = os.environ.get("MEMORY_ID")
MEMORY_USER_ID = os.environ.get("MEMORY_USER_ID", "default-user")
MEMORY_SESSION_ID = os.environ.get("MEMORY_SESSION_ID", "default-session")

# Initialize tools
code_interpreter = AgentCoreCodeInterpreter(region=REGION)
browser_tool = AgentCoreBrowser(region=REGION)
memory_client = MemoryClient(region_name=REGION) if MEMORY_ID else None
identity_helper = IdentityHelper(region=REGION)

def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Internal helper to call MCP gateway tools"""
    if not GATEWAY_MCP_ENDPOINT:
        return json.dumps({"error": "Gateway not configured"})
    
    try:
        # Get access token
        token_response = requests.post(
            GATEWAY_TOKEN_ENDPOINT,
            data={
                "grant_type": "client_credentials",
                "client_id": GATEWAY_OAUTH_CLIENT_ID,
                "client_secret": GATEWAY_OAUTH_CLIENT_SECRET,
                "scope": GATEWAY_OAUTH_SCOPE
            }
        )
        
        if token_response.status_code != 200:
            return json.dumps({"error": "Authentication failed"})
        
        access_token = token_response.json().get("access_token")
        
        # Call MCP endpoint
        response = requests.post(
            GATEWAY_MCP_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "jsonrpc": "2.0",
                "id": f"unified-{tool_name}",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            return json.dumps(result.get("result", {}))
        else:
            return json.dumps({"error": f"API call failed: {response.status_code}"})
            
    except Exception as e:
        return json.dumps({"error": f"Error calling gateway API: {str(e)}"})

@tool
def search_flights(origin: str, destination: str) -> str:
    """Search for flights between two airports on a specific date
    
    Args:
        dep_iata: Filter by departure IATA code (e.g., SFO).
        arr_iata: Filter by arrival IATA code (e.g., DFW).
    """
    return _call_mcp_tool(
        "FlightSearch___getFlights",
        {"dep_iata": origin, "arr_iata": destination}
    )


@tool
def get_weather(location: str, units: str = "metric") -> str:
    """Get current weather for a location
    
    Args:
        location: City name and country code (e.g., 'Rome,IT', 'Paris,FR', 'New York,US')
        units: Temperature units - 'metric' (Celsius) or 'imperial' (Fahrenheit)
    """
    return _call_mcp_tool(
        "WeatherSearch___getCurrentWeather",
        {"q": location, "units": units}
    )

@tool
def convert_currency(from_currency: str, to_currency: str) -> str:
    """Get current exchange rate between two currencies
    
    Args:
        from_currency: Source currency code (e.g., 'USD', 'EUR', 'GBP')
        to_currency: Target currency code (e.g., 'EUR', 'USD', 'JPY')
    """
    # Retrieve API key from credential provider
    api_key = identity_helper.get_exchangerate_api_key()
    
    if not api_key:
        return json.dumps({"error": "ExchangeRate API key not available"})
    
    return _call_mcp_tool(
        "ExchangeRate___convertCurrency",
        {
            "api_key": api_key,
            "from_currency": from_currency,
            "to_currency": to_currency
        }
    )

@tool
def get_user_preferences() -> str:
    """Retrieve user travel preferences from memory"""
    if not memory_client or not MEMORY_ID:
        return "Memory not configured - missing MEMORY_ID environment variable"
    
    try:
        memories = memory_client.retrieve_memories(
            memory_id=MEMORY_ID,
            namespace=f"travel/user/{MEMORY_USER_ID}/preferences",
            query="travel preferences",
            top_k=5
        )
        
        preferences = []
        for memory in memories:
            if isinstance(memory, dict) and 'content' in memory:
                content = memory['content']
                if isinstance(content, dict) and 'text' in content:
                    preferences.append(content['text'])
        
        return json.dumps({
            "preferences": preferences,
            "user_id": MEMORY_USER_ID
        })
        
    except Exception as e:
        return f"Error retrieving preferences: {str(e)}"

@tool
def save_travel_memory(content: str, memory_type: str = "semantic") -> str:
    """Save travel information to memory"""
    if not memory_client or not MEMORY_ID:
        return "Memory not configured - missing MEMORY_ID environment variable"
    
    try:
        memory_client.create_event(
            memory_id=MEMORY_ID,
            actor_id=MEMORY_USER_ID,
            session_id=MEMORY_SESSION_ID,
            messages=[(content, "ASSISTANT")]
        )
        return "Memory saved successfully"
    except Exception as e:
        return f"Error saving memory: {str(e)}"

# Create unified agent
model = BedrockModel(model_id=MODEL_ID)

unified_agent = Agent(
    model=model,
    tools=[
        search_flights,
        get_weather,
        convert_currency,
        get_user_preferences,
        save_travel_memory,
        #code_interpreter.code_interpreter,
        #browser_tool.browser
    ],
    system_prompt="""
You are a comprehensive AI Travel Companion with access to:

1. **Flight Search**: search_flights(origin, destination) - Find flights between airports
2. **Weather**: get_weather(location, units) - Get current weather for a city
3. **Currency**: convert_currency(from_currency, to_currency) - Get exchange rates
4. **Memory**: get_user_preferences() and save_travel_memory(content) - Store/retrieve preferences

Always:
- Check user preferences first using get_user_preferences()
- Use real APIs for current flight, hotel, weather, and currency information
- Provide comprehensive travel planning with budget considerations
- Save important travel decisions to memory

Provide comprehensive, personalized travel planning assistance.
"""
)

# Initialize AgentCore app
app = BedrockAgentCoreApp()

@app.entrypoint
def invoke_unified_agent(payload: Dict[str, Any]) -> str:
    """Unified agent entrypoint"""
    user_input = payload.get("prompt", "Hello! How can I help you plan your travel?")
    
    try:
        response = unified_agent(user_input)
        
        # Extract response text
        if isinstance(response.message, dict):
            content = response.message.get('content', [])
            if isinstance(content, list) and content:
                return content[0].get('text', str(response.message))
        
        return str(response.message)
        
    except Exception as e:
        return f"Error processing request: {str(e)}"

if __name__ == "__main__":
    app.run()
