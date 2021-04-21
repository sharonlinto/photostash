import os
import slack
import requests
from GoogleAPI import Create_Service
from googleapiclient.http import MediaFileUpload
from slackeventsapi import SlackEventAdapter
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask

# TODO: Figure out why requests are sometimes sent multiple times
# TODO: Figure out how to delete images after they've been uploaded to GDrive
# TODO: Figure out how to download full version of media (not compressed)
# TODO: Save file name better (use timestamp instead of file id)
# TODO: Clean code pls (try catch blocks included, move files to dirs)
# TODO: Perhaps configure the UI of the bot too????????
# TODO: Write a setup README

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
        File extension. Must be part of ACCEPTED_FILE_TYPES

    Returns
    -------
    bool
        True on success, False on failure
    """

    # Make GET request to retrieve data
    media_data = requests.get(
        media_url, headers={"Authorization": f'Bearer {os.environ["SLACK_TOKEN"]}'}
    )

    # If not status OK, return immediately
    if media_data.status_code != 200:
        return False

    # Open the file
    media = media_data.content
    proper_file_name = f"{file_name}.{file_type}"
    local_file_name = f"cache/{proper_file_name}"

    handler = open(local_file_name, "wb")
    handler.write(media)
    handler.close()

    # Now with the media file written, we can copy image to GDrive
    file_metadata = {
        "name": proper_file_name,
        "parents": [os.environ["TARGET_FOLDER_ID"]],
    }

    media_body = MediaFileUpload(local_file_name)
    GOOGLE_SERVICE.files().create(
        body=file_metadata, media_body=media_body, fields="id"
    ).execute()

    # After the file has been uploaded, delete it
    # handler.close()
    # os.remove(local_file_name)

    return True


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

    # Make sure it isn't the bot that is sending the message
    if user_id != BOT_ID:
        print("I'm not the bot!")

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
                    file_name = single_file["id"]
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
                text += "files.\n" if success != 1 else "file.\n"

            # Post message to channel
            if text:
                client.chat_postMessage(
                    channel=channel_id,
                    text=text,
                    thread_ts=ts,
                )


if __name__ == "__main__":
    app.run(debug=True)
