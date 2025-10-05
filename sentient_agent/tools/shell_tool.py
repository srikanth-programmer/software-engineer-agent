import subprocess
import shlex
import shutil
from google.adk.sessions import Session
from google.adk.tools import ToolContext
from google.adk.auth.auth_schemes import AuthScheme, AuthSchemeType # Required for AuthConfig structure
from google.adk.auth.auth_tool import AuthConfig
from google.adk.auth.auth_credential import AuthCredential
from fastapi.openapi.models import HTTPBearer
from typing import Optional
PASSWORD_STATE_KEY = "user_sudo_password"
CUSTOM_SUDO_KEY = "cli_sudo_password_prompt" 


MINIMAL_AUTH_SCHEME_INSTANCE = HTTPBearer(scheme="bearer") 
auth_config_params = {
    "auth_scheme": MINIMAL_AUTH_SCHEME_INSTANCE,
    "credential_key": CUSTOM_SUDO_KEY,
    "type": "sudo_password_prompt",       # Custom field for HIL prompt
    "prompt_message": "Please provide the sudo password to execute the command." # Custom field for HIL prompt
}

# 2. Create the AuthConfig instance (assuming model_config allows extra fields)
AUTH_CONFIG_INSTANCE = AuthConfig(**auth_config_params)

def execute_shell_command(command: str, tool_context: ToolContext) -> dict:
    """
    Executes a shell command, handling both sudo password prompts (authentication)
    and interactive confirmations (e.g., 'Y/n').
    """
    print(f"\n[TOOL] Executing 'execute_shell_command' with input: '{command}'")

    if 'commands' not in tool_context.state:
        tool_context.state['commands'] = {}

    # --- MAIN LOGIC BRANCH: SUDO vs. NON-SUDO ---
    if command.strip().startswith("sudo"):
        return _handle_sudo_command(command, tool_context)
    else:
        return _handle_standard_command(command, tool_context)

def _handle_sudo_command(command: str, tool_context: ToolContext) -> dict:
    """Handles the complex logic for sudo commands, including auth and confirmation."""
    
    # --- Part 1: Handle Resuming from a Confirmation Prompt ---
    if tool_context.tool_confirmation is not None:
        if not tool_context.tool_confirmation.confirmed:
            return {"status": "rejected", "details": "User rejected the confirmation prompt."}
        
        # User confirmed 'Y'. Get the original command from the payload and re-run with 'y'.
        original_command = tool_context.tool_confirmation.payload.get('command_to_confirm', command)
        password = tool_context.state.get(PASSWORD_STATE_KEY)
        if not password:
             return {"status": "error", "reason": "StateError", "details": "Password was lost after confirmation."}
        return _run_subprocess(original_command, password=password, tool_context=tool_context, confirmation_input='y\n')

    # --- Part 2: Handle Authentication (Password Check) ---
    password = None
    auth_response: AuthCredential | None = tool_context.get_auth_response(AUTH_CONFIG_INSTANCE)
    
    if auth_response and auth_response.http and auth_response.http.credentials:
        password = auth_response.http.credentials.token
        if password:
            tool_context.state[PASSWORD_STATE_KEY] = password # Cache the new password
    else:
        password = tool_context.state.get(PASSWORD_STATE_KEY) # Use cached password

    if not password:
        print("[TOOL] Sudo command requires password. Pausing for authentication.")
        tool_context.request_credential(AUTH_CONFIG_INSTANCE)
        return {"status": "pending_auth", "details": "Awaiting sudo password."}

    # --- Part 3: Initial Execution and Check for Confirmation Prompt ---
    result = _run_subprocess(command, password=password,tool_context=tool_context)

    # Check if the command output is asking for a Y/n confirmation
    output_text = result.get('stdout', '') + result.get('stderr', '')
    confirmation_phrases = ["do you want to continue?", "[y/n]", "is this ok? [y/n]"]
    if any(phrase in output_text.lower() for phrase in confirmation_phrases):
        print("[TOOL] Command requires user confirmation. Pausing.")
        tool_context.request_confirmation(
            hint=f"The command is asking for confirmation:\n---\n{output_text}\n---\nPlease respond with 'y' or 'n'.",
            payload={'command_to_confirm': command} # Pass the command along for the resume step
        )
        return {"status": "pending_confirmation", "details": "Awaiting user confirmation (Y/n)."}

    # If auth failed, clear password and re-request
    if result.get("reason") == "AuthenticationFailed":
        if PASSWORD_STATE_KEY in tool_context.state:
            del tool_context.state[PASSWORD_STATE_KEY]
        tool_context.request_credential(AUTH_CONFIG_INSTANCE)
        return {"status": "pending_auth", "details": "Sudo password was incorrect. Please try again."}

    return result

