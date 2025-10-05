 
import asyncio
import uuid
from google.adk.runners import Runner
from google.adk.events import Event
import os
from sentient_agent.memory.postgres_memory_service import PostgresSessionService
from google.adk.sessions import InMemorySessionService,DatabaseSessionService
from sentient_agent.agent import root_agent as sentient_agent
from google.adk.agents.llm_agent import LlmAgent
from google.genai.types import Part, Content
from google.genai.types import FunctionResponse
from google.adk.tools.tool_confirmation import ToolConfirmation
from typing import AsyncGenerator, Dict, Any

ADK_AUTH_FN = "adk_request_credential"
ADK_CONFIRMATION_FN = 'adk_request_confirmation'

# --- 1. CONSTRUCT THE DATABASE URL ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# The format is crucial: 'dialect+driver://user:password@host:port/database'
db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
# --- 2. Configuration & Initialization ---

# Use the built-in in-memory session service for simple testing [3].
# All data is lost when the application restarts [3].
# session_service = InMemorySessionService()  
# session_service = PostgresSessionService()
session_service = DatabaseSessionService(db_url=db_url)
APP_NAME = "sentient_agent_app"
USER_ID = "user_123"
4
# Create the main Runner instance, configuring it with the agent and session service.
# Note: For programmatic runs, the Runner is typically created for the specific agent [14].
runner = Runner(
    app_name=APP_NAME,
    agent=sentient_agent, 
    session_service=session_service
) 
MINIMAL_AUTH_SCHEME_DICT = {"type": "http", "scheme": "bearer"} 

async def stream_and_parse_events(event_stream:AsyncGenerator[Event, None]):
    """
    Streams all events, prints them, and returns a 'pause signal' if one is detected.
    This function consolidates the event loop to avoid duplication.
    """
    async for event in event_stream:
        # Print all relevant event info for detailed debugging
        if event.content and event.content.parts:
            # Check all parts for text content
            for part in event.content.parts:
                if part.text:
                    text_chunk = part.text
                    # Print the text chunk, including the thoughts if they are streamed as text
                    print(text_chunk, end="", flush=True)
        function_calls = event.get_function_calls()
        
        if function_calls:
            for call in function_calls:
                print(f"\n[STATUS: TOOL CALL] Agent requests to execute: {call.name}")
                print(f"   | Arguments: {dict(call.args)}")
                if call.name == ADK_AUTH_FN:                    
                    auth_call_id = call.id
                    return {"type": "auth", "id": auth_call_id}
                if call.name == ADK_CONFIRMATION_FN:
                    confirmation_call_id = call.id
                    
                    # The arguments for ADK_CONFIRMATION_FN contain the requested ToolConfirmation object [5, 6]
                    tool_conf_data = call.args.get('toolConfirmation', {})
                    
                    # Extract the hint text from the payload
                    # Note: We assume toolConfirmation is structured or parsed JSON/Dict 
                    # containing the 'hint' field, as defined in the ToolConfirmation model [7, 8].
                    hint = tool_conf_data.get('hint', 'User confirmation required.')
                    
                    print(f"\n[STATUS] Agent requires confirmation (call_id: {confirmation_call_id})")
                    print(f"[PROMPT] {hint}")
                    
                    # Pause the execution stream and return the signal
                    return {"type": "confirm", "id": confirmation_call_id}
            

    print() # Final newline for clean output
    return None # No pause detected, task is complete or continuing

# --- 3. RESUME HANDLERS ---
async def handle_auth_resume(session_id: str, auth_call_id: str, password: str):
    """Resumes the agent after an authentication pause."""
    print(f"\n[CLIENT] Sending password back to resume...")
    CUSTOM_SUDO_KEY = "cli_sudo_password_prompt"
    
    print(f"\n[CLIENT] Sending password back to agent (call_id: {auth_call_id}) to resume task...")

    # 1. Package the user's password into an AuthCredential structure (HttpAuth/HttpCredentials)
    # Since this is a simple password, we model it as an HTTP Bearer token credential.
    user_credential_dict = {
        # AuthType must match AuthCredentialTypes.HTTP [4]
        "authType": "http", 
        "http": {
            "scheme": "bearer",
            "credentials": {"token": password} # Password provided here [2]
        }
    }
    
    # 2. Construct the FULL AuthConfig dictionary to satisfy validation.
    # It must include the original structural fields (auth_scheme) and the new credential.
    
 
    
    auth_config_content: Dict[str, Any] = {
        # REQUIRED structural fields:
        "authScheme": MINIMAL_AUTH_SCHEME_DICT, # Fills the missing field in validation [1]
        "credentialKey": CUSTOM_SUDO_KEY,       # Required for storage lookup [5, 6]
        
        # This field tells the framework what credential was successfully exchanged/collected
        # (This is where the user's password data is located)
        "exchangedAuthCredential": user_credential_dict,
        
        # Optional: Include custom fields used for the initial prompt (good practice)
        "type": "sudo_password_prompt",
        "prompt_message": "  provide   sudo password "
    }
    auth_response = FunctionResponse(name=ADK_AUTH_FN, id=auth_call_id, response=auth_config_content)
    resume_content = Content(role='user', parts=[Part.from_function_response(auth_response)])
    return runner.run_async(user_id=USER_ID, session_id=session_id, new_message=resume_content)

