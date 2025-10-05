import platform
import shutil
from google.adk.tools import ToolContext

def get_environment_info(dummy_str:str,tool_context:ToolContext) -> dict:
    """
    Detects the operating system and default package manager.

    This tool is state-aware. It checks if the environment information
    is already stored in the tool_context state to avoid redundant checks. If not,
    it detects the OS and package manager, updates the state, and returns
    the information.

    Args:
        dummy_str: Any dummy value can be passed.

    Returns:
        A dictionary containing the environment details.
    """
    print("Executing tool 'get_environment_info'")

    # 1. MEMORY CHECK: First, check if we already know the environment.
    if 'environment' in tool_context.state and tool_context.state['environment']:
        print("Perception: Environment info found in state. Returning cached data.")
        return {
            "status": "success",
            "source": "cache",
            "data": tool_context.state['environment']
        }

    # 2. PERCEPTION: If not in memory, detect the environment now.
    print("Perception: Environment info not in state. Detecting now...")
    env_info = {}
    os_name = platform.system().lower()
    env_info['os'] = os_name

    pkg_manager = None
    if os_name == "linux":
        if shutil.which("apt-get"):
            pkg_manager = "apt"
        elif shutil.which("yum"):
            pkg_manager = "yum"
        elif shutil.which("dnf"):
            pkg_manager = "dnf"
    elif os_name == "darwin": # macOS
        if shutil.which("brew"):
            pkg_manager = "brew"
    elif os_name == "windows":
        if shutil.which("choco"):
            pkg_manager = "choco"
        elif shutil.which("winget"):
            pkg_manager = "winget"

    env_info['pkg_manager'] = pkg_manager

    # 3. STATE UPDATE: Save the findings to the tool_context memory.
    print(f"State Update: Saving environment info to tool_context state: {env_info}")
    tool_context.state['environment'] = env_info

    return {
        "status": "success",
        "source": "discovery",
        "data": env_info
    }