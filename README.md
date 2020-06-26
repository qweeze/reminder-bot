# reminder telegram bot

```bash
$ docker build -t local/reminder --build-arg TZ=Asia/Yekaterinburg .
$ export BOT_TOKEN=<bot_token>
$ docker run \
    -d \
    --name reminder \
    -v ${PWD}/db.sqlite:/db.sqlite \
    local/reminder \
    --token $TOKEN \
    --usernames <username_1> ... <username_n>
```