async def handle_confirmation_resume(session_id: str, confirm_call_id: str, confirmed: bool):
    """Resumes the agent after a confirmation pause."""
    print(f"\n[CLIENT] Sending confirmation ('{ 'Yes' if confirmed else 'No' }') back to resume...")
     
    confirmation_payload = {
 
        "confirmed": confirmed
    }
    confirmation_response = FunctionResponse(
        name=ADK_CONFIRMATION_FN, 
        id=confirm_call_id, 
        response=confirmation_payload
    )
    resume_content = Content(role='user', parts=[Part.from_function_response(confirmation_response)])
    return runner.run_async(  user_id=USER_ID, session_id=session_id, new_message=resume_content)

# --- 4. MAIN AGENT TASK CONTROLLER ---
async def run_agent_task(user_input: str, session_id: str):
    """
    The main controller that runs the agent and manages the pause/resume lifecycle.
    """
    print(f"--- Running task for session: {session_id} ---")
    print(f"User Input: '{user_input}'")
    print("Agent Output:")
    user_content = Content(role="user", parts=[Part(text=user_input)])
    # Start the initial run
    event_stream = runner.run_async(  session_id=session_id, user_id=USER_ID,new_message=user_content)

    while event_stream:
        pause_signal = await stream_and_parse_events(event_stream)

        if pause_signal is None:
            # The event stream finished without pausing
            event_stream = None
            continue

        if pause_signal["type"] == "auth":
            password = input("Sudo Password Required: ")
            event_stream = await handle_auth_resume(session_id, pause_signal["id"], password)
        
        elif pause_signal["type"] == "confirm":
            choice = input("Confirm? [y/n]: ")
            confirmed = choice.lower().strip() == 'y'
            event_stream = await handle_confirmation_resume(session_id, pause_signal["id"], confirmed)

    print("--- Task Complete ---")

async def handle_auth_resume(app_name: str, user_id: str, session_id: str, auth_call_id: str, password: str):
    """Sends the user-provided password back to the runner to resume the paused agent."""
     # Constants must match the original request made by execute_shell_command
   
    CUSTOM_SUDO_KEY = "cli_sudo_password_prompt"
    
    print(f"\n[CLIENT] Sending password back to agent (call_id: {auth_call_id}) to resume task...")

    # 1. Package the user's password into an AuthCredential structure (HttpAuth/HttpCredentials)
    # Since this is a simple password, we model it as an HTTP Bearer token credential.
    user_credential_dict = {
        # AuthType must match AuthCredentialTypes.HTTP [4]
        "authType": "http", 
        "http": {
            "scheme": "bearer",
            "credentials": {"token": password} # Password provided here [2]
        }
    }
    
    # 2. Construct the FULL AuthConfig dictionary to satisfy validation.
    # It must include the original structural fields (auth_scheme) and the new credential.
    
 
    
    auth_config_content: Dict[str, Any] = {
        # REQUIRED structural fields:
        "authScheme": MINIMAL_AUTH_SCHEME_DICT, # Fills the missing field in validation [1]
        "credentialKey": CUSTOM_SUDO_KEY,       # Required for storage lookup [5, 6]
        
        # This field tells the framework what credential was successfully exchanged/collected
        # (This is where the user's password data is located)
        "exchangedAuthCredential": user_credential_dict,
        
        # Optional: Include custom fields used for the initial prompt (good practice)
        "type": "sudo_password_prompt",
        "prompt_message": "  provide   sudo password "
    }
    auth_response = FunctionResponse(name=ADK_AUTH_FN, id=auth_call_id, response=auth_config_content)
    # Explicitly constructing the Part object (Fix for previous TypeError)
    auth_response_part = Part(function_response=auth_response)
    response_content = Content(role='user', parts=[auth_response_part])


  

    event_stream = runner.run_async(
  
        user_id=USER_ID,
        session_id=session_id,
        new_message=response_content
    )
    # Stream the rest of the events from the resumed execution
    async for event in event_stream:
        if event.content and event.content.parts:
            # Check all parts for text content
            for part in event.content.parts:
                if part.text:
                    text_chunk = part.text
                    # Print the text chunk, including the thoughts if they are streamed as text
                    print(text_chunk, end="", flush=True)

