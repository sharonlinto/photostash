import os
import slack
import requests
import datetime
import yaml
from GoogleAPI import Create_Service
from googleapiclient.http import MediaFileUpload
from slackeventsapi import SlackEventAdapter
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, Response


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
FOLDER_YAML = "folders.yaml"


def get_folder_id(channel_id):
    """
    Given the channel id, return the associated folder ID
    """

    yaml_file = None

    # If the file does not exist, make one
    if not os.path.exists(FOLDER_YAML):
        open(FOLDER_YAML, 'w').close()

    # Load yaml file with contents
    with open(FOLDER_YAML, "r") as stream:
        yaml_file = yaml.safe_load(stream) or {}
    folder_id = yaml_file.get(channel_id, None)

    return folder_id


def upload_image(media_url, file_name, file_type, folder_id):
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

    # Make GET request to retrieve media file from Slack server
    media_data = requests.get(
        media_url, headers={"Authorization": f'Bearer {os.environ["SLACK_TOKEN"]}'}
    )

    # If not status OK, return immediately
    if media_data.status_code != 200:
        return False, "Could not retrieve file from Google Drive API."

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
        "parents": [folder_id],
    }

    # Perform the upload
    media_body = MediaFileUpload(local_file_name, resumable=True)
    try:
        GOOGLE_SERVICE.files().create(
            body=file_metadata, media_body=media_body, fields="id"
        ).execute()
        media_body = None  # NOTE: set to None so that we can delete file
    except Exception:
        media_body = None  # NOTE: set to None so that we can delete file
        try:
            os.remove(local_file_name)
        except:
            pass

        return (
            False,
            "Could not upload to Google Drive. Make sure that the Google Drive folder ID is correct "
            "by running the slash command: `/current-folder-id`. If the folder ID is correct, "
            "consider changing viewing permissions on your folder (set to the *entire organization*) "
            "to allow the bot write access.",
        )

    # Now, delete the file (since we don't need a local copy)
    try:
        os.remove(local_file_name)
    except:
        pass

    # Make sure to return true
    return True, None


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
    folder_id = get_folder_id(channel_id)
    user_id = event.get("user")
    ts = event.get("ts")
    thread_ts = event.get("thread_ts", ts)  # for media in threads
    proper_date = datetime.datetime.fromtimestamp(float(ts)).strftime(
        "%Y-%m-%d--%H-%M-%S"
    )

    # First, make sure that GOOGLE_SERVICE is working
    if user_id != BOT_ID:
        if not GOOGLE_SERVICE:
            client.chat_postMessage(
                channel=channel_id,
                text=":x: Failed to upload files.\n\nCould not generate a token.",
                thread_ts=thread_ts,
            )

            return  # Return immediately

        # Make sure it isn't the bot that is sending the message
        if ts not in stored_timestamps:
            # NOTE: For some reason, Slack API might send multiple requests
            stored_timestamps.add(ts)
            encountered_error_messages = set()

            # Check to see if files is part of the payload
            if "files" in event:
                success = 0
                failure = 0

                # Iterate through all file objects
                for single_file in event["files"]:
                    file_type = single_file["filetype"]

                    # If the file type is valid, upload to GDrive
                    if file_type in ACCEPTED_FILE_TYPES:

                        # Next, get the folder ID for this channel
                        if not folder_id:
                            client.chat_postMessage(
                                channel=channel_id,
                                text=":x: Failed to upload files.\n\nThe Google Drive folder ID is not configured "
                                "for this channel. Use the slash command: `/current-folder-id` to check the "
                                "current Google Drive folder ID.",
                                thread_ts=thread_ts,
                            )
                            return  # Return immediately

                        private_url = single_file["url_private"]
                        file_name = proper_date + " " + single_file["id"]
                        response, message = upload_image(
                            private_url, file_name, file_type, folder_id
                        )

                        # Tally based on the response
                        if response:
                            success += 1
                        else:
                            failure += 1
                            encountered_error_messages.add(" • " + message)

                # Construct text message
                text = ""
                if success > 0:
                    text += f":white_check_mark: Successfully uploaded {success} "
                    text += "files.\n" if success != 1 else "file.\n"
                if failure > 0:
                    text += f":x: Failed to upload {failure} "
                    text += "files.\n\n" if failure != 1 else "file.\n\n"
                    text += "Errors:\n" + "\n".join(encountered_error_messages)

                # Post message to channel
                if text:
                    client.chat_postMessage(
                        channel=channel_id,
                        text=text,
                        thread_ts=thread_ts,
                    )


@app.route("/config-folder-id", methods=["POST"])
def handle_folder_config():
    """
    Handle slack command for configuring GDrive folder ID
    """
    # Retrieve channel and folder ID's from POST request
    data = request.form
    channel_id = data["channel_id"]
    folder_id = data["text"]

    # Load the YAML file of folder mappings
    yaml_file = None

    if not os.path.exists(FOLDER_YAML):
        open(FOLDER_YAML, 'w').close()

    with open(FOLDER_YAML, "r") as stream:
        yaml_file = yaml.safe_load(stream) or {}

    # Create Slack Bot reply message
    message = ""

    if len(folder_id.split()) > 1:  # Make sure it is one word
        message = "The Google Drive folder ID should be one string. Please verify and try again."
    else:  # Otherwise, we can update the yaml file
        yaml_file.update({channel_id: folder_id})

        with open(FOLDER_YAML, "w") as yamlfile:
            yaml.safe_dump(yaml_file, yamlfile)
        message = (
            f"The Google Drive folder ID for this channel is set to: "
            f"<https://drive.google.com/drive/u/0/folders/{folder_id}|{folder_id}>"
        )

    # Return a message with the current channel_id
    client.chat_postMessage(channel=channel_id, text=message)

    return Response(), 200


@app.route("/current-folder-id", methods=["POST"])
def return_current_folder():
    """
    Given the channel ID, return the GDrive folder ID from FOLDER_YAML
    """
    data = request.form
    channel_id = data["channel_id"]
    folder_id = get_folder_id(channel_id)

    # Print message based on the folder ID
    message = ""
    if not folder_id:
        message = (
            "This channel's Google Drive folder ID has *not* been configured. "
            "Use the slash command: `/config-folder-id <folder-id>` to configure this channel's Google Drive folder ID."
        )
    else:
        message = f"This channel's Google Drive folder ID is: <https://drive.google.com/drive/u/0/folders/{folder_id}|{folder_id}>"

    # Return a message with the current channel_id
    client.chat_postMessage(channel=channel_id, text=message)

    return Response(), 200


if __name__ == "__main__":
    app.run(debug=True)
