GPT-powered Discord bot for my own server.

```bash
poetry install
python cli.py sync-commands
python cli.py run
```

## Commands

- /chat — Start a conversation with the bot. It will create a new thread.
- /stats — In an existing thread, show info such as tokens used and the Chat Completion API request payload.

## Features

### Rich content

Text attachments will have their content included.

Embeds are sent as a Markdown document, for example:

```md
---
source: The New York Times <https://www.nytimes.com/>
author: By Noam Chomsky, Ian Roberts and Jeffrey Watumull
url: https://www.nytimes.com/2023/03/08/opinion/noam-chomsky-chatgpt-ai.html?smid=nytcore-ios-share&referringSource=articleShare
type: article
---

**Opinion | Noam Chomsky: The False Promise of ChatGPT**

The most prominent strain of A.I. encodes a flawed conception of language and knowledge.
```

### Multiple participants

The bot listens to other users as well, including other bots and Discord system messages.

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

### Response timing

Use the `timing` option to control when the bot will respond: after every message, only when mentioned.

Use the `reply_to` option to control to whom the bot will respond: everyone (including bots and Discord), every human, or you.

### Presets

By default, the following system message is included at the beginning the request:

```json
{
  "role": "system",
  "content": "Your name is {bot_name}. You are talking to {user} over Discord. Server name: {server}. Channel: {channel}. Current date: {current_date}"
}
```

Use the `preset` option to choose other presets, or use the `system_message` option to write your own.
