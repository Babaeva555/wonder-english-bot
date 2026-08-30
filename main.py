import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from json_repair import repair_json


logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
JUDGE_ID = int(os.getenv("JUDGE_ID", "328761045"))

HEROES = {
    "bunny": "🐰 Brave Bunny", "dragon": "🐲 Spark the Dragon",
    "luna": "👧 Luna the Inventor", "leo": "🦁 Captain Leo",
    "alien": "👽 Pip the Alien", "fairy": "🧚‍♀️ Willow the Fairy",
    "random": "🎲 Any Hero",
}
PLACES = {
    "forest": "🌲 Green Forest", "castle": "☁️ Cloud Castle",
    "candy": "🍭 Candy Planet", "pirate": "🏴‍☠️ Pirate Island",
    "jungle": "🌴 Wild Jungle", "ice": "❄️ Ice World",
    "toy": "🧸 Toy City", "museum": "🏛️ Mystery Museum",
    "sea": "🌊 Underwater World", "space": "🚀 Space Station",
    "random": "🎲 Any Place",
}
TOPICS = {
    "animals": "🐾 Animals", "family": "👨‍👩‍👧‍👦 Family",
    "school": "🎒 School", "toys": "🧸 Toys", "food": "🍕 Food",
    "clothes": "👕 Clothes", "home": "🏠 Home", "transport": "🚗 Transport",
    "hobbies": "⚽ Hobbies", "jobs": "👩‍⚕️ Jobs", "body": "🧍 Body",
    "colours": "🎨 Colours", "numbers": "🔢 Numbers", "weather": "🌦️ Weather",
    "day": "🕐 My Day", "holidays": "🎉 Holidays", "places": "🌍 Places",
    "mixed": "🎲 Mixed Topics",
}
PRACTICE = {
    "words": "🔤 Words", "grammar": "🧠 Grammar",
    "mixed": "🎲 Words + Grammar",
}
GRAMMAR = {
    "be": "🙋 Am / Is / Are", "have": "🎒 Have Got / Has Got",
    "can": "💪 Can / Can’t", "like": "❤️ Like / Don’t Like",
    "present": "▶️ Present Simple", "continuous": "🔄 Present Continuous",
    "prepositions": "📍 Prepositions", "plural": "🔢 Singular / Plural",
    "questions": "❓ Questions", "past": "🕰️ Past Simple",
    "future": "🔮 Future", "mixed": "🎲 Mixed Grammar",
}
TASKS = {
    "true_false": "✅ True or False",
    "guess": "🔤 Guess the Word", "complete": "🧩 Complete the Sentence",
    "choice": "💬 Choose the Answer", "mixed": "🎲 Mixed Tasks",
}
LEVELS = {"easy": "🌱 Easy", "normal": "⭐ Normal", "hard": "🚀 Hard", "auto": "🤖 Choose for Me"}


@dataclass
class Player:
    stage: str = "welcome"
    name: str = ""
    age: int = 0
    hero: str = ""
    place: str = ""
    topic: str = ""
    practice: str = ""
    grammar: str = ""
    task_type: str = ""
    level: str = ""
    task_count: int = 0
    story_title: str = ""
    story: str = ""
    tasks: list[dict] = field(default_factory=list)
    task_index: int = 0
    score: int = 0
    stars: int = 0
    stories: int = 0


players: dict[int, Player] = {}


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        for row in rows
    ])


def option_kb(options, prefix, cols=2, nav=True):
    items = [(label, f"{prefix}:{key}") for key, label in options.items()]
    rows = [items[i:i + cols] for i in range(0, len(items), cols)]
    if nav:
        rows.append([("⬅️ Back", "nav:back"), ("🏠 Main Menu", "nav:menu")])
    return kb(rows)


def grammar_options(age: int):
    if age <= 8:
        return {key: value for key, value in GRAMMAR.items() if key not in {"past", "future"}}
    return GRAMMAR


def main_kb():
    return kb([
        [("📖 Start a Story", "menu:story")],
        [("🏆 My Stars", "menu:stars"), ("👤 My Profile", "menu:profile")],
        [("ℹ️ Help", "menu:help"), ("⚙️ Settings", "menu:settings")],
    ])


def safe_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-zА-Яа-яЁё\- ]", "", text).strip()
    return cleaned[:24]


async def ai_call(messages, max_tokens=1400):
    if not KIE_API_KEY:
        raise RuntimeError("KIE_API_KEY is missing")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "messages": messages,
                "temperature": 0.55,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        return message.get("content") or message.get("reasoning") or ""


