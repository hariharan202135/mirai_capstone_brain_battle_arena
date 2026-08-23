import streamlit as st
import os
import random
import string
import json
import re
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client
from google import genai


st.set_page_config(
    page_title="Brain Battle Arena",
    page_icon="🧠",
    layout="wide"
)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not GEMINI_KEY:
    st.error("Check your .env file. SUPABASE_URL, SUPABASE_KEY and GEMINI_API_KEY are required.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini = genai.Client(api_key=GEMINI_KEY)

BATTLE_TIME = 12 * 60
TOTAL_QUESTIONS = 15

TOPICS = [
    "Logical Reasoning",
    "Number Patterns",
    "Mathematics",
    "Aptitude",
    "Brain Puzzles",
    "Riddles",
    "Verbal Ability",
    "Science",
    "Computer Fundamentals",
    "General Knowledge",
    "History",
    "Geography",
    "Economics",
    "Sports",
    "Movies & Entertainment"
]

DIFFICULTIES = ["Easy", "Medium", "Hard", "Mixed"]


# -----------------------------
# Styling Helpers
# -----------------------------

def page_style():
    st.markdown("""
    <style>
    .stApp {
        background:
            radial-gradient(circle at 10% 0%, rgba(255, 75, 75, .08), transparent 28%),
            radial-gradient(circle at 90% 10%, rgba(70, 120, 255, .08), transparent 28%),
            #0b0f17;
    }
    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }
    h1, h2, h3 {
        letter-spacing: -0.03em;
    }
    .hero {
        padding: 28px 30px;
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 22px;
        background: linear-gradient(135deg, rgba(255,75,75,.12), rgba(40,55,90,.18));
        margin-bottom: 24px;
    }
    .hero-title {
        font-size: 2.7rem;
        font-weight: 800;
        margin: 0;
    }
    .hero-sub {
        color: #aab4c5;
        margin-top: 8px;
        font-size: 1.05rem;
    }
    .card {
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 18px;
        padding: 20px;
        background: rgba(20,25,36,.72);
        margin-bottom: 16px;
    }
    .mini-card {
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 14px;
        padding: 15px;
        background: rgba(24,31,45,.75);
        min-height: 92px;
    }
    .question-box {
        padding: 24px;
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,.09);
        background: linear-gradient(145deg, #141a26, #0f141e);
        margin: 12px 0 18px;
    }
    .question-text {
        font-size: 1.35rem;
        line-height: 1.55;
        font-weight: 650;
    }
    .result-card {
        padding: 28px;
        border-radius: 22px;
        border: 1px solid rgba(255,255,255,.08);
        background: linear-gradient(145deg, rgba(35,45,65,.8), rgba(16,21,31,.9));
        text-align: center;
    }
    .big-score {
        font-size: 3.2rem;
        font-weight: 800;
    }
    .muted {
        color: #9aa6b8;
    }
    div[data-testid="stMetric"] {
        background: rgba(20,25,36,.68);
        border: 1px solid rgba(255,255,255,.07);
        padding: 12px;
        border-radius: 14px;
    }
    .stButton > button {
        border-radius: 12px;
        min-height: 44px;
        font-weight: 650;
    }
    .stProgress > div > div > div > div {
        border-radius: 999px;
    }
    </style>
    """, unsafe_allow_html=True)


def make_match_code():
    chars = string.ascii_uppercase + string.digits
    return "BB-" + "".join(random.choices(chars, k=6))


def get_match(code):
    try:
        result = supabase.table("matches").select("*").eq("match_code", code).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def get_players(match_id):
    try:
        result = supabase.table("players").select("*").eq("match_id", match_id).order("player_number").execute()
        return result.data
    except Exception:
        return []


def get_current_player(players):
    value = st.query_params.get("player")
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 1

    for player in players:
        if player.get("player_number") == number:
            return player
    return None


def get_remaining_seconds(match):
    start_time = match.get("battle_start_time")
    if not start_time:
        return None

    try:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        elapsed = int((datetime.now(timezone.utc) - start).total_seconds())
        return BATTLE_TIME - elapsed
    except Exception:
        return None


def safe_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


# -----------------------------
# AI Questions & Freshness Guard
# -----------------------------

def clean_ai_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return text


def validate_questions(questions, topics=None):
    if not isinstance(questions, list):
        raise ValueError("AI response is not a list.")

    if len(questions) != TOTAL_QUESTIONS:
        raise ValueError("AI did not create 15 questions.")

    topic_counts = {}

    for q in questions:
        if not q.get("question"):
            raise ValueError("A question is missing.")

        if not isinstance(q.get("options"), list) or len(q["options"]) != 4:
            raise ValueError("Every question needs 4 options.")

        if len(set(q["options"])) != 4:
            raise ValueError("Question options must be different.")

        if q.get("answer") not in q["options"]:
            raise ValueError("Invalid answer in AI response.")

        topic = q.get("topic")
        if topics and topic not in topics:
            raise ValueError("AI returned an unselected topic.")

        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    if topics:
        for topic in topics:
            if topic_counts.get(topic, 0) != 3:
                raise ValueError(
                    f"AI must create exactly 3 questions for {topic}."
                )

    return questions




def get_previous_questions_avoid_list():
    try:
        result = supabase.table("matches").select("question_set").order("created_at", desc=True).limit(15).execute()
        avoid_list = []
        if result.data:
            for row in result.data:
                q_set = safe_json(row.get("question_set"))
                if isinstance(q_set, list):
                    for q in q_set:
                        if isinstance(q, dict) and "question" in q:
                            avoid_list.append(q["question"])
        return avoid_list[:50]
    except Exception:
        return []



def fresh_fallback_questions(topics, difficulty):
    """
    Backup quiz used only when Gemini is unavailable.
    It deliberately creates three variants per selected topic so the
    fallback also follows the 15-question / 5-topic structure.
    """
    questions = []

    def add(topic, question, options, answer):
        questions.append({
            "topic": topic,
            "difficulty": difficulty,
            "question": question,
            "options": options,
            "answer": answer,
            "explanation": f"The correct answer is {answer}."
        })

    for topic in topics:
        if topic == "Mathematics":
            a = random.randint(12, 35)
            b = random.randint(6, 18)
            product = a * b
            add(
                topic,
                f"What is {a} × {b}?",
                [str(product), str(product + 8), str(product - 6), str(product + 12)],
                str(product)
            )

            base = random.choice([120, 160, 200, 240, 300])
            percent = random.choice([10, 15, 20, 25])
            answer = base * percent // 100
            add(
                topic,
                f"What is {percent}% of {base}?",
                [str(answer), str(answer + 10), str(max(1, answer - 10)), str(answer + 20)],
                str(answer)
            )

            x = random.randint(8, 20)
            total = x + 7
            add(
                topic,
                f"If x + 7 = {total}, what is x?",
                [str(x), str(x + 1), str(x + 2), str(x - 1)],
                str(x)
            )

        elif topic == "Number Patterns":
            start = random.randint(2, 12)
            step = random.randint(2, 7)
            values = [start + step * i for i in range(4)]
            answer = values[-1] + step
            add(
                topic,
                f"What comes next: {', '.join(map(str, values))}, ?",
                [str(answer), str(answer + step), str(answer + 2), str(answer - step)],
                str(answer)
            )

            start = random.randint(2, 8)
            values = [start * (2 ** i) for i in range(4)]
            answer = values[-1] * 2
            add(
                topic,
                f"What comes next: {', '.join(map(str, values))}, ?",
                [str(answer), str(answer + 4), str(answer - 2), str(answer * 2)],
                str(answer)
            )

            start = random.randint(3, 10)
            values = [start + i * 3 for i in range(4)]
            answer = values[-1] + 3
            add(
                topic,
                f"Find the next number: {', '.join(map(str, values))}, ?",
                [str(answer), str(answer + 3), str(answer - 3), str(answer + 6)],
                str(answer)
            )

        elif topic == "Logical Reasoning":
            add(topic, "If A is taller than B and B is taller than C, who is shortest?",
                ["A", "B", "C", "Cannot say"], "C")
            add(topic, "Which one is different from the other three?",
                ["Triangle", "Square", "Circle", "Rectangle"], "Circle")
            add(topic, "If all cats are animals, which statement is certain?",
                ["All animals are cats", "All cats are animals", "No cats are animals", "Some animals are not cats"],
                "All cats are animals")

        elif topic == "Aptitude":
            speed = random.choice([40, 50, 60, 70])
            hours = random.choice([2, 3, 4])
            distance = speed * hours
            add(topic,
                f"A vehicle travels at {speed} km/h for {hours} hours. What distance does it cover?",
                [f"{distance} km", f"{distance + speed} km", f"{distance - speed} km", f"{distance + 20} km"],
                f"{distance} km")
            nums = random.sample(range(10, 51), 3)
            avg = sum(nums) / 3
            add(topic,
                f"What is the average of {nums[0]}, {nums[1]} and {nums[2]}?",
                [str(avg), str(avg + 2), str(avg - 2), str(avg + 5)],
                str(avg))
            price = random.choice([400, 500, 600, 800])
            discount = random.choice([10, 20])
            sale = price - price * discount // 100
            add(topic,
                f"A product costs ₹{price} and gets a {discount}% discount. What is the sale price?",
                [f"₹{sale}", f"₹{sale + 20}", f"₹{sale + 40}", f"₹{sale - 20}"],
                f"₹{sale}")

        elif topic == "Brain Puzzles":
            add(topic, "Which month has 28 days?", ["February only", "January only", "Every month", "None"], "Every month")
            add(topic, "A clock shows 3:00. What is the angle between the hands?",
                ["30°", "60°", "90°", "120°"], "90°")
            add(topic, "What can travel around the world while staying in one corner?",
                ["A stamp", "A clock", "A cloud", "A shadow"], "A stamp")

        elif topic == "Riddles":
            add(topic, "I have keys but cannot open locks. What am I?",
                ["Piano", "Door", "Map", "Book"], "Piano")
            add(topic, "I get wetter the more I dry. What am I?",
                ["Sponge", "Towel", "Paper", "Cloth"], "Towel")
            add(topic, "I have hands but cannot clap. What am I?",
                ["Robot", "Clock", "Tree", "Chair"], "Clock")

        elif topic == "Verbal Ability":
            add(topic, "Choose the synonym of 'rapid'.", ["Slow", "Quick", "Weak", "Late"], "Quick")
            add(topic, "Choose the antonym of 'ancient'.", ["Old", "Historic", "Modern", "Past"], "Modern")
            add(topic, "Choose the correctly spelled word.",
                ["Seperate", "Separate", "Seperete", "Separete"], "Separate")

        elif topic == "Science":
            add(topic, "Which planet is known as the Red Planet?",
                ["Earth", "Mars", "Jupiter", "Venus"], "Mars")
            add(topic, "Which gas do plants mainly use during photosynthesis?",
                ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"], "Carbon dioxide")
            add(topic, "What is H2O commonly called?",
                ["Salt", "Water", "Oxygen", "Hydrogen"], "Water")

        elif topic == "Computer Fundamentals":
            add(topic, "Which device is mainly used to type text?",
                ["Monitor", "Keyboard", "Speaker", "Printer"], "Keyboard")
            add(topic, "What does CPU stand for?",
                ["Central Processing Unit", "Computer Power Unit", "Core Program Utility", "Central Program User"],
                "Central Processing Unit")
            add(topic, "Which is an operating system?",
                ["Python", "Linux", "HTML", "SQL"], "Linux")

        elif topic == "General Knowledge":
            add(topic, "How many continents are commonly recognized?",
                ["5", "6", "7", "8"], "7")
            add(topic, "Which is the largest ocean?",
                ["Atlantic", "Indian", "Pacific", "Arctic"], "Pacific")
            add(topic, "What is the capital of India?",
                ["Mumbai", "Chennai", "New Delhi", "Kolkata"], "New Delhi")

        elif topic == "History":
            add(topic, "India became independent in which year?",
                ["1945", "1946", "1947", "1950"], "1947")
            add(topic, "The Taj Mahal was built by which Mughal emperor?",
                ["Akbar", "Shah Jahan", "Babur", "Aurangzeb"], "Shah Jahan")
            add(topic, "Who is known as the Father of the Indian Constitution?",
                ["Mahatma Gandhi", "B. R. Ambedkar", "Jawaharlal Nehru", "Sardar Patel"],
                "B. R. Ambedkar")

        elif topic == "Geography":
            add(topic, "Which is the largest continent?",
                ["Africa", "Asia", "Europe", "Australia"], "Asia")
            add(topic, "Mount Everest is part of which mountain range?",
                ["Andes", "Alps", "Himalayas", "Rockies"], "Himalayas")
            add(topic, "Which is the longest river in India?",
                ["Ganga", "Yamuna", "Godavari", "Narmada"], "Ganga")

        elif topic == "Economics":
            add(topic, "What does GDP stand for?",
                ["Gross Domestic Product", "General Development Price", "Global Domestic Profit", "Gross Development Plan"],
                "Gross Domestic Product")
            add(topic, "Inflation generally means?",
                ["Fall in prices", "Rise in general prices", "Fall in income", "Rise in exports"],
                "Rise in general prices")
            add(topic, "Which institution issues currency notes in India?",
                ["SEBI", "RBI", "IRDAI", "NITI Aayog"], "RBI")

        elif topic == "Sports":
            add(topic, "How many players are on the field for one cricket team?",
                ["9", "10", "11", "12"], "11")
            add(topic, "Which sport uses a shuttlecock?",
                ["Tennis", "Badminton", "Hockey", "Football"], "Badminton")
            add(topic, "How many rings are on the Olympic symbol?",
                ["4", "5", "6", "7"], "5")

        elif topic == "Movies & Entertainment":
            add(topic, "Which award is popularly associated with Indian cinema?",
                ["Oscars", "National Film Awards", "Pulitzer", "Booker"],
                "National Film Awards")
            add(topic, "A screenplay is mainly used for?",
                ["Cooking", "Film or video production", "Accounting", "Driving"],
                "Film or video production")
            add(topic, "Which device is commonly used to record video?",
                ["Camera", "Calculator", "Router", "Scanner"], "Camera")

        else:
            add(topic, f"Which option is most closely related to {topic}?",
                [topic, "Cooking", "Driving", "Gardening"], topic)
            add(topic, f"What is mainly studied under {topic}?",
                [topic, "Weather only", "Recipes only", "Road signs only"], topic)
            add(topic, f"Which option belongs to {topic}?",
                [topic, "Vehicle", "Fruit", "Furniture"], topic)

    random.shuffle(questions)
    return questions[:TOTAL_QUESTIONS]





def generate_questions(topics, difficulty):
    topic_text = ", ".join(topics)
    avoid_questions = get_previous_questions_avoid_list()

    avoid_clause = ""

    if avoid_questions:
        avoid_clause = (
            "\n\nSTRICT DO-NOT-USE LIST FROM PREVIOUS BATTLES:\n"
            + "\n".join(f"- {q}" for q in avoid_questions)
        )

    freshness_id = f"{time.time_ns()}-{random.randint(100000, 999999)}"

    prompt = f"""
Create a completely NEW competitive quiz for Brain Battle Arena.

Fresh generation ID: {freshness_id}

Selected topics: {topic_text}
Difficulty: {difficulty}

Create exactly 15 multiple-choice questions.

There are exactly 5 selected topics.
Create exactly 3 questions for EACH selected topic.

IMPORTANT FRESHNESS RULES:
- Every question must be newly created for THIS battle.
- NEVER reuse an old question.
- NEVER copy an old question.
- NEVER paraphrase an old question.
- NEVER slightly rewrite an old question.
- NEVER reuse an old question and only change numbers, names, dates,
  places, options, or wording.
- Do not reuse the same scenario or reasoning pattern from the old list.
- Use different facts, situations, values and reasoning paths.
- Do not repeat a question within this new 15-question set.
- The questions should feel like a fresh quiz, not a recycled question bank.

QUALITY RULES:
- Exactly 4 different options per question.
- Exactly one correct answer.
- The answer must exactly match one option.
- Respect the requested difficulty.
- Include a short explanation.
- Return ONLY valid JSON.
- Do not return markdown.

{avoid_clause}

Before returning the JSON, mentally compare every generated question
against the DO-NOT-USE list and replace anything that is the same,
nearly the same, paraphrased, or only numerically modified.

Return exactly this structure:

[
  {{
    "topic": "Science",
    "difficulty": "Medium",
    "question": "Question",
    "options": ["A", "B", "C", "D"],
    "answer": "A",
    "explanation": "Short explanation"
  }}
]
"""

    # Several independent generations make repeated questions less likely.
    for attempt in range(4):
        try:
            response = gemini.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            questions = json.loads(clean_ai_json(response.text))
            questions = validate_questions(questions, topics)

            if has_internal_duplicates(questions):
                raise ValueError("AI returned duplicate questions.")

            if any(question_is_duplicate(q, avoid_questions) for q in questions):
                raise ValueError("AI returned a question from a previous battle.")

            random.shuffle(questions)
            return questions

        except Exception:
            if attempt < 3:
                time.sleep(0.8)

    st.toast(
        "AI is busy. A fresh randomized backup quiz is being prepared.",
        icon="⚡"
    )

    return fresh_fallback_questions(topics, difficulty)



# -----------------------------
# Profiles & Safe Handling
# -----------------------------

def create_profile(name):
    name = name.strip()
    if not name:
        return None
    try:
        result = supabase.table("profiles").select("*").eq("player_name", name).execute()
        if result.data:
            return result.data[0]

        result = supabase.table("profiles").insert({
            "player_name": name,
            "total_xp": 0,
            "matches_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "total_score": 0,
            "best_streak": 0
        }).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def save_profile_after_match(name, score, result_type, streak):
    try:
        profile = create_profile(name)
        if not profile:
            return

        xp = score + (500 if result_type == "win" else 200 if result_type == "draw" else 100)
        wins = profile["wins"] + (1 if result_type == "win" else 0)
        losses = profile["losses"] + (1 if result_type == "loss" else 0)
        draws = profile["draws"] + (1 if result_type == "draw" else 0)

        supabase.table("profiles").update({
            "total_xp": profile["total_xp"] + xp,
            "matches_played": profile["matches_played"] + 1,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "total_score": profile["total_score"] + score,
            "best_streak": max(profile["best_streak"], streak)
        }).eq("player_name", name).execute()
    except Exception:
        pass


# -----------------------------
# Completion & Race Condition Guard
# -----------------------------


def finish_battle(match, players):
    if len(players) < 2:
        return False

    p1, p2 = players[0], players[1]

    # Never finalize until both players really completed all questions.
    if (p1.get("current_question", 0) or 0) < TOTAL_QUESTIONS:
        return False

    if (p2.get("current_question", 0) or 0) < TOTAL_QUESTIONS:
        return False

    try:
        latest = get_match(match["match_code"])

        if latest and latest.get("status") == "finished":
            return True

        # Only one status transition is needed. If two browsers arrive
        # together, both will harmlessly converge on the same finished state.
        supabase.table("matches").update({
            "status": "finished",
            "results_saved": True
        }).eq(
            "id",
            match["id"]
        ).eq(
            "status",
            "battle"
        ).execute()

    except Exception:
        return False

    score1 = p1.get("score", 0) or 0
    score2 = p2.get("score", 0) or 0

    if score1 > score2:
        res1, res2 = "win", "loss"
    elif score2 > score1:
        res1, res2 = "loss", "win"
    else:
        res1 = res2 = "draw"

    # Profile saving must never prevent the results screen.
    save_profile_after_match(
        p1["player_name"],
        score1,
        res1,
        p1.get("best_streak", 0) or 0
    )

    save_profile_after_match(
        p2["player_name"],
        score2,
        res2,
        p2.get("best_streak", 0) or 0
    )

    return True



def check_both_players_completed(match_id):
    # Always fetch fresh player rows directly from Supabase.
    try:
        result = (
            supabase
            .table("players")
            .select("*")
            .eq("match_id", match_id)
            .order("player_number")
            .execute()
        )
        players = result.data or []
    except Exception:
        return False, []

    if len(players) < 2:
        return False, players

    p1_done = (players[0].get("current_question", 0) or 0) >= TOTAL_QUESTIONS
    p2_done = (players[1].get("current_question", 0) or 0) >= TOTAL_QUESTIONS

    return p1_done and p2_done, players




# -----------------------------
# Dashboard & Detailed Comparison
# -----------------------------

def show_leaderboard():
    st.markdown("### 🏆 Global Leaderboard")
    try:
        result = supabase.table("profiles").select("*").order("total_xp", desc=True).limit(10).execute()
        players = result.data
    except Exception:
        st.info("Leaderboard is unavailable right now.")
        return

    if not players:
        st.info("No completed battles yet.")
        return

    for i, player in enumerate(players):
        position = i + 1
        medal = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else f"#{position}"
        c1, c2, c3, c4 = st.columns([1, 4, 2, 2])
        with c1: st.write(f"### {medal}")
        with c2: st.write(f"**{player['player_name']}**")
        with c3: st.write(f"⭐ {player['total_xp']} XP")
        with c4: st.write(f"🏆 {player['wins']} wins")


def show_dashboard():
    st.markdown("""
    <div class="hero">
        <div class="hero-title">📊 Player Dashboard</div>
        <div class="hero-sub">Track your battles, XP, wins and streaks.</div>
    </div>
    """, unsafe_allow_html=True)

    name = st.session_state.get("dashboard_name", "")
    if not name:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        name = st.text_input("Player name", placeholder="Example: Hari")
        if st.button("VIEW MY STATS", type="primary", use_container_width=True):
            if name.strip():
                st.session_state.dashboard_name = name.strip()
                st.rerun()
            else:
                st.toast("Enter your name.", icon="⚠️")
        st.markdown("</div>", unsafe_allow_html=True)
        show_leaderboard()
        return

    try:
        result = supabase.table("profiles").select("*").eq("player_name", name).execute()
        profile = result.data[0] if result.data else None
    except Exception:
        profile = None

    if not profile:
        st.info("No completed battle history is available for this player yet.")
        show_leaderboard()
        return

    matches = profile["matches_played"]
    wins = profile["wins"]
    losses = profile["losses"]
    draws = profile["draws"]
    xp = profile["total_xp"]
    score = profile["total_score"]
    streak = profile["best_streak"]

    win_rate = round(wins / matches * 100) if matches else 0
    level = (xp // 1000) + 1
    level_xp = xp % 1000

    st.markdown(f'<div class="card"><h2>👋 Welcome back, {name}</h2><p class="muted">Keep battling and climb the arena leaderboard.</p></div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("🏟️ Matches", matches)
    with c2: st.metric("🏆 Wins", wins)
    with c3: st.metric("📈 Win Rate", f"{win_rate}%")
    with c4: st.metric("⭐ XP", xp)

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("❌ Losses", losses)
    with c2: st.metric("🤝 Draws", draws)
    with c3: st.metric("🔥 Best Streak", streak)

    st.markdown(f"### 🆙 Level {level}")
    st.progress(level_xp / 1000)
    st.caption(f"{level_xp} / 1000 XP until Level {level + 1}")

    st.markdown(f'<div class="card"><h3>⭐ Total Score</h3><div class="big-score">{score}</div></div>', unsafe_allow_html=True)
    show_leaderboard()


# -----------------------------
# Lobby & Battle Fragments
# -----------------------------

@st.fragment(run_every=2)
def watch_lobby(match):
    latest = get_match(match["match_code"])
    if not latest:
        return

    players = get_players(latest["id"])
    if latest.get("status") == "generating":
        st.info("🧠 Player 1 is preparing the battle...")
        return
    if latest.get("status") == "battle":
        st.rerun(scope="app")
        return

    if len(players) >= 2:
        if not st.session_state.get("opponent_joined"):
            opponent = players[1]
            st.session_state.opponent_joined = True
            st.toast(f"🎉 {opponent['player_name']} joined your arena!", icon="🔥")
            st.rerun(scope="app")
        return

    st.info("⏳ Waiting for your opponent to join...")


@st.fragment(run_every=2)
def wait_for_battle(match):
    latest = get_match(match["match_code"])
    if not latest:
        return

    status = latest.get("status")
    if status == "generating":
        st.warning("🧠 Player 1 is generating the questions...")
        return
    if status == "battle" and latest.get("question_set"):
        st.rerun(scope="app")
        return
    if status == "finished":
        st.rerun(scope="app")
        return

    st.info("⏳ Waiting for Player 1 to start the battle...")



@st.fragment(run_every=1)
def battle_fragment(match):
    # Always fetch a fresh match and fresh player rows.
    latest_match = get_match(match["match_code"])

    if not latest_match:
        st.error("Battle could not be found.")
        return

    both_done, fresh_players = check_both_players_completed(
        latest_match["id"]
    )

    if both_done:
        finished = finish_battle(
            latest_match,
            fresh_players
        )

        if finished:
            latest_finished_match = get_match(
                latest_match["match_code"]
            ) or latest_match

            show_results(
                latest_finished_match,
                fresh_players
            )
            return

    if latest_match.get("status") == "finished":
        show_results(latest_match, fresh_players)
        return

    current_player = get_current_player(fresh_players)

    if not current_player:
        st.error("Player information could not be found.")
        return

    questions = safe_json(latest_match.get("question_set"))

    if not questions:
        st.info("🧠 Questions are being prepared...")
        return

    total = len(questions)
    question_number = current_player.get("current_question", 0) or 0
    remaining = get_remaining_seconds(latest_match)

    # If this player finished, check the opponent before showing waiting.
    if question_number >= total:
        both_done, fresh_players = check_both_players_completed(
            latest_match["id"]
        )

        if both_done:
            finish_battle(latest_match, fresh_players)
            finished_match = get_match(latest_match["match_code"]) or latest_match
            show_results(finished_match, fresh_players)
            return

        opponent = next(
            (
                p for p in fresh_players
                if p["id"] != current_player["id"]
            ),
            None
        )

        st.markdown("""
        <div class="result-card">
            <div style="font-size:3rem;">🎉</div>
            <h2>You finished all 15 questions!</h2>
            <p class="muted">Waiting only for your opponent to finish...</p>
        </div>
        """, unsafe_allow_html=True)

        if opponent:
            opp_q = opponent.get("current_question", 0) or 0
            st.progress(min(opp_q / total, 1.0))
            st.caption(
                f"{opponent['player_name']}: "
                f"{opp_q}/{total} completed"
            )

        return

    # Time is handled per player. If the timer expires, move directly
    # to results only when both players are done; otherwise save this
    # player's completion and wait.
    if remaining is not None and remaining <= 0:
        st.warning("⏰ Time is up!")

        supabase.table("players").update({
            "current_question": total
        }).eq(
            "id",
            current_player["id"]
        ).execute()

        both_done, fresh_players = check_both_players_completed(
            latest_match["id"]
        )

        if both_done:
            finish_battle(latest_match, fresh_players)
            finished_match = get_match(latest_match["match_code"]) or latest_match
            show_results(finished_match, fresh_players)
        else:
            st.info("Waiting for your opponent to finish.")

        return

    question = questions[question_number]

    minutes = max(remaining or 0, 0) // 60
    seconds = max(remaining or 0, 0) % 60

    st.markdown("""
    <div class="hero">
        <div class="hero-title" style="font-size:2.2rem;">⚔️ Battle Mode</div>
        <div class="hero-sub">Think fast. Choose wisely. Beat your opponent.</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("⏱️ Time", f"{minutes:02d}:{seconds:02d}")

    with c2:
        st.metric("⭐ Score", current_player.get("score", 0) or 0)

    with c3:
        st.metric("🔥 Streak", current_player.get("best_streak", 0) or 0)

    with c4:
        st.metric("📝 Progress", f"{question_number + 1}/{total}")

    st.progress(question_number / total)

    st.markdown(
        f"""
        <div class="question-box">
            <div class="muted">
                🎯 {question['topic']} •
                {question.get('difficulty', latest_match.get('difficulty', 'Mixed'))}
            </div>
            <div class="question-text">{question['question']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    options = question["options"]

    answer = st.radio(
        "Choose your answer",
        options,
        key=f"answer_{current_player['id']}_{question_number}"
    )

    hints_left = current_player.get("hints_left", 0) or 0

    hint_col, submit_col = st.columns([1, 3])

    with hint_col:
        if hints_left > 0 and st.button(
            f"💡 Hint ({hints_left})",
            use_container_width=True
        ):
            wrong = [
                opt for opt in options
                if opt != question["answer"]
            ]

            if wrong:
                st.info(
                    f"💡 You can eliminate: "
                    f"**{random.choice(wrong)}**"
                )

                supabase.table("players").update({
                    "hints_left": hints_left - 1
                }).eq(
                    "id",
                    current_player["id"]
                ).execute()

    with submit_col:
        submit = st.button(
            "✅ SUBMIT ANSWER",
            type="primary",
            use_container_width=True
        )

    if submit:
        correct = answer == question["answer"]

        old_score = current_player.get("score", 0) or 0
        old_streak = current_player.get("best_streak", 0) or 0
        old_correct = current_player.get("correct_answers", 0) or 0
        old_answered = current_player.get("questions_answered", 0) or 0

        if correct:
            new_streak = old_streak + 1
            points = (
                100
                + (25 if new_streak >= 3 else 0)
                + (25 if new_streak >= 5 else 0)
            )

            new_score = old_score + points
            new_correct = old_correct + 1

            st.toast(
                f"🔥 Correct! +{points} points",
                icon="🎯"
            )
        else:
            new_streak = 0
            new_score = old_score
            new_correct = old_correct

            st.toast(
                "❌ Not quite. Keep going!",
                icon="💥"
            )

        next_question = question_number + 1

        supabase.table("players").update({
            "score": new_score,
            "questions_answered": old_answered + 1,
            "correct_answers": new_correct,
            "current_question": next_question,
            "best_streak": new_streak
        }).eq(
            "id",
            current_player["id"]
        ).execute()

        try:
            supabase.table("answers").insert({
                "match_id": latest_match["id"],
                "player_id": current_player["id"],
                "question_number": next_question,
                "selected_answer": answer,
                "is_correct": correct
            }).execute()
        except Exception:
            pass

        # Q15: immediately fetch BOTH players again.
        if next_question >= total:
            time.sleep(0.2)

            both_now_done, updated_players = (
                check_both_players_completed(
                    latest_match["id"]
                )
            )

            if both_now_done:
                finish_battle(
                    latest_match,
                    updated_players
                )

                finished_match = (
                    get_match(latest_match["match_code"])
                    or latest_match
                )

                show_results(
                    finished_match,
                    updated_players
                )

                return

            st.toast(
                "🎉 You finished all 15! Waiting for your opponent...",
                icon="🏁"
            )

            st.rerun(scope="fragment")
            return

        st.rerun(scope="fragment")

    st.divider()

    opponent = next(
        (
            p for p in fresh_players
            if p["id"] != current_player["id"]
        ),
        None
    )

    if opponent:
        st.markdown("### 👤 Opponent")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.write(f"**{opponent['player_name']}**")

        with c2:
            st.write(
                f"📝 {opponent.get('questions_answered', 0) or 0}/{total}"
            )

        with c3:
            st.write(
                f"⭐ {opponent.get('score', 0) or 0} XP"
            )



# -----------------------------
# Detailed Results & Comparison Screen
# -----------------------------

def show_results(match, players):
    st.markdown("""
    <div class="hero">
        <div class="hero-title">🏁 Battle Complete</div>
        <div class="hero-sub">The arena has spoken. Review the detailed head-to-head comparison.</div>
    </div>
    """, unsafe_allow_html=True)

    if len(players) < 2:
        st.warning("Waiting for both players to sync.")
        return

    p1, p2 = players[0], players[1]
    score1 = p1.get("score", 0) or 0
    score2 = p2.get("score", 0) or 0
    corr1 = p1.get("correct_answers", 0) or 0
    corr2 = p2.get("correct_answers", 0) or 0
    streak1 = p1.get("best_streak", 0) or 0
    streak2 = p2.get("best_streak", 0) or 0

    acc1 = round((corr1 / TOTAL_QUESTIONS) * 100)
    acc2 = round((corr2 / TOTAL_QUESTIONS) * 100)

    if score1 > score2:
        winner = p1
    elif score2 > score1:
        winner = p2
    else:
        winner = None

    if winner:
        st.markdown(
            f"""
            <div class="result-card">
                <div style="font-size:4rem;">🏆</div>
                <h1>{winner['player_name']} wins the Battle!</h1>
                <p class="muted">Outsmarted opponent with superior score and accuracy.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.balloons()
    else:
        st.markdown(
            """
            <div class="result-card">
                <div style="font-size:4rem;">🤝</div>
                <h1>It's a Dead Heat Draw!</h1>
                <p class="muted">Both masterminds finished with matching performance.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("### 📊 Head-to-Head Comparison Analysis")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="card">
                <h2>👤 {p1['player_name']}</h2>
                <div class="big-score">{score1} <span style="font-size:1rem;" class="muted">pts</span></div>
                <hr style="border-color:rgba(255,255,255,0.1)">
                <p>🎯 <b>Correct Answers:</b> {corr1} / {TOTAL_QUESTIONS}</p>
                <p>📈 <b>Accuracy Rate:</b> {acc1}%</p>
                <p>🔥 <b>Best Streak:</b> {streak1}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"""
            <div class="card">
                <h2>👤 {p2['player_name']}</h2>
                <div class="big-score">{score2} <span style="font-size:1rem;" class="muted">pts</span></div>
                <hr style="border-color:rgba(255,255,255,0.1)">
                <p>🎯 <b>Correct Answers:</b> {corr2} / {TOTAL_QUESTIONS}</p>
                <p>📈 <b>Accuracy Rate:</b> {acc2}%</p>
                <p>🔥 <b>Best Streak:</b> {streak2}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()
    current = get_current_player(players)
    if st.button("📊 OPEN MY DASHBOARD", type="primary", use_container_width=True):
        if current:
            st.session_state.dashboard_name = current["player_name"]
        st.query_params.clear()
        st.rerun()


# -----------------------------
# Main Application Flow
# -----------------------------

page_style()

st.markdown("""
<div class="hero">
    <div class="hero-title">🧠 Brain Battle Arena</div>
    <div class="hero-sub">Choose your topics. Challenge your opponent. Outsmart them.</div>
</div>
""", unsafe_allow_html=True)

if "dashboard_name" not in st.session_state:
    st.session_state.dashboard_name = ""

match_code = st.query_params.get("match")
player_param = st.query_params.get("player")

top_left, top_right = st.columns([5, 1])
with top_right:
    if st.button("📊 Dashboard", use_container_width=True):
        st.query_params.clear()
        st.session_state.dashboard_name = ""
        st.rerun()

if not match_code and st.session_state.get("dashboard_name"):
    show_dashboard()
    st.stop()

# Match Creation Screen
if not match_code:
    st.markdown("## ⚔️ Create a New Battle")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    name = st.text_input("Your name", placeholder="Example: Hari")

    selected_topics = st.multiselect("Select exactly 5 topics", TOPICS, max_selections=5, placeholder="Pick five topics...")
    count = len(selected_topics)

    c1, c2 = st.columns([4, 1])
    with c1:
        if count == 5:
            st.success("✅ Perfect. Your battle topics are ready.")
        else:
            st.info(f"Choose {5 - count} more topic(s).")
    with c2:
        st.metric("Topics", f"{count}/5")

    difficulty = st.radio("Choose the challenge level", DIFFICULTIES, horizontal=True)

    if selected_topics:
        cols = st.columns(5)
        for i, topic in enumerate(selected_topics):
            with cols[i]:
                st.markdown(f'<div class="mini-card"><b>🎯</b><br>{topic}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if count == 5 and st.button("🔥 CREATE BATTLE", type="primary", use_container_width=True):
        if not name.strip():
            st.toast("Enter your name first.", icon="⚠️")
            st.stop()

        with st.spinner("⚔️ Building your private arena..."):
            match_id = make_match_code()
            res = supabase.table("matches").insert({
                "match_code": match_id,
                "status": "waiting",
                "topics": selected_topics,
                "difficulty": difficulty
            }).execute()

            if not res.data:
                st.error("Could not create match.")
                st.stop()

            match_row = res.data[0]
            supabase.table("players").insert({
                "match_id": match_row["id"],
                "player_number": 1,
                "player_name": name.strip(),
                "is_ready": True,
                "score": 0,
                "questions_answered": 0,
                "correct_answers": 0,
                "current_question": 0,
                "hints_left": 3,
                "best_streak": 0
            }).execute()
            create_profile(name.strip())

        st.query_params["match"] = match_id
        st.query_params["player"] = "1"
        st.rerun()

    st.stop()

# Existing Match Handling
match = get_match(match_code)
if not match:
    st.error("❌ Match not found.")
    st.stop()

both_finished, players = check_both_players_completed(match["id"])
status = "finished" if both_finished or match.get("status") == "finished" else match.get("status", "waiting")

if status == "finished":
    show_results(match, players)
    st.stop()

if status == "battle":
    battle_fragment(match)
    st.stop()

# Lobby Screen
st.markdown(f"## ⚔️ Match `{match_code}`")
c1, c2, c3 = st.columns(3)
with c1: st.metric("👥 Players", f"{len(players)}/2")
with c2: st.metric("⏱️ Battle Time", "12:00")
with c3: st.metric("🎯 Topics", len(match.get("topics", [])))

st.markdown("### 👥 Battle Lobby")
player_cols = st.columns(2)
for i in range(2):
    p = next((x for x in players if x.get("player_number") == i + 1), None)
    with player_cols[i]:
        if p:
            st.markdown(f'<div class="card"><h3>🟢 Player {i+1}</h3><h2>{p["player_name"]}</h2><p class="muted">Ready for battle</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="card"><h3>🟡 Player {i+1}</h3><p class="muted">Waiting for player...</p></div>', unsafe_allow_html=True)

if len(players) == 1:
    try:
        p_num = int(player_param)
    except (TypeError, ValueError):
        p_num = 1

    if p_num == 1:
        host = st.context.headers.get("Host", "localhost:8501")
        protocol = st.context.headers.get("X-Forwarded-Proto", "http")
        st.code(f"{protocol}://{host}?match={match_code}&player=2", language="text")
        st.caption("Send this link to your opponent.")
        watch_lobby(match)
        st.stop()

    st.markdown("### 🚀 Join the Arena")
    p2_name = st.text_input("Your name", placeholder="Example: Saran")
    if st.button("🚀 JOIN BATTLE", type="primary", use_container_width=True):
        if not p2_name.strip():
            st.toast("Enter your name.", icon="⚠️")
            st.stop()

        supabase.table("players").insert({
            "match_id": match["id"],
            "player_number": 2,
            "player_name": p2_name.strip(),
            "is_ready": True,
            "score": 0,
            "questions_answered": 0,
            "correct_answers": 0,
            "current_question": 0,
            "hints_left": 3,
            "best_streak": 0
        }).execute()
        create_profile(p2_name.strip())
        st.query_params["player"] = "2"
        st.rerun()

    st.stop()

# Both Players Ready Screen
st.success("🎉 Both players are ready!")
try:
    p_num = int(player_param)
except (TypeError, ValueError):
    p_num = 1

if p_num == 1:
    if st.button("🧠 START BATTLE", type="primary", use_container_width=True):
        with st.spinner("🧠 Preparing your 15-question challenge..."):
            try:
                supabase.table("matches").update({"status": "generating"}).eq("id", match["id"]).execute()
                questions = generate_questions(match.get("topics", []), match.get("difficulty", "Mixed"))
                start_time = datetime.now(timezone.utc).isoformat()
                supabase.table("matches").update({
                    "question_set": questions,
                    "battle_start_time": start_time,
                    "status": "battle"
                }).eq("id", match["id"]).execute()
            except Exception as error:
                supabase.table("matches").update({"status": "waiting"}).eq("id", match["id"]).execute()
                st.error("Could not prepare battle.")
                st.code(str(error))
                st.stop()

        st.rerun()
else:
    wait_for_battle(match)