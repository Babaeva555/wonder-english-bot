# 🌟 Wonder English

AI Telegram bot for children aged 6–14. The child chooses a hero, place, vocabulary topic, practice type, task type, level and task count. AI creates a safe short English story, generates exercises and checks free-text answers.

## Environment variables

Set these in the hosting dashboard. Never add real keys to GitHub.

- `BOT_TOKEN` — token from Telegram @BotFather
- `OPENROUTER_API_KEY` — key from OpenRouter
- `AI_MODEL` — `openrouter/free`
- `JUDGE_ID` — `328761045`

## Start command

```bash
python main.py
```

## AI use

OpenRouter API is used to:

1. generate an age-appropriate story from the child's selections;
2. generate tasks based on the story;
3. assess free-text answers by meaning and provide feedback.

The project evaluator ID uses a token-saving demonstration pack.
