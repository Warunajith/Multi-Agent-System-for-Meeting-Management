import os
import time
import requests
from typing import Optional
from phi.tools.googlecalendar import GoogleCalendarTools
import datetime
from tzlocal import get_localzone_name
from phi.utils.log import logger
from phi.agent import Agent
from phi.model.openai import OpenAIChat
from phi.tools.zoom import ZoomTool
from phi.tools.slack import SlackTools
from dotenv import load_dotenv

load_dotenv()
# Get environment variables
ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")


class CustomZoomTool(ZoomTool):
    def __init__(
        self,
        account_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        name: str = "zoom_tool",
    ):
        super().__init__(account_id=account_id, client_id=client_id, client_secret=client_secret, name=name)
        self.token_url = "https://zoom.us/oauth/token"
        self.access_token = None
        self.token_expires_at = 0

    def get_access_token(self) -> str:
        """
        Obtain or refresh the access token for Zoom API.
        Returns:
            A string containing the access token or an empty string if token retrieval fails.
        """
        if self.access_token and time.time() < self.token_expires_at:
            return str(self.access_token)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"grant_type": "account_credentials", "account_id": self.account_id}

        try:
            response = requests.post(
                self.token_url, headers=headers, data=data, auth=(self.client_id, self.client_secret)
            )
            response.raise_for_status()

            token_info = response.json()
            self.access_token = token_info["access_token"]
            expires_in = token_info["expires_in"]
            self.token_expires_at = time.time() + expires_in - 60

            self._set_parent_token(str(self.access_token))
            return str(self.access_token)
        except requests.RequestException as e:
            logger.error(f"Error fetching access token: {e}")
            return ""

    def _set_parent_token(self, token: str) -> None:
        """Helper method to set the token in the parent ZoomTool class"""
        if token:
            self._ZoomTool__access_token = token


zoom_tools = CustomZoomTool(account_id=ACCOUNT_ID, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)


zoom_agent = Agent(
    name="Zoom Meeting Manager",
    agent_id="zoom-meeting-manager",
    model=OpenAIChat(model="gpt-4"),
    tools=[zoom_tools],
    markdown=True,
    debug_mode=True,
    show_tool_calls=True,
    instructions=[
        "You are an expert at managing Zoom meetings using the Zoom API.",
        "You can:",
        "1. Schedule new meetings (schedule_meeting)",
        "2. Get meeting details (get_meeting)",
        "3. List all meetings (list_meetings)",
        "4. Get upcoming meetings (get_upcoming_meetings)",
        "5. Delete meetings (delete_meeting)",
        "6. Get meeting recordings (get_meeting_recordings)",
        "",
        "For recordings, you can:",
        "- Retrieve recordings for any past meeting using the meeting ID",
        "- Include download tokens if needed",
        "- Get recording details like duration, size, download link and file types",
        "",
        "Guidelines:",
        "- Use ISO 8601 format for dates (e.g., '2024-12-28T10:00:00Z')",
        "- Ensure meeting times are in the future",
        "- Provide meeting details after scheduling (ID, URL, time)",
        "- Handle errors gracefully",
        "- Confirm successful operations",
    ],
)


# Define Google Calendar Assistant Agent
# Define Google Calendar Assistant Agent
calendar_agent = Agent(
    name="Google Calendar Assistant",
    agent_id="google-calendar-assistant",
    model=OpenAIChat(model="gpt-4"),
    tools=[GoogleCalendarTools(credentials_path="client_secret_assistant.json")],
    show_tool_calls=True,
    instructions=[
        f"""
        You are a scheduling assistant. Today is {datetime.datetime.now()} and the user's timezone is {get_localzone_name()}.
        Your tasks include:
        - Retrieving scheduled events from Google Calendar.
        - Creating new calendar events based on user input.
        """,
    ],
    add_datetime_to_instructions=True,
)


# Define Slack Tool
slack_tools = SlackTools()

# Define Slack Communication Agent
slack_agent = Agent(
    name="Slack Communication Manager",
    agent_id="slack-communication-manager",
    tools=[SlackTools()],
    show_tool_calls=True,
    markdown=True,
    debug_mode=True,
    instructions=[
        "You are responsible for managing Slack communications.",
        "You can perform the following tasks:",
        "- Send messages to Slack channels or users",
        "- Retrieve recent Slack messages from a specific channel",
        "- Get a list of Slack channels and members",
        "- Notify users about upcoming meetings",
        "",
        "Guidelines:",
        "- Ensure messages are formatted correctly in Markdown when needed.",
        "- Confirm successful message delivery and provide response summaries.",
        "- Use clear and concise messaging to improve communication.",
    ],
)




# Define Team Leader Agent
# Define Team Leader Agent
team_leader_agent = Agent(
    name="Team Leader",
    agent_id="team-leader",
    model=OpenAIChat(model="gpt-4"),
    tools=[],
    markdown=True,
    debug_mode=True,
    show_tool_calls=True,
    instructions=[
        "You are responsible for delegating tasks to the appropriate agent(s) in the Scheduling Team.",
        "Your goal is to optimize performance by selecting the correct agent(s) for each request while minimizing unnecessary API calls.",
        "",
        "Rules for Delegation:",
        "- If the request is ONLY about Zoom meetings (scheduling, listing, retrieving recordings, etc.), delegate to the **Zoom Meeting Manager** and ignore the other agents.",
        "- If the request is ONLY about Google Calendar (getting events, adding events, modifying events), delegate to the **Google Calendar Assistant** and ignore the other agents.",
        "- If the request is ONLY about Slack (sending messages, retrieving messages, notifying users), delegate to the **Slack Communication Manager** and ignore the other agents.",
        "- If the request involves BOTH Zoom and Google Calendar (e.g., scheduling a Zoom meeting and adding it to Google Calendar), first call the **Zoom Meeting Manager**, retrieve meeting details, then pass those details to the **Google Calendar Assistant**.",
        "- If the request involves notifying users on Slack after scheduling a Zoom meeting or adding a Google Calendar event, first complete the scheduling task, then pass relevant details to the **Slack Communication Manager**.",
        "",
        "Additional Guidelines:",
        "- Ensure correct agent selection to avoid unnecessary API calls.",
        "- Provide users with clear responses based on the selected agent(s).",
        "- Confirm task completion after execution.",
        "- If a Zoom meeting or calendar event is scheduled, ask the user if they want to notify participants via Slack before triggering the Slack Agent.",
        "- If a task is unclear, request clarification before delegating.",
    ],
)


# Create a Team in Phi Data
scheduling_team = Agent(
    name="Scheduling Team",
    team=[team_leader_agent, zoom_agent, calendar_agent,slack_agent],
    instructions="Handles Zoom meetings, Google Calendar scheduling and Slack Communication.",
    show_tool_calls=True,
    markdown=True,
)

# Example Usage
#user_request = "Schedule a Zoom meeting titled daily Standup for 30mins on February 25 2025 at 11.30 AM for Sri Lankan Time and add this event to my Google Calander as well"

user_request="List all my upcoming Zoom meetings"

#user_request="Create an event in Google Calander on 20th February 2025 at 6PM with the topic Crew AI Learning. This event details should be sent to the slack channel called all-softworldpro"
#user_request="get the last 10 messages of slack channel all-softworldpro and crate a zoom meeting by using last message details. timezone is Sri Lanka."
#scheduling_team.print_response(user_request,stream=True)


response = scheduling_team.run(user_request)


print(f'Below is the OUTPUT:========  {response.content}')