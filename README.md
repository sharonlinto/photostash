# Sharon's Photostash App

## About
The OG PhotoStash app no longer works on Slack, so I'm going to make a new one!!!

## Todos
- [x] Figure out why requests are sometimes sent multiple times
- [x] Figure out how to delete images after they've been uploaded to GDrive
- [x] Figure out how to download full version of media (not compressed)
- [x] Save file name better (use timestamp instead of file id)
- [x] Handle large files
- [ ] Clean code pls (try catch blocks included, move files to dirs)
- [ ] Perhaps configure the UI of the bot too????????
- [ ] Write a setup README
- [ ] Handle images inside threads

## Running the App
Make sure to add the Slackbot to your channel

## Running the Server
Using ngrok.exe, run the command: ```ngrok http 5000```
- Make sure that you update **Event Subscriptions** on the Slack API with endpoint in ngrok
- Make sure that you update **Request URL** under Slash commands with endpoint in ngrok

## Creating GCP Project
[Follow This Link](https://www.youtube.com/watch?v=6bzzpda63H0&ab_channel=JieJenn)