import logging, time, os, socket
# Import WebClient from Python SDK (github.com/slackapi/python-slack-sdk)
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_discovery_sdk import DiscoveryClient
from slack_discovery_sdk.errors import DiscoveryApiError
from pathlib import Path
from dotenv import load_dotenv

### Path to the token
env_path = Path('Tokens/.env')
load_dotenv(dotenv_path=env_path)

# Get the current date and time
now = datetime.now()

script_directory = os.path.dirname(os.path.abspath(__file__))
# Define the log file path relative to the script's directory
log_file_path = os.path.join(script_directory, f"script_log_{now.strftime('%Y-%m-%d_%H-%M-%S')}.log")
second_log_file_path = os.path.join(script_directory, f"Channel_IDs{now.strftime('%Y-%m-%d_%H-%M-%S')}.log")

logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

### This script uses admin.conversations.archive API call which requires one admin level scope <admin.conversations:write>

# Set up Slack API client
enterprise_token = os.environ["SLACK_DISCOVERY_TOKEN"]
clientDiscovery = DiscoveryClient(token=enterprise_token)
client = WebClient(token=os.environ['SLACK_TOKEN'])

# You probably want to use a database to store any conversations information ;)
team_ids = ['Enterprise_ID','TeamID','TeamID2','TeamID3'] # Enterprise ID should go first as we want to check cross-shared channels followed by team IDs

MAX_RETRY_COUNT = 3  # Maximum number of retries

# Error handling 
def handle_slack_api_error(func, *args, **kwargs):
    for retry in range(MAX_RETRY_COUNT):
        try:
            return func(*args, **kwargs)
        except SlackApiError as e:
            if "timed out" in str(e).lower() or isinstance(e, socket.timeout):
                logger.error("Timeout error. Retrying...")
                time.sleep(5)  # Add a delay before retrying
            elif e.response is not None and e.response.status_code == 429:
                delay = int(e.response.headers.get('Retry-After', 1))
                logger.error(f"Rate limited. Retrying in {delay} seconds")
                time.sleep(delay)
            else:
                logger.error(f"ERROR {e}")
        except DiscoveryApiError as e:
            if "timed out" in str(e).lower() or isinstance(e, socket.timeout):
                logger.error("Timeout error. Retrying...")
                time.sleep(5)  # Add a delay before retrying
            else:
                logger.error(f"ERROR {e}")

# Fetching all channels from the specified workspaces
def fetch_conversations(team_id,private_state,public_state):
    conversations_store = []
    try:
        result = clientDiscovery.discovery_conversations_list(team=team_id, limit=1000, only_private = private_state, only_public = public_state)
        save_conversations(conversations_store, result["channels"])
        print(result['offset'])
        while result['offset'] != None:
            cursor = result['offset']
            result = clientDiscovery.discovery_conversations_list(team=team_id, limit=1000, only_private = private_state, only_public = public_state, offset=cursor)
            save_conversations(conversations_store, result["channels"])
        return conversations_store
    except DiscoveryApiError as e:
        logger.error("ERROR fetching conversations: {}".format(e))


def fetch_conversations_private(team_id, private_state, public_state):
    private_channels = fetch_conversations(team_id,private_state = private_state, public_state = public_state)
    print(len(private_channels),team_id)
    return private_channels

def fetch_conversations_public(team_id, private_state, public_state):
    public_channels = fetch_conversations(team_id,private_state = private_state, public_state = public_state)
    print(len(public_channels),team_id)
    return public_channels

# Put conversations into the JavaScript object
def save_conversations(conversations_store, conversations):
    for conversation in conversations:
        if conversation['is_archived'] is False and conversation['is_file'] is False:
            conversations_store.append(conversation)


# Fetch channels last activity date and call archival function
def fetch_last_activity_date(team_id):
    private_channels = fetch_conversations_private(team_id, private_state =True, public_state = False)
    public_channels = fetch_conversations_public(team_id, private_state =False, public_state = True)
    all_channels = [x for n in (private_channels,public_channels) for x in n]
    for channel in all_channels:
        try:
            response = handle_slack_api_error(
                clientDiscovery.discovery_conversations_history,
                channel=channel['id'],
                team=team_id
            )

            if response is not None and response.get("messages"):
                last_message_timestamp = response["messages"][0]["ts"]
                last_message_time = time.localtime(float(last_message_timestamp))
                days_since_last_message = (time.time() - time.mktime(last_message_time)) / (24 * 60 * 60)
                ### IMPORTANT set the date in days to specify after which inactivity time to archive the channel
                if days_since_last_message >= 180:
                    archive_conversations(days_since_last_message, channel)
                else:
                    logger.info(f"Channel #{channel['name']} was last active {days_since_last_message} days ago and won't be archived.")
            elif response is not None and not response.get("messages") and not response.get("has_edits"):
                try:
                    response = clientDiscovery.discovery_conversations_info(channel=channel['id'], team=team_id)
                    if response is not None:
                        channel_creation_timestamp = response["info"][0]["created"]
                        channel_creation_time = time.localtime(float(channel_creation_timestamp))
                        days_since_channel_creation = (time.time() - time.mktime(channel_creation_time)) / (24 * 60 * 60)
                        if days_since_channel_creation >= 180:
                            archive_conversations(days_since_channel_creation, channel)
                        else:
                            logger.info(f"Channel #{channel['name']} was created {days_since_channel_creation} days ago and won't be archived.")
                except DiscoveryApiError as e:
                    logger.error(f"ERROR {e} fetching channel's info: #{channel['name']}")
                    continue
        except DiscoveryApiError as e:
            logger.error(f"ERROR {e} fetching last activity date for a channel: #{channel['name']}")


# Function to archive conversations
def archive_conversations(date, channel):
    try:
        response = client.admin_conversations_archive(channel_id=channel['id'])
        logger.info(f"SUCCESS: Channel #{channel['name']} archived because it was inactive for {date} days.")
    except SlackApiError as e:
        if e.response.status_code == 429:
        # The `Retry-After` header will tell you how long to wait before retrying
            delay = int(e.response.headers['Retry-After'])
            logger.error(f"Rate limited. Retrying in {delay} seconds")
            time.sleep(delay)
            logger.error(f"Rate limited. Retrying in {delay} seconds")
            try:
                response = client.admin_conversations_archive(channel_id=channel['id'])
                logger.info(f"SUCCESS: Channel #{channel['name']} archived because it was inactive for {date} days.")
            except SlackApiError as e:
                if e.response.status_code == 410:
                    logger.error(f"Channel is already Archived : #{channel['name']}")
                else:
                    logger.error(f"ERROR {e} archiving channel: #{channel['name']}")
        

def main():
    logger.info('Script started')
    start_time = time.time()
    for team_id in team_ids:
        fetch_last_activity_date(team_id)
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Script completed in {duration:.2f} seconds")

# Execute the main function
if __name__ == "__main__":
    main()
