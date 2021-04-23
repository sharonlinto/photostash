import os
import slack
import requests
import datetime
from GoogleAPI import Create_Service
from googleapiclient.http import MediaFileUpload
from slackeventsapi import SlackEventAdapter
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask


"""
Load environment
"""
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


"""
Setup Flask App and Slack Client
"""
app = Flask(__name__)
client = slack.WebClient(token=os.environ["SLACK_TOKEN"])


"""
Create Google API Service
"""
GOOGLE_SECRET_FILENAME = "token.json"
GOOGLE_API_NAME = "drive"
GOOGLE_API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/drive"]

GOOGLE_SERVICE = Create_Service(
    GOOGLE_SECRET_FILENAME, GOOGLE_API_NAME, GOOGLE_API_VERSION, SCOPES
)


"""
Create Slack Event Adapter
    - Event endpoint: '/slack/events'
"""
slack_event_adapter = SlackEventAdapter(
    os.environ["SIGNING_SECRET"], "/slack/events", app
)
BOT_ID = client.api_call("auth.test")["user_id"]
ACCEPTED_FILE_TYPES = ["heic", "heif", "jpeg", "jpg", "mov", "mp4", "mpg", "png", "raw"]


def download_image(media_url, file_name, file_type):
    """
    Given the media URL, upload media to GDrive

    Parameters
    ----------
    media_url : str
        The URL (private) of the media (requires token)
    file_name : str
        The name to save the file
    file_type : str
        File extension, which must be part of ACCEPTED_FILE_TYPES

    Returns
    -------
    bool
        True on success, False on failure
    """
    # If the Google service is down, then we are screwed
    if not GOOGLE_SERVICE:
        return False

    # Make GET request to retrieve media file from Slack server
    media_data = requests.get(
        media_url, headers={"Authorization": f'Bearer {os.environ["SLACK_TOKEN"]}'}
    )

    # If not status OK, return immediately
    if media_data.status_code != 200:
        return False

    # Open file content and configure file names
    media = media_data.content
    proper_file_name = f"{file_name}.{file_type}"
    local_file_name = f"cache/{proper_file_name}"

    # Make cache dir if it doesn't exist
    if not os.path.exists("cache"):
        os.makedirs("cache")

    # Write the media to a temp file so that we can upload to GDrive
    with open(local_file_name, "wb") as file:
        file.write(media)

    # Set up metadata to upload to GDrive
    file_metadata = {
        "name": proper_file_name,
        "parents": [os.environ["TARGET_FOLDER_ID"]],
    }

    # Perform the upload
    media_body = MediaFileUpload(local_file_name, resumable=True)
    try:
        GOOGLE_SERVICE.files().create(
            body=file_metadata, media_body=media_body, fields="id"
        ).execute()
        media_body = None  # NOTE: set to None so that we can delete file
    except Exception as err:
        return False

    # Now, delete the file (since we don't need a local copy)
    try:
        os.remove(local_file_name)
    except PermissionError as err:
        print(f"Failed to delete local file. Looks like a permision error: {err}")
    except Exception as err:
        print(f"Failed to delete local file.")

    # Make sure to return true
    return True


# Keep track of ts to avoid duplicate messages
stored_timestamps = set()


@slack_event_adapter.on("message")
def handle_incoming_message(payload):
    """
    Handle all incoming slack messages

    Parameters
    ----------
    payload : dict
        See https://api.slack.com/events/message for more information

    Returns
    -------
    None
    """

    # Get relevant slack bot information
    event = payload.get("event", {})
    channel_id = event.get("channel")
    user_id = event.get("user")
    ts = event.get("ts")
    thread_ts = event.get("thread_ts", ts) # for media in threads
    proper_date = datetime.datetime.fromtimestamp(float(ts)).strftime(
        "%Y-%m-%d--%H-%M-%S"
    )

    # Make sure it isn't the bot that is sending the message
    if user_id != BOT_ID and ts not in stored_timestamps:
        # NOTE: For some reason, Slack API might send multiple requests
        stored_timestamps.add(ts)

        # Check to see if files is part of the payload
        if "files" in event:
            success = 0
            failure = 0

            # Iterate through all file objects
            for single_file in event["files"]:
                file_type = single_file["filetype"]

                # If the file type is valid, upload to GDrive
                if file_type in ACCEPTED_FILE_TYPES:
                    private_url = single_file["url_private"]
                    file_name = proper_date + " " + single_file["id"]
                    response = download_image(private_url, file_name, file_type)

                    # Tally based on the response
                    if response:
                        success += 1
                    else:
                        failure += 1

            # Construct text message
            text = ""
            if success > 0:
                text += f":white_check_mark: Successfully uploaded {success} "
                text += "files.\n" if success != 1 else "file.\n"
            if failure > 0:
                text += f":x: Failed to upload {failure} "
                text += "files.\n" if failure != 1 else "file.\n"

            # Post message to channel
            if text:
                client.chat_postMessage(
                    channel=channel_id,
                    text=text,
                    thread_ts=thread_ts,
                )


if __name__ == "__main__":
    app.run()
