GPT-powered Discord bot for my own server.

```bash
poetry install
python cli.py sync-commands
python cli.py run
```

## Commands

- **/chat** — Start a conversation with the bot. It will create a new thread for you.
- **/ask** — Ask the bot a one-shot question in the current channel.
- **/regenerate** — In an existing thread, regenerate the bot's last response.
- **/stats** — In an existing thread, show info such as tokens used and the Chat
  Completion API request payload.

## Features

### Multiple participants

The bot listens to other users' messages, including those from other bots and Discord.

In the request, messages from other users will look like:

```json
{
  "role": "user",
  "content": "<@user_mention> says: Hello, ChatGPT!"
}
```

Messages from Discord will look like:

```json
{
  "role": "system",
  "content": "Discord: <@bot> added <@user> to the thread"
}
```

### Rich content

Text attachments will have their content included.

Embeds are sent as a Markdown document, for example:

```md
---
source: The New York Times <https://www.nytimes.com/>
author: By Noam Chomsky, Ian Roberts and Jeffrey Watumull
url: https://www.nytimes.com/2023/03/08/opinion/noam-chomsky-chatgpt-ai.html
type: article
---

**Opinion | Noam Chomsky: The False Promise of ChatGPT**

The most prominent strain of A.I. encodes a flawed conception of language and knowledge.
```

### Response timing

Use the `timing` option to control when the bot will respond: after every message, only
when the bot is mentioned.

Use the `reply_to` option to control to whom the bot will respond: any user (including
bots and Discord), any human user, or the user who started the bot.

### Presets

By default, the following system message is included at the beginning the request:

```json
{
  "role": "system",
  "content": "Your name is {bot_name}. You are talking to {user} over Discord. Server name: {server}. Channel: {channel}"
}
```

Use the `preset` option to choose other presets, or use the `system_message` option to
write your own.