# # --- 3. Programmatic Execution Logic ---
# async def run_agent_task(user_input: str, session_id: str):
#     """Runs the agent and handles the interactive pause/resume cycle for authentication."""
#     print(f"\n--- Running task for session: {session_id} ---")
#     print(f"User Input: {user_input}")
#     print("Agent Output: ", end="", flush=True)

#     # 1. Create the user input content object
#     user_content = Content(role="user", parts=[Part(text=user_input)])
    
#     # 2. Call runner.run_async, which is the primary method for execution [2, 18]
#     # This returns an asynchronous generator of Event objects [9, 19].
#     event_stream = runner.run_async(
#         user_id= USER_ID,
#         session_id=session_id,
#         new_message=user_content
#     )  
#     auth_required, auth_call_id = False, None
 
#     async for event in event_stream:
        
        
#         # 1. Look for Function Calls (Tool Request Status)
#         # These events signal the LLM asking to run a tool [5, 6].
#         function_calls = event.get_function_calls()
#         if function_calls:
#             for call in function_calls:
#                 print(f"\n[STATUS: TOOL CALL] Agent requests to execute: {call.name}")
#                 print(f"   | Arguments: {dict(call.args)}")
#                 if call.name == ADK_AUTH_FN:
#                     auth_required = True
#                     auth_call_id = call.id
#                     print(f"\n\n[CLIENT] PAUSE DETECTED. Agent requires sudo password (call_id: {auth_call_id}).")
#                     break
#         if auth_required: break

                    
#         # 2. Look for Function Responses (Tool Results/Perception)
#         # These events signal the result of the tool execution that the agent receives [5, 6].
#         function_responses = event.get_function_responses()
#         if function_responses:
#             for response in function_responses:
#                 print(f"\n[STATUS: TOOL RESULT] Agent received result for: {response.name}")
#                 if response.response:
#                     print(f"   | Result Status: {response.response.get('status', 'N/A')}")
#                     print(f"   | Full Output: {response.response.get('output', 'N/A')}")

#         # 3. Look for State Updates (Side Effects/Commitment)
#         # The Runner coordinates with Services to commit changes signaled here [10-12].
#         if event.actions and event.actions.state_delta:
#             print(f"\n[STATUS: STATE COMMIT] Runner confirmed changes: {event.actions.state_delta}")

#         # 4. Look for Text Content (Thoughts and Final Response)
#         # This handles streaming text chunks [5, 13].
#         if event.content and event.content.parts:
#             # Check all parts for text content
#             for part in event.content.parts:
#                 if part.text:
#                     text_chunk = part.text
#                     # Print the text chunk, including the thoughts if they are streamed as text
#                     print(text_chunk, end="", flush=True)
#     if auth_required and auth_call_id:
#             # --- THIS IS THE INTERACTIVE PART ---
#             sudo_password = input("Please enter your sudo password: ")
           

#             await handle_auth_resume(app_name=APP_NAME, user_id=USER_ID, session_id=session_id, auth_call_id=auth_call_id, password=sudo_password)
#         # After the loop finishes, we print a newline.
#     print("\n--- Task Complete ---")

async def main():
 
    # We will use a consistent session_id to test the agent's memory (persistence of state/history).
    # We generate a unique ID for each run for demonstration purposes.
    
    # Retrieve the session id if exists
    existing_sessions = await session_service.list_sessions(
        app_name=APP_NAME,
        user_id=USER_ID
    )
    if existing_sessions and len(existing_sessions.sessions) > 0:
        test_session = existing_sessions.sessions[0]
        print(f"Resuming existing session with id: {test_session.id}")
    else:
        print("Creating a new session")
        test_session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,            
        )

    test_session_id = test_session.id
    print(f"Using session_id: {test_session_id}")

    # await session_service.connect()

    # Scenario 1: Initial Question
    while True:
        user_input = input("Your Turn....  ")
        await run_agent_task(
            user_input=user_input,
            session_id=test_session_id
        )

    # Scenario 2: Follow-up question (should reference the context of ADK)
    # await run_agent_task(
    #     user_input="How can I verify that installation?",
    #     session_id=test_session_id
    # )
 
if __name__ == "__main__":
    # To run the async main function [2]
    asyncio.run(main())
 