def demo_pack(player: Player):
    return {
        "title": "Spark and the Little Rabbit",
        "story": "Spark is a little green dragon. He lives near a big forest. One morning, he sees a small rabbit under a tree. The rabbit is sad. It cannot find its family. Spark helps the rabbit. They find three rabbits near a river. The little rabbit is happy again!",
        "tasks": [
            {"type": "true_false", "question": "Spark is a big red dragon.", "answer": "False", "hint": "Read the first sentence."},
            {"type": "question", "question": "Where is the rabbit?", "answer": "It is under a tree.", "hint": "Use: It is ..."},
            {"type": "order", "question": "Put in order: rabbit / The / sad / is", "answer": "The rabbit is sad.", "hint": "Start with The rabbit."},
            {"type": "mistake", "question": "Find the mistake: The rabbit are happy.", "answer": "The rabbit is happy.", "hint": "Use is or are?"},
            {"type": "question", "question": "Who helps the rabbit?", "answer": "Spark helps the rabbit.", "hint": "The dragon’s name starts with S."},
        ][:player.task_count],
    }


async def make_pack(user_id: int, player: Player):
    if user_id == JUDGE_ID:
        return demo_pack(player)
    if player.level == "easy":
        if player.age <= 8:
            level_rules = "A0-A1. Use only very common words, 35-55 words, sentences of 3-7 words. Use only Present Simple, am/is/are, have got/has got, can/can't and like/don't like. NEVER use Past Simple, Future forms, phrasal verbs or difficult adjectives."
        elif player.age <= 11:
            level_rules = "A1. Use common words, 55-80 words and short sentences. Prefer Present Simple, am/is/are, have got/has got and can/can't. Do not use Past Simple or Future forms."
        else:
            level_rules = "A1-A2. Use common words, 70-100 words and clear short sentences. Avoid complex grammar and rare words."
    elif player.level == "hard":
        level_rules = "Use an age-appropriate challenge, but keep every sentence clear and child-friendly."
    else:
        level_rules = "Use age-appropriate A1 English for ages 6-8, A1-A2 for ages 9-11, and A2 for ages 12-14."

    prompt = f"""
Create one safe, cheerful English mini-story and tasks for a child.
Child: {player.name}, age {player.age}. Hero: {HEROES[player.hero]}. Place: {PLACES[player.place]}.
Vocabulary topic: {TOPICS[player.topic]}. Practice: {PRACTICE[player.practice]}.
Grammar: {GRAMMAR.get(player.grammar, 'age-appropriate grammar')}. Level: {LEVELS[player.level]}.
Requested task type: {TASKS[player.task_type]}. Number of tasks: {player.task_count}.

Rules:
- Exact language rules: {level_rules}
- The selected level is mandatory. Never make an Easy story harder than the rules above.
- No violence, fear, romance, personal-data requests, brands, politics or unsafe content.
- Every task must be answerable from the story or selected language topic.
- Use only these interactive task types: true_false, choice, guess, complete.
- If task type is mixed, vary those four types.
- For every choice, guess and complete task, include exactly 3 short options. One option must exactly match answer.
- For true_false, use an empty options list.
- Keep questions very short. The child must answer by pressing a button, not by writing.
- answer must be short. hint must not reveal the answer.
- Return ONLY valid JSON, no Markdown:
{{"title":"...","story":"...","tasks":[{{"type":"choice","question":"...","options":["...","...","..."],"answer":"...","hint":"..."}}]}}
""".strip()
    raw = await ai_call([
        {"role": "system", "content": "You create safe English learning content for children and output strict JSON."},
        {"role": "user", "content": prompt},
    ])
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("AI returned no JSON")
    data = json.loads(repair_json(match.group(0)))
    if not data.get("story") or len(data.get("tasks", [])) < player.task_count:
        raise ValueError("Incomplete AI pack")
    data["tasks"] = data["tasks"][:player.task_count]
    return data


async def check_answer(player: Player, answer: str):
    task = player.tasks[player.task_index]
    prompt = f"""
You are a kind English teacher. The learner is {player.age} years old.
Question: {task['question']}
Model answer: {task['answer']}
Learner answer: {answer[:500]}
Check meaning, not exact wording. Accept minor spelling, punctuation and capitalization errors when meaning is clear.
Return ONLY JSON: {{"correct":true,"feedback":"short simple English praise or a brief Russian explanation of one error"}}
Maximum 25 words in feedback.
""".strip()
    raw = await ai_call([
        {"role": "system", "content": "You assess children's English kindly and return strict JSON."},
        {"role": "user", "content": prompt},
    ], 180)
    match = re.search(r"\{.*\}", raw, re.S)
    return json.loads(repair_json(match.group(0)))


