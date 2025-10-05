
from google.adk.agents import LlmAgent,Agent
from .prompts.prompts import AGENT_SYSTEM_PROMPT
from .tools.shell_tool import execute_shell_command
from .tools.environment_info import get_environment_info
from google.adk.tools import google_search_tool,agent_tool
from google.adk.planners import BuiltInPlanner
from google.genai import types


# google_search_agent = Agent(
#     name="google_search_agent",
#     description="An AI agent that can perform Google searches to find information.",
#     model="gemini-2.5-flash",
#     instruction="""
# You are an AI agent that can perform Google searches to find information. Use the `google_search_tool` tool to search for relevant information based on user queries. Provide concise and accurate responses based on the search results.
# """,
#     tools=[google_search_tool]
# )

root_agent = LlmAgent(
    name="sentient_agent",
    description="An AI agent that can execute shell commands and learn from its environment.",
    model="gemini-2.5-flash",
    # The system prompt is the most important part of the agent's configuration
    instruction=AGENT_SYSTEM_PROMPT,
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=1024,
        )
    ),
    
    # Register the tools the agent is allowed to use.
    # In our case, it's only the powerful shell tool.
    tools=[
        execute_shell_command,
        get_environment_info,
        # agent_tool.AgentTool(agent=google_search_agent)
    ]
)