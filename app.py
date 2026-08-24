import streamlit as st
import os
import random
import string
import json
import re
import pandas as pd
import difflib
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



def normalize_question(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def has_internal_duplicates(questions):
    seen = set()
    for question in questions:
        text = normalize_question(question.get("question", ""))
        if not text or text in seen:
            return True
        seen.add(text)
    return False


def question_is_duplicate(question, old_question):
    new_text = normalize_question(question.get("question", ""))
    old_text = normalize_question(old_question)

    if not new_text or not old_text:
        return False

    if new_text == old_text:
        return True

    similarity = difflib.SequenceMatcher(
        None, new_text, old_text
    ).ratio()

    return similarity >= 0.88



def balance_answer_positions(questions):
    """
    Gemini may repeatedly put the correct answer first.
    Randomize the option order while keeping the correct answer
    attached to its value, and deliberately distribute correct
    positions across A/B/C/D.
    """
    positions = [0, 1, 2, 3] * 4 + [0, 1, 2]
    random.shuffle(positions)

    for question, target_position in zip(questions, positions):
        correct = question["answer"]
        wrong = [
            option
            for option in question["options"]
            if option != correct
        ]

        random.shuffle(wrong)

        new_options = []
        wrong_index = 0

        for index in range(4):
            if index == target_position:
                new_options.append(correct)
            else:
                new_options.append(wrong[wrong_index])
                wrong_index += 1

        question["options"] = new_options

    return questions


def question_looks_too_easy(question):
    text = question.get("question", "").lower().strip()

    obvious_recall = [
        "what is the capital",
        "which planet is known",
        "what does cpu stand for",
        "what does gdp stand for",
        "which gas do plants",
        "which sport uses",
        "what year did",
        "who is known as",
    ]

    if any(pattern in text for pattern in obvious_recall):
        return True

    # Very short questions are usually direct-recall questions.
    if len(text.split()) < 8:
        return True

    return False


def validate_requested_difficulty(questions, difficulty):
    if difficulty != "Hard":
        return True

    easy_count = sum(
        1
        for question in questions
        if question_looks_too_easy(question)
    )

    if easy_count > 2:
        raise ValueError(
            "Gemini generated too many questions that are too easy for Hard mode."
        )

    return True




def generate_questions(topics, difficulty):
    topic_text = ", ".join(topics)
    previous_questions = get_previous_questions_avoid_list()

    avoid_text = "\n".join(
        f"- {question}" for question in previous_questions
    )

    prompt = f"""
You are the dedicated AI question engine for Brain Battle Arena.

Create a completely NEW quiz for this battle.

Selected topics: {topic_text}
Difficulty: {difficulty}

Create exactly 15 multiple-choice questions.
Create exactly 3 questions for each of the 5 selected topics.

ABSOLUTE UNIQUENESS RULES:
1. Every question must be newly authored for this battle.
2. NEVER copy a previous question.
3. NEVER paraphrase a previous question.
4. NEVER slightly rewrite an old question.
5. NEVER keep the same structure and only change numbers, names,
   dates, places, values, or options.
6. NEVER reuse the same scenario, reasoning chain, puzzle setup,
   example, or fact pattern.
7. Two questions that test essentially the same idea count as duplicates.
8. Never repeat a question inside this 15-question set.

QUALITY RULES:
- Exactly 4 unique options for every question.
- Exactly one correct answer.
- The answer must exactly match one option.
- Match the requested difficulty exactly.
- Easy: direct recall, one-step calculations, straightforward patterns or simple logic.
- Medium: requires 2-3 reasoning steps, combining concepts, or moderate calculations.
- Hard: requires multi-step reasoning, non-obvious patterns, deeper concept application, edge cases, or careful elimination.
- Do not generate Hard questions that can be solved by simple recall, an obvious pattern, or one basic calculation.
- For Hard questions, make distractor options plausible and require reasoning before selecting an answer.
- The difficulty label must reflect the actual solving effort, not just be a label.
- Questions must be clear, unambiguous, useful and engaging.
- Easy: direct recall, one-step calculations, straightforward patterns or simple logic.
- Medium: requires 2-3 reasoning steps, combining concepts, or moderate calculations.
- Hard: requires multi-step reasoning, non-obvious patterns, deeper concept application, edge cases, or careful elimination.
- Do not generate Hard questions that can be solved by simple recall, obvious patterns, or one basic calculation.
- For Hard questions, make the distractor options plausible and require reasoning before selecting an answer.
- Include a short explanation.
- Do not put the correct answer in the same option position repeatedly.
- Distribute correct answers across A, B, C and D as evenly as possible.
- Return ONLY valid JSON.
- Do not use markdown.

STRICT DO-NOT-USE LIST FROM PREVIOUS BATTLES:
{avoid_text if avoid_text else "No previous questions are available."}

Before returning the JSON, compare every generated question with the
DO-NOT-USE list and replace anything that is identical, very similar,
paraphrased, structurally recycled, or only numerically changed.

Return exactly this structure:
[
  {{
    "topic": "Science",
    "difficulty": "Medium",
    "question": "Question here",
    "options": ["A", "B", "C", "D"],
    "answer": "A",
    "explanation": "Short explanation"
  }}
]
"""

    for attempt in range(5):
        try:
            response = gemini.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )

            questions = json.loads(
                clean_ai_json(response.text)
            )

            questions = validate_questions(
                questions,
                topics
            )

            validate_requested_difficulty(
                questions,
                difficulty
            )

            if has_internal_duplicates(questions):
                raise ValueError(
                    "Gemini generated duplicate questions."
                )

            for question in questions:
                for old_question in previous_questions:
                    if question_is_duplicate(
                        question,
                        old_question
                    ):
                        raise ValueError(
                            "Gemini generated a repeated or similar question."
                        )

            questions = balance_answer_positions(questions)
            # Correct-answer positions are redistributed after generation.
            random.shuffle(questions)
            return questions

        except Exception as error:
            if attempt < 4:
                time.sleep(1)

    st.error(
        "Gemini could not create a sufficiently unique quiz. "
        "Please try starting the battle again."
    )
    st.stop()