async def make_more_tasks(player: Player):
    old_questions = "\n".join(f"- {task['question']}" for task in player.tasks)
    prompt = f"""
Create {player.task_count} NEW English tasks for a {player.age}-year-old child based on this story:

{player.story}

Do not repeat these questions:
{old_questions}

Use simple English. Every answer must be clear from the story.
Use the selected task style: {TASKS[player.task_type]}.
Use only interactive types: true_false, choice, guess, complete. If mixed, vary those four types.
For every choice, guess and complete task include exactly 3 short options, with one option exactly matching answer.
For true_false use an empty options list. Keep every question and option short.
Return ONLY valid JSON:
{{"tasks":[{{"type":"choice","question":"...","options":["...","...","..."],"answer":"...","hint":"..."}}]}}
""".strip()
    raw = await ai_call([
        {"role": "system", "content": "You create safe English learning tasks for children and output strict JSON."},
        {"role": "user", "content": prompt},
    ])
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("AI returned no JSON")
    data = json.loads(repair_json(match.group(0)))
    tasks = data.get("tasks", [])[:player.task_count]
    if len(tasks) < player.task_count:
        raise ValueError("AI returned too few tasks")
    return tasks


async def show_main(message: Message, player: Player):
    player.stage = "menu"
    await message.answer(f"🌟 <b>What do you want to do, {player.name}?</b>", reply_markup=main_kb())


async def cmd_start(message: Message):
    players[message.from_user.id] = Player()
    await message.answer(
        "🌟 <b>Hello! Welcome to Wonder English!</b>\n\n"
        "📖 Read fun stories.\n🎯 Do English tasks.\n⭐ Get stars and prizes!\n\n"
        "🚀 <b>Are you ready?</b>",
        reply_markup=kb([[("▶️ Start", "welcome:start"), ("ℹ️ About", "welcome:about")]]),
    )


