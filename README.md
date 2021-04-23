# Sharon's Photostash App

## About
The OG PhotoStash app no longer works on Slack, so I'm going to make a new one!!!

## .env file
```
SLACK_TOKEN=<get from Slack API webpage>
SIGNING_SECRET=<get from Slack API webpage>

# GDrive folder URL: https://drive.google.com/drive/u/0/folders/<TARGET_FOLDER_ID>
TARGET_FOLDER_ID=<get from Gdrive URL>
```

## Running the App
Make sure to add the Slackbot to your channel, and that should be it!

## Running the Server
Using ngrok.exe, run the command: ```ngrok http 5000```
- Make sure that you update **Event Subscriptions** on the Slack API with server endpoint (to be edited)

## Creating GCP Project
[Follow This Link](https://www.youtube.com/watch?v=6bzzpda63H0)
- Make sure to get the .json file from GCP in order to enable the login token