# -----------------------------
# Profiles & Safe Handling
# -----------------------------

def create_profile(name):
    name = name.strip()

    if not name:
        return None

    try:
        result = (
            supabase
            .table("profiles")
            .select("*")
            .eq("player_name", name)
            .limit(1)
            .execute()
        )

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
            return False

        total_xp = profile.get("total_xp", 0) or 0
        matches_played = profile.get("matches_played", 0) or 0
        wins = profile.get("wins", 0) or 0
        losses = profile.get("losses", 0) or 0
        draws = profile.get("draws", 0) or 0
        total_score = profile.get("total_score", 0) or 0
        best_streak = profile.get("best_streak", 0) or 0

        xp_gain = (
            score + 500 if result_type == "win"
            else score + 200 if result_type == "draw"
            else score + 100
        )

        if result_type == "win":
            wins += 1
        elif result_type == "loss":
            losses += 1
        else:
            draws += 1

        payload = {
            "total_xp": total_xp + xp_gain,
            "matches_played": matches_played + 1,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "total_score": total_score + score,
            "best_streak": max(best_streak, streak)
        }

        (
            supabase
            .table("profiles")
            .update(payload)
            .eq("id", profile["id"])
            .execute()
        )

        return True

    except Exception:
        return False


# -----------------------------
# Completion & Race Condition Guard
# -----------------------------


def save_match_result(match, players, winner_player):
    try:
        existing = (
            supabase
            .table("match_results")
            .select("id")
            .eq("match_id", match["id"])
            .limit(1)
            .execute()
        )

        if existing.data:
            return True

        p1, p2 = players[0], players[1]

        correct1 = p1.get("correct_answers", 0) or 0
        correct2 = p2.get("correct_answers", 0) or 0

        return bool(
            supabase
            .table("match_results")
            .insert({
                "match_id": match["id"],
                "player1_score": p1.get("score", 0) or 0,
                "player2_score": p2.get("score", 0) or 0,
                "winner_player": winner_player,
                "player1_accuracy": round(
                    (correct1 / TOTAL_QUESTIONS) * 100,
                    2
                ),
                "player2_accuracy": round(
                    (correct2 / TOTAL_QUESTIONS) * 100,
                    2
                )
            })
            .execute()
            .data
        )

    except Exception:
        return False