async def callbacks(call: CallbackQuery):
    player = players.setdefault(call.from_user.id, Player())
    data = call.data
    await call.answer()

    if data == "welcome:about":
        await call.message.edit_text(
            "ℹ️ <b>About Wonder English</b>\n\n📖 Choose a hero and a place.\n✨ Get a new English story.\n🎯 Do fun tasks.\n⭐ Get stars!",
            reply_markup=kb([[("▶️ Start", "welcome:start")]]),
        )
    elif data == "welcome:start":
        player.stage = "name"
        await call.message.edit_text("👋 <b>What’s your name?</b>")
    elif data.startswith("age:"):
        player.age = int(data.split(":")[1])
        await call.message.edit_text(f"🎉 <b>Great, {player.name}!</b>\n🌈 Let’s make your English story!")
        await show_main(call.message, player)
    elif data == "menu:story":
        player.stage = "hero"
        await call.message.edit_text("🦸 <b>Choose a hero.</b>", reply_markup=option_kb(HEROES, "hero", 1))
    elif data == "menu:stars":
        await call.message.edit_text(
            f"🏆 <b>My Stars</b>\n\n⭐ Stars: {player.stars}\n📖 Stories: {player.stories}",
            reply_markup=kb([[("📖 Start a Story", "menu:story")], [("🏠 Main Menu", "nav:menu")]]),
        )
    elif data == "menu:profile":
        await call.message.edit_text(
            f"👤 <b>My Profile</b>\n\n😊 Name: {player.name}\n🎂 Age: {player.age}\n⭐ Stars: {player.stars}",
            reply_markup=kb([[("✏️ Change My Name", "profile:name"), ("🎂 Change My Age", "profile:age")], [("🏠 Main Menu", "nav:menu")]]),
        )
    elif data == "menu:help":
        await call.message.edit_text(
            "ℹ️ <b>How to play</b>\n\n1️⃣ Choose a hero.\n2️⃣ Choose a place.\n3️⃣ Choose a topic.\n4️⃣ Read the story.\n5️⃣ Do the tasks.\n6️⃣ Get stars! ⭐",
            reply_markup=kb([[("📖 Start a Story", "menu:story")], [("🏠 Main Menu", "nav:menu")]]),
        )
    elif data == "menu:settings":
        await call.message.edit_text("⚙️ <b>Settings</b>\n\n🇬🇧 Simple English is used in the game.\n🇷🇺 Difficult mistakes can be explained in Russian.", reply_markup=kb([[("🏠 Main Menu", "nav:menu")]]))
    elif data.startswith("hero:"):
        player.hero = data.split(":")[1]
        player.stage = "place"
        await call.message.edit_text("🗺️ <b>Where do you want to go?</b>", reply_markup=option_kb(PLACES, "place", 1))
    elif data.startswith("place:"):
        player.place = data.split(":")[1]
        player.stage = "topic"
        await call.message.edit_text("📚 <b>Choose a topic.</b>", reply_markup=option_kb(TOPICS, "topic", 2))
    elif data.startswith("topic:"):
        player.topic = data.split(":")[1]
        player.stage = "practice"
        await call.message.edit_text("📚 <b>What do you want to practise?</b>", reply_markup=option_kb(PRACTICE, "practice", 1))
    elif data.startswith("practice:"):
        player.practice = data.split(":")[1]
        if player.practice == "grammar":
            player.stage = "grammar"
            await call.message.edit_text("🧠 <b>Choose grammar.</b>", reply_markup=option_kb(grammar_options(player.age), "grammar", 1))
        else:
            player.stage = "task_type"
            await call.message.edit_text("🎯 <b>Choose your tasks.</b>", reply_markup=option_kb(TASKS, "taskkind", 1))
    elif data.startswith("grammar:"):
        player.grammar = data.split(":")[1]
        player.stage = "task_type"
        await call.message.edit_text("🎯 <b>Choose your tasks.</b>", reply_markup=option_kb(TASKS, "taskkind", 1))
    elif data.startswith("taskkind:"):
        player.task_type = data.split(":")[1]
        player.stage = "level"
        await call.message.edit_text("⭐ <b>Choose a level.</b>", reply_markup=option_kb(LEVELS, "level", 1))
    elif data.startswith("level:"):
        player.level = data.split(":")[1]
        player.stage = "count"
        counts = {"3": "3️⃣ 3 Tasks", "5": "5️⃣ 5 Tasks", "7": "7️⃣ 7 Tasks", "10": "🔟 10 Tasks"}
        await call.message.edit_text("🔢 <b>How many tasks?</b>", reply_markup=option_kb(counts, "count", 2))
    elif data.startswith("count:"):
        player.task_count = int(data.split(":")[1])
        await call.message.edit_text("✨ <b>Your story is coming!</b>\nPlease wait a little…")
        try:
            pack = await make_pack(call.from_user.id, player)
            player.story_title, player.story, player.tasks = pack["title"], pack["story"], pack["tasks"]
            player.task_index = player.score = 0
            player.stories += 1
            player.stage = "story"
            await call.message.answer(
                f"📖 <b>{player.story_title}</b>\n\n{player.story}",
                reply_markup=kb([[("▶️ Start the Tasks", "story:tasks")], [("📖 New Story", "menu:story"), ("🏠 Main Menu", "nav:menu")]]),
            )
        except Exception:
            logging.exception("Story generation failed")
            await call.message.answer("🤖 The AI is busy now. Please try again.", reply_markup=kb([[("🔄 Try Again", data), ("🏠 Main Menu", "nav:menu")]]))
    elif data == "story:tasks":
        await send_task(call.message, player)
    elif data == "task:true" or data == "task:false":
        await handle_answer(call.message, player, "True" if data.endswith("true") else "False", call.from_user.id)
    elif data.startswith("task:option:"):
        option_index = int(data.rsplit(":", 1)[1])
        options = player.tasks[player.task_index].get("options", [])
        if option_index < len(options):
            await handle_answer(call.message, player, str(options[option_index]), call.from_user.id)
    elif data == "task:hint":
        await call.message.answer(f"💡 <b>Hint:</b> {player.tasks[player.task_index]['hint']}")
    elif data == "task:show":
        await call.message.answer(f"👀 <b>Answer:</b> {player.tasks[player.task_index]['answer']}", reply_markup=kb([[("⏭️ Next Task", "task:next")]]))
    elif data == "task:next":
        player.task_index += 1
        await send_task(call.message, player)
    elif data == "task:retry":
        await send_task(call.message, player)
    elif data == "result:more":
        await call.message.answer("✨ <b>New tasks are coming!</b>\nPlease wait a little…")
        try:
            player.tasks = await make_more_tasks(player)
            player.task_index = player.score = 0
            await send_task(call.message, player)
        except Exception:
            logging.exception("More tasks generation failed")
            await call.message.answer(
                "🤖 The AI is busy now. Please try again.",
                reply_markup=kb([[('🔄 Try Again', 'result:more'), ('🏠 Main Menu', 'nav:menu')]]),
            )
    elif data == "profile:name":
        player.stage = "name_change"
        await call.message.edit_text("✏️ <b>What’s your name?</b>")
    elif data == "profile:age":
        player.stage = "age_change"
        await call.message.edit_text("🎂 <b>How old are you?</b>", reply_markup=age_kb("agechange"))
    elif data.startswith("agechange:"):
        player.age = int(data.split(":")[1])
        await call.message.edit_text("✅ Age changed!")
        await show_main(call.message, player)
    elif data == "nav:menu":
        await call.message.edit_text("🏠 <b>Main Menu</b>")
        await show_main(call.message, player)
    elif data == "nav:back":
        await show_main(call.message, player)


