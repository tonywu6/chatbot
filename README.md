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

Text attachments will have their content included.

The bot listens to other users as well (including other bots). In the request, messages from other users will look like

```json
{
  "role": "user",
  "content": "<@user_mention>: Hello, ChatGPT!"
}
```

Currently only messages from you will trigger a response.