def _handle_standard_command(command: str, tool_context: ToolContext) -> dict:
    """Handles non-sudo commands with the robust 'act-first, then-learn' logic."""
    return _run_subprocess(command, tool_context=tool_context)

def _run_subprocess(command: str, tool_context: ToolContext, password: str | None = None, confirmation_input: str | None = None) -> dict:
    """A centralized function for running subprocess commands."""
    try:
        command_to_run = command
        process_input = confirmation_input

        if password:
            # Use 'sudo -S' to read password from stdin
            command_to_run = f"sudo -S {command.strip().replace('sudo', '', 1).strip()}"
            process_input = password + '\n'
            # If we also have a confirmation, chain them
            if confirmation_input:
                process_input += confirmation_input
        
        process = subprocess.run(
            command_to_run, shell=True, capture_output=True, text=True,
            input=process_input, check=False
        )
        stdout, stderr = process.stdout.strip(), process.stderr.strip()

        # Sudo auth failure check
        if password and ("sorry, try again" in stderr.lower() or "incorrect password" in stderr.lower()):
            return {"status": "error", "reason": "AuthenticationFailed"}

        # Standard command success/failure learning logic
        base_command = shlex.split(command)[0]
        if process.returncode == 0:
            tool_context.state['commands'][base_command] = {'installed': True}
            return {"status": "success", "stdout": stdout, "stderr": stderr}
        elif 'command not found' in stderr.lower() or 'not recognized as' in stderr.lower():
            tool_context.state['commands'][base_command] = {'installed': False}
            return {"status": "error", "reason": "CommandNotInstalled"}
        else:
            tool_context.state['commands'][base_command] = {'installed': True} # It exists but failed
            return {"status": "error", "reason": "ExecutionFailed", "stdout": stdout, "stderr": stderr}

    except Exception as e:
        return {"status": "error", "reason": "ToolException", "details": str(e)}