def age_kb(prefix="age"):
    ages = [(f"{age}", f"{prefix}:{age}") for age in range(6, 15)]
    return kb([ages[i:i + 3] for i in range(0, len(ages), 3)])


async def send_task(message: Message, player: Player):
    if player.task_index >= len(player.tasks):
        player.stars += player.score
        await message.answer(
            f"🎉 <b>Great job, {player.name}!</b>\n\n✅ Correct answers: {player.score}/{len(player.tasks)}\n⭐ New stars: {player.score}\n🏆 All stars: {player.stars}",
            reply_markup=kb([[("📖 New Story", "menu:story"), ("🎯 More Tasks", "result:more")], [("🏠 Main Menu", "nav:menu")]]),
        )
        player.stage = "result"
        return
    task = player.tasks[player.task_index]
    player.stage = "answer"
    text = f"🎯 <b>Task {player.task_index + 1}/{len(player.tasks)}</b>\n\n{task['question']}"
    if task.get("type") == "true_false":
        markup = kb([[("✅ True", "task:true"), ("❌ False", "task:false")], [("💡 Hint", "task:hint"), ("🏠 Main Menu", "nav:menu")]])
    elif task.get("options"):
        choices = [(str(option), f"task:option:{index}") for index, option in enumerate(task["options"][:4])]
        rows = [choices[i:i + 2] for i in range(0, len(choices), 2)]
        rows.append([("💡 Hint", "task:hint"), ("🏠 Main Menu", "nav:menu")])
        markup = kb(rows)
    else:
        markup = kb([[("💡 Hint", "task:hint"), ("👀 Show the Answer", "task:show")], [("🏠 Main Menu", "nav:menu")]])
        text += "\n\n✍️ Write your answer."
    await message.answer(text, reply_markup=markup)


async def handle_answer(message: Message, player: Player, answer: str, user_id: int):
    task = player.tasks[player.task_index]
    try:
        if task.get("type") == "true_false" or task.get("options"):
            correct = answer.strip().casefold() == str(task["answer"]).strip().casefold()
            result = {
                "correct": correct,
                "feedback": "Great! You got it right. 🌟" if correct else "Good try! Read the story again. 😊",
            }
        elif user_id == JUDGE_ID:
            correct = answer.strip().lower() == str(task["answer"]).strip().lower()
            result = {"correct": correct, "feedback": "Great job! 🌟" if correct else "Good try! Read the story again. 😊"}
        else:
            result = await check_answer(player, answer)
    except Exception:
        logging.exception("Answer check failed")
        await message.answer("🤖 The AI is busy now. Please send your answer again.")
        return
    if result.get("correct"):
        player.score += 1
        await message.answer(f"✅ {result.get('feedback', 'Great job!')} ⭐", reply_markup=kb([[("⏭️ Next Task", "task:next")]]))
    else:
        await message.answer(
            f"😊 {result.get('feedback', 'Good try!')} ",
            reply_markup=kb([[("🔄 Try Again", "task:retry"), ("💡 Hint", "task:hint")], [("👀 Show the Answer", "task:show")]]),
        )


async def text_messages(message: Message):
    player = players.setdefault(message.from_user.id, Player())
    if player.stage in {"name", "name_change"}:
        name = safe_name(message.text or "")
        if not name:
            await message.answer("😊 Please write your name.")
            return
        player.name = name
        if player.stage == "name_change":
            await message.answer(f"✅ Hello, {name}!")
            await show_main(message, player)
        else:
            player.stage = "age"
            await message.answer(f"😊 <b>Nice to meet you, {name}!</b>\n🎂 <b>How old are you?</b>", reply_markup=age_kb())
    elif player.stage == "answer":
        await handle_answer(message, player, message.text or "", message.from_user.id)
    else:
        await message.answer("🌟 Press /start to open Wonder English.")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(callbacks)
    dp.message.register(text_messages, F.text)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