def finish_battle(match, players):
    if len(players) < 2:
        return False

    p1, p2 = players[0], players[1]

    if (p1.get("current_question", 0) or 0) < TOTAL_QUESTIONS:
        return False

    if (p2.get("current_question", 0) or 0) < TOTAL_QUESTIONS:
        return False

    score1 = p1.get("score", 0) or 0
    score2 = p2.get("score", 0) or 0

    if score1 > score2:
        result1, result2 = "win", "loss"
        winner_player = 1
    elif score2 > score1:
        result1, result2 = "loss", "win"
        winner_player = 2
    else:
        result1 = result2 = "draw"
        winner_player = None

    try:
        # Change the status only if the match is still in battle state.
        supabase.table("matches").update({
            "status": "finished"
        }).eq(
            "id",
            match["id"]
        ).eq(
            "status",
            "battle"
        ).execute()
    except Exception:
        pass

    # Save the final match result independently from profile updates.
    save_match_result(
        match,
        players,
        winner_player
    )

    # Profile updates must never stop the result screen.
    save_profile_after_match(
        p1["player_name"],
        score1,
        result1,
        p1.get("best_streak", 0) or 0
    )

    save_profile_after_match(
        p2["player_name"],
        score2,
        result2,
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





def build_battle_dataframe(p1, p2):
    rows = [
        {
            "Player": p1["player_name"],
            "Score": p1.get("score", 0) or 0,
            "Correct": p1.get("correct_answers", 0) or 0,
            "Accuracy": round(((p1.get("correct_answers", 0) or 0) / TOTAL_QUESTIONS) * 100),
            "Best Streak": p1.get("best_streak", 0) or 0
        },
        {
            "Player": p2["player_name"],
            "Score": p2.get("score", 0) or 0,
            "Correct": p2.get("correct_answers", 0) or 0,
            "Accuracy": round(((p2.get("correct_answers", 0) or 0) / TOTAL_QUESTIONS) * 100),
            "Best Streak": p2.get("best_streak", 0) or 0
        }
    ]
    return pd.DataFrame(rows)


# -----------------------------
# Dashboard & Detailed Comparison
# -----------------------------


def get_dashboard_history(name):
    try:
        result = (
            supabase
            .table("players")
            .select(
                "match_id, player_number, player_name, "
                "score, correct_answers, best_streak"
            )
            .eq("player_name", name)
            .execute()
        )

        rows = result.data or []

        completed_matches = 0
        wins = 0
        losses = 0
        draws = 0
        total_score = 0
        total_xp = 0
        best_streak = 0

        seen_matches = set()

        for row in rows:
            match_id = row.get("match_id")

            if not match_id or match_id in seen_matches:
                continue

            match_result = (
                supabase
                .table("matches")
                .select("id, status")
                .eq("id", match_id)
                .limit(1)
                .execute()
            )

            if (
                not match_result.data
                or match_result.data[0].get("status") != "finished"
            ):
                continue

            match_players = (
                supabase
                .table("players")
                .select(
                    "player_number, player_name, "
                    "score, best_streak"
                )
                .eq("match_id", match_id)
                .order("player_number")
                .execute()
            ).data or []

            if len(match_players) < 2:
                continue

            me = next(
                (
                    player
                    for player in match_players
                    if player["player_name"] == name
                ),
                None
            )

            opponent = next(
                (
                    player
                    for player in match_players
                    if player["player_name"] != name
                ),
                None
            )

            if not me or not opponent:
                continue

            seen_matches.add(match_id)
            completed_matches += 1

            my_score = me.get("score", 0) or 0
            opponent_score = opponent.get("score", 0) or 0

            total_score += my_score
            best_streak = max(
                best_streak,
                me.get("best_streak", 0) or 0
            )

            if my_score > opponent_score:
                wins += 1
                total_xp += my_score + 500
            elif my_score < opponent_score:
                losses += 1
                total_xp += my_score + 100
            else:
                draws += 1
                total_xp += my_score + 200

        return {
            "matches_played": completed_matches,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "total_score": total_score,
            "total_xp": total_xp,
            "best_streak": best_streak
        }

    except Exception:
        return {
            "matches_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "total_score": 0,
            "total_xp": 0,
            "best_streak": 0
        }


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

    history = get_dashboard_history(name)

    if not profile and history["matches_played"] == 0:
        st.info("No completed battle history is available for this player yet.")
        show_leaderboard()
        return

    profile_matches = profile.get("matches_played", 0) if profile else 0
    profile_matches = profile_matches or 0
    profile_wins = profile.get("wins", 0) if profile else 0
    profile_wins = profile_wins or 0
    profile_losses = profile.get("losses", 0) if profile else 0
    profile_losses = profile_losses or 0
    profile_draws = profile.get("draws", 0) if profile else 0
    profile_draws = profile_draws or 0
    profile_score = profile.get("total_score", 0) if profile else 0
    profile_score = profile_score or 0

    matches = max(profile_matches, history["matches_played"])
    wins = max(profile_wins, history["wins"])
    losses = max(profile_losses, history["losses"])
    draws = max(profile_draws, history["draws"])

    profile_xp = profile.get("total_xp", 0) if profile else 0
    profile_xp = profile_xp or 0
    xp = max(profile_xp, history["total_xp"])

    score = max(profile_score, history["total_score"])

    profile_streak = profile.get("best_streak", 0) if profile else 0
    profile_streak = profile_streak or 0
    streak = max(profile_streak, history["best_streak"])

    win_rate = round(wins / matches * 100) if matches else 0
    level = (xp // 1000) + 1
    level_xp = xp % 1000

    st.markdown(f'<div class="card"><h2>👋 Welcome back, {name}</h2><p class="muted">Keep battling and climb the arena leaderboard.</p></div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🏟️ Matches", matches, delta=f"{wins} wins")
    with c2:
        st.metric("🏆 Wins", wins, delta=f"{wins - losses:+d} net")
    with c3:
        st.metric("📈 Win Rate", f"{win_rate}%", delta=f"{win_rate - 50:+d}% vs 50%")
    with c4:
        st.metric("⭐ XP", xp, delta=f"Level {level}")

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





@st.fragment(run_every=2)
def wait_for_opponent_finish(match, player_id):
    latest = get_match(match["match_code"])

    if not latest:
        st.error("Match could not be found.")
        return

    both_done, players = check_both_players_completed(
        latest["id"]
    )

    if both_done or latest.get("status") == "finished":
        finish_battle(latest, players)

        st.toast(
            "🏆 Battle complete! Showing results...",
            icon="🏆"
        )

        st.rerun(scope="app")
        return

    opponent = next(
        (
            p for p in players
            if p["id"] != player_id
        ),
        None
    )

    st.markdown("""
    <div class="result-card">
        <div style="font-size:3rem;">🎉</div>
        <h2>You finished all 15 questions!</h2>
        <p class="muted">
            Your answers are saved. Waiting for your opponent to finish...
        </p>
    </div>
    """, unsafe_allow_html=True)

    if opponent:
        completed = opponent.get(
            "current_question",
            0
        ) or 0

        st.progress(
            min(completed / TOTAL_QUESTIONS, 1.0)
        )

        st.caption(
            f"👤 {opponent['player_name']}: "
            f"{completed}/{TOTAL_QUESTIONS} completed"
        )

    st.caption(
        "This screen updates automatically."
    )


@st.fragment(run_every=1)
def battle_timer(match):
    latest = get_match(match["match_code"])

    if not latest:
        return

    remaining = get_remaining_seconds(latest)

    if remaining is None:
        return

    remaining = max(remaining, 0)
    minutes = remaining // 60
    seconds = remaining % 60

    st.metric(
        "⏱️ Time",
        f"{minutes:02d}:{seconds:02d}"
    )


@st.fragment(run_every=2)
def opponent_progress(match, current_player_id, total):
    latest_players = get_players(match["id"])

    opponent = next(
        (
            player for player in latest_players
            if player["id"] != current_player_id
        ),
        None
    )

    if not opponent:
        return

    st.markdown("### 👤 Opponent")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.write(f"**{opponent['player_name']}**")

    with c2:
        answered = opponent.get("questions_answered", 0) or 0
        st.write(f"📝 {answered}/{total}")

    with c3:
        st.write(f"⭐ {opponent.get('score', 0) or 0} XP")


@st.fragment
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

    # Completed players are routed by the main flow to
    # wait_for_opponent_finish(), which is the only polling section.

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

    st.markdown("""
    <div class="hero">
        <div class="hero-title" style="font-size:2.2rem;">⚔️ Battle Mode</div>
        <div class="hero-sub">Think fast. Choose wisely. Beat your opponent.</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)

    with c1:
        battle_timer(latest_match)

    with c2:
        st.metric(
            "⭐ Score",
            current_player.get("score", 0) or 0
        )

    with c3:
        st.metric(
            "🔥 Streak",
            current_player.get("best_streak", 0) or 0
        )

    st.caption(
        f"📝 Question {question_number + 1} of {total}"
    )

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

    with st.form("answer_form", clear_on_submit=False):
        answer = st.radio(
            "Choose your answer",
            options,
            key=f"answer_{current_player['id']}_{question_number}"
        )

        hints_left = current_player.get("hints_left", 0) or 0

        hint_col, submit_col = st.columns([1, 3])

        with hint_col:
            hint = st.form_submit_button(
                f"💡 Hint ({hints_left})",
                use_container_width=True,
                disabled=hints_left <= 0
            )

        with submit_col:
            submit = st.form_submit_button(
                "✅ SUBMIT ANSWER",
                type="primary",
                use_container_width=True
            )

    if hint and hints_left > 0:
        wrong = [
            option for option in options
            if option != question["answer"]
        ]

        if wrong:
            st.info(
                f"💡 You can eliminate: **{random.choice(wrong)}**"
            )

            supabase.table("players").update({
                "hints_left": hints_left - 1
            }).eq(
                "id",
                current_player["id"]
            ).execute()

            st.toast(
                "Hint used!",
                icon="💡"
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

            # Only Q15 changes the page flow. Normal answers stay
            # inside the battle fragment, so the UI does not blink.
            st.rerun(scope="app")
            return

        st.rerun(scope="fragment")


    st.divider()

    opponent_progress(
        latest_match,
        current_player["id"],
        total
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

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "⭐ Score",
            score1,
            delta=score1 - score2
        )

    with c2:
        st.metric(
            "🎯 Correct",
            corr1,
            delta=corr1 - corr2
        )

    with c3:
        st.metric(
            "📈 Accuracy",
            f"{acc1}%",
            delta=f"{acc1 - acc2}%"
        )

    with c4:
        st.metric(
            "🔥 Best Streak",
            streak1,
            delta=streak1 - streak2
        )

    comparison_df = build_battle_dataframe(p1, p2)

    st.dataframe(
        comparison_df,
        use_container_width=True,
        hide_index=True
    )

    with st.expander("📋 Question Review"):
        try:
            answer_result = (
                supabase
                .table("answers")
                .select("*")
                .eq("match_id", match["id"])
                .execute()
            )

            answer_rows = answer_result.data or []
            questions = safe_json(match.get("question_set")) or []
            review_rows = []

            for row in answer_rows:
                number = row.get("question_number", 0) or 0
                question_text = ""
                topic = ""

                if 1 <= number <= len(questions):
                    question_text = questions[number - 1].get("question", "")
                    topic = questions[number - 1].get("topic", "")

                review_rows.append({
                    "Player": row.get("player_id", ""),
                    "Question": question_text,
                    "Topic": topic,
                    "Correct": bool(row.get("is_correct", False))
                })

            if review_rows:
                review_df = pd.DataFrame(review_rows)

                st.data_editor(
                    review_df,
                    use_container_width=True,
                    hide_index=True,
                    disabled=True
                )
            else:
                st.info("No answer review data available.")
        except Exception:
            st.info("Question review is unavailable for this match.")

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
    current_player = get_current_player(players)

    if (
        current_player
        and (current_player.get("current_question", 0) or 0) >= TOTAL_QUESTIONS
    ):
        wait_for_opponent_finish(
            match,
            current_player["id"]
        )
    else:
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