# def execute_shell_command(command: str, tool_context: ToolContext) -> dict:
    # """
    # Executes a shell command, handling sudo prompts by pausing and requesting credentials.
    # Args:
    #     command: The full shell command to execute.
    #     tool_context: The ADK context object for tool interactions.
    # """
    # print(f"\n[TOOL] Executing 'execute_shell_command' with input: '{command}'")

    # if 'commands' not in tool_context.state:
    #     tool_context.state['commands'] = {}

    # # --- SUDO AUTHENTICATION FLOW ---
    # if command.strip().startswith("sudo"):
    #     password = None
    #     auth_response: Optional[AuthCredential] = tool_context.get_auth_response(AUTH_CONFIG_INSTANCE) 
        
         
    #     # 1. Check if the client just sent us the password to resume execution
       
    #     if auth_response :
    #         if (auth_response.http and 
    #             auth_response.http.credentials and 
    #             auth_response.http.credentials.token):
    #             password = auth_response.http.credentials.token
            
    #         if password:       
    #             # Cache successful password in persistent session state
    #             tool_context.state[PASSWORD_STATE_KEY] = password
    #     else:
    #         # 2. If not resuming, check if the password is already cached in our memory
    #         password = tool_context.state.get(PASSWORD_STATE_KEY)
    #         if password:
    #             print("[TOOL] Using cached password from session state.")

    #     # 3. If we still don't have a password, pause the execution and ask the user
    #     if not password:
             
    #         # This is the magic call that signals the runner to pause and wait for the client
    #         tool_context.request_credential(AUTH_CONFIG_INSTANCE)
    #         return {"status": "pending_auth", "details": "Awaiting sudo password from the user."}

    #     # 4. If we have a password, execute the command using it
    #     try:
    #         print(f"[TOOL] Executing privileged command: '{command}'")
    #         # The 'sudo -S' command reads the password from stdin.
    #         # We pass the password to the process's input.
    #         process = subprocess.run(
    #             f"sudo -S {command.strip().replace('sudo', '', 1).strip()}",
    #             shell=True,
    #             capture_output=True,
    #             text=True,
    #             input=password + '\n', # Pass the password to stdin
    #             check=False
    #         )
    #         stdout = process.stdout.strip()
    #         stderr = process.stderr.strip()

    #         # Check if authentication failed
    #         if "sorry, try again" in stderr.lower() or "incorrect password" in stderr.lower():              
    #             # Rejection: Clear cached password and re-request HIL
    #             if PASSWORD_STATE_KEY in tool_context.state:
    #                 del tool_context.state[PASSWORD_STATE_KEY]
                
    #             tool_context.request_credential(AUTH_CONFIG_INSTANCE)
                
    #             return {"status": "pending_auth", "details": "Sudo password rejected. Please try again."}

    #         return {"status": "success", "stdout": stdout, "stderr": stderr}

    #     except Exception as e:
    #         return {"status": "error", "reason": "ToolException", "details": str(e)}
    # else:
    #     try:
    #         base_command = shlex.split(command)[0]
    #     except (IndexError, ValueError):
    #         return {"status": "error", "reason": "Invalid command", "details": "The command string is malformed."}

    #     try:
    #         # --- ACTION FIRST ---
    #         # Always attempt to run the command. This is the only way to know the ground truth.
    #         process = subprocess.run(
    #             command,
    #             shell=True,
    #             capture_output=True,
    #             text=True,
    #             check=False # We handle our own errors.
    #         )
    #         stdout = process.stdout.strip()
    #         stderr = process.stderr.strip()

    #         # --- LEARN FROM THE OUTCOME ---
    #         if process.returncode == 0:
    #             # SUCCESS: The command worked. Update our memory to reflect this.
    #             print(f"Action Succeeded. Updating state: '{base_command}' is installed.")
    #             tool_context.state['commands'][base_command] = {'installed': True}
    #             return {"status": "success", "stdout": stdout}

    #         # FAILURE ANALYSIS:
    #         elif 'command not found' in stderr.lower() or 'not recognized as' in stderr.lower():
    #             # SPECIFIC FAILURE: The command doesn't exist. Update memory.
    #             print(f"Action Failed: Command Not Found. Updating state: '{base_command}' is not installed.")
    #             tool_context.state['commands'][base_command] = {'installed': False}
    #             return {
    #                 "status": "error",
    #                 "reason": "CommandNotInstalled",
    #                 "details": f"The command '{base_command}' is not installed. The agent's memory has been updated."
    #             }
    #         else:
    #             # OTHER FAILURE: The command exists but failed for another reason (e.g., wrong args).
    #             # We can still confirm it's installed, but return the error.
    #             print(f"Action Failed: Execution Error. Confirming state: '{base_command}' is installed.")
    #             tool_context.state['commands'][base_command] = {'installed': True}
    #             return {"status": "error", "reason": "ExecutionFailed", "stdout": stdout, "stderr": stderr, "return_code": process.returncode}

    #     except Exception as e:
    #         print(f"An unexpected error occurred in the tool itself: {e}")
    #         return {"status": "error", "reason": "ToolException", "details": str(e)}