#!/usr/bin/env python3
"""
Travel Agent with Google Drive Integration
Uses AgentCore Identity for OAuth2 authentication with Google Drive
"""

import os
import json
import asyncio
import io
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.identity.auth import requires_access_token
from oauth2_callback_server import get_oauth2_callback_url

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# Environment configuration
os.environ["STRANDS_OTEL_ENABLE_CONSOLE_EXPORT"] = "true"
os.environ["OTEL_PYTHON_EXCLUDED_URLS"] = "/ping,/invocations"

# Google Drive API scope
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Global variable to store access token
google_access_token: Optional[str] = None

@tool(
    name="save_itinerary_to_drive",
    description="Saves a travel itinerary to Google Drive as a text file"
)
def save_itinerary_to_drive(destination: str, itinerary_content: str) -> str:
    """
    Save travel itinerary to Google Drive.
    
    Args:
        destination: Travel destination name
        itinerary_content: The itinerary content to save
    
    Returns:
        str: Success message with file link or error message
    """
    global google_access_token
    
    if not google_access_token:
        return json.dumps({
            "message": "Google Drive authentication is required. Please wait while we set up the authorization.",
            "success": False
        })
    
    try:
        # Create credentials from access token
        creds = Credentials(token=google_access_token, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        
        # Create filename
        filename = f"{destination.lower().replace(' ', '_')}_itinerary_{datetime.now().strftime('%Y%m%d')}.txt"
        
        # Create file metadata
        file_metadata = {'name': filename}
        
        # Create media upload
        media = MediaIoBaseUpload(
            io.BytesIO(itinerary_content.encode('utf-8')),
            mimetype='text/plain'
        )
        
        # Upload file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        return json.dumps({
            "success": True,
            "message": f"✅ Itinerary saved to Google Drive: {file.get('name')}",
            "file_id": file.get('id'),
            "view_link": file.get('webViewLink')
        })
        
    except HttpError as error:
        return json.dumps({
            "success": False,
            "error": f"Google Drive API error: {str(error)}"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error saving to Google Drive: {str(e)}"
        })

# Initialize the agent
agent = Agent(
    model="global.anthropic.claude-haiku-5-5",
    tools=[save_itinerary_to_drive],
    system_prompt="""
You are a helpful travel planning assistant with the ability to save itineraries to Google Drive.
When users ask you to create travel plans, generate detailed itineraries and offer to save them to Google Drive.
Always format itineraries clearly with day-by-day breakdowns, times, and activities.
"""
)

# Initialize app
app = BedrockAgentCoreApp()

class StreamingQueue:
    def __init__(self):
        self.finished = False
        self.queue = asyncio.Queue()
        
    async def put(self, item: str) -> None:
        await self.queue.put(item)

    async def finish(self) -> None:
        self.finished = True
        await self.queue.put(None)

    async def stream(self) -> AsyncGenerator[str, None]:
        while True:
            item = await self.queue.get()
            if item is None and self.finished:
                break
            yield item

queue = StreamingQueue()

async def on_auth_url(url: str) -> None:
    """Handle authorization URL callback."""
    print(f"Authorization url: {url}")
    await queue.put(f"Authorization url: {url}")

async def agent_task(user_message: str) -> None:
    """Execute the agent task with authentication handling."""
    try:
        await queue.put("Begin agent execution")
        
        # Call the agent first to see if it needs authentication
        response = agent(user_message)
        
        # Extract text content from the response structure
        response_text = ""
        if isinstance(response.message, dict):
            content = response.message.get('content', [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        response_text += item['text']
        else:
            response_text = str(response.message)
        
        # Check if the response indicates authentication is required
        auth_keywords = [
            "authentication", "authorize", "authorization", "auth", 
            "sign in", "login", "access", "permission", "credential",
            "need authentication", "requires authentication"
        ]
        needs_auth = any(keyword.lower() in response_text.lower() for keyword in auth_keywords)
       
        if needs_auth:
            await queue.put("Authentication required for Google Drive access. Starting authorization flow...")
            
            # Trigger the 3LO authentication flow
            try:
                global google_access_token
                google_access_token = await get_google_drive_token(access_token='')
                await queue.put("Authentication successful! Retrying your request...")
                
                # Retry the agent call now that we have authentication
                response = agent(user_message)
            except Exception as auth_error:
                print(f"auth_error: {auth_error}")
                await queue.put(f"Authentication failed: {str(auth_error)}")
        
        await queue.put(response.message)
        await queue.put("End agent execution")
    except Exception as e:
        await queue.put(f"Error: {str(e)}")
    finally:
        await queue.finish()

@requires_access_token(
    provider_name="google-drive-provider",
    scopes=SCOPES,
    auth_flow='USER_FEDERATION',
    on_auth_url=on_auth_url,
    force_authentication=True,
    callback_url=get_oauth2_callback_url()
)
async def get_google_drive_token(*, access_token: str) -> str:
    """Get Google Drive access token."""
    global google_access_token
    google_access_token = access_token
    return access_token

@app.entrypoint
async def agent_invocation(payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """Main entrypoint for agent invocations."""
    user_message = payload.get(
        "prompt", 
        "Hello! I'm your travel planning assistant. How can I help you plan your next trip?"
    )
    
    # Create and start the agent task
    task = asyncio.create_task(agent_task(user_message))
    
    # Stream results
    async def stream_with_task() -> AsyncGenerator[str, None]:
        async for item in queue.stream():
            yield item
        await task
    
    return stream_with_task()

if __name__ == "__main__":
    app.run()
