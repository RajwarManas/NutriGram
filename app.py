from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from googletrans import Translator
from langdetect import detect
import pandas as pd
from pulp import LpProblem, LpVariable, LpMinimize, lpSum, PULP_CBC_CMD
import spacy
import re
import en_core_web_sm

app = Flask(__name__)
translator = Translator()
nlp = en_core_web_sm.load()

# supported languages
SUPPORTED_LANGS = {
    "en": "English", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil",
    "te": "Telugu", "mr": "Marathi", "gu": "Gujarati", "kn": "Kannada",
    "ml": "Malayalam", "pa": "Punjabi", "or": "Odia"
}

# loading food data
try:
    food_df = pd.read_csv("fssai_food_data.csv")
    food_df["approx_price_per_100g_INR"] = food_df["approx_price_per_100g_INR"].replace(0, 0.01)
    print(f"Loaded {len(food_df)} foods")
except Exception as e:
    print(f"CSV error: {e}")
    food_df = pd.DataFrame()

# current regions
CURRENT_REGIONS = ["North", "South", "East", "West"]

def detect_region(text):
    text = text.lower()
    for r in CURRENT_REGIONS:
        if r.lower() in text:
            return r
    # keywords for regions
    keywords = {
        "North": ["north", "uttar", "उत्तर", "উত্তর", "வடக்கு", "ఉత్తర", "उत्तर", "ਉੱਤਰ", "ଉତ୍ତର"],
        "South": ["south", "dakshin", "दक्षिण", "দক্ষিণ", "தெற்கு", "దక్షিণ", "दक्षिण", "ਦੱਖਣ", "ଦକ୍ଷିଣ"],
        "East":  ["east",  "purab",  "पूर्व",  "পূর্ব",  "கிழக்கு", "తూర్పు", "पूर्व", "ਪੂਰਬ", "ପୂର୍ବ"],
        "West":  ["west",  "paschim", "पश्चिम", "পশ্চিম", "மேற்கு", "పశ్చిమ", "पश्चिम", "ਪੱਛਮ", "ପଶ୍ଚିମ"]
    }
    for r, words in keywords.items():
        if any(w in text for w in words):
            return r
    return None

def parse_user_input(user_input):
    try:
        lang = detect(user_input)
        user_lang = lang if lang in SUPPORTED_LANGS else "en"
        text_en = user_input.lower() if user_lang == "en" else translator.translate(user_input, dest="en").text.lower()
        print(f"[{user_lang}] {user_input} -> {text_en}")

        region = detect_region(text_en)
        if not region:
            return None, None, None, None, user_lang

        doc = nlp(text_en)
        calories = protein = None
        for ent in doc.ents:
            if ent.label_ == "CARDINAL":
                n = int(ent.text)
                if 1400 <= n <= 2500 and not calories:
                    calories = n
                elif 50 <= n <= 200 and not protein:
                    protein = n

        if not calories:
            m = re.search(r'\b(1[5-9]\d{2}|2[0-2]\d{2})\b', text_en)
            if m: calories = int(m.group())
        if not protein:
            m = re.search(r'\b(\d{2,3})\s*g\b', text_en)
            if m: protein = int(m.group(1))

        budget = "cheap"
        if any(k in text_en for k in ["expensive", "premium", "महंगा", "দামি", "விலையுயர்ந்த"]):
            budget = "expensive"

        return region, calories or 2000, protein or 80, budget, user_lang

    except Exception as e:
        print(f"Parse error: {e}")
        return None, None, None, None, "en"

def solve_meal_plan(region, cal_goal, prot_goal, budget, foods_df):
    prob = LpProblem("Meal", LpMinimize)
    vars = {row['food']: LpVariable(row['food'], lowBound=0) for _, row in foods_df.iterrows()}

    # cheap: min cost, expensive: min weight
    if budget == "expensive":
        prob += lpSum(vars.values())
    else:
        prob += lpSum(vars[r['food']] * r["approx_price_per_100g_INR"] for _, r in foods_df.iterrows())

    # calorie & protein constraints
    prob += lpSum((r["calories_per_100g"]/100) * vars[r['food']] for _, r in foods_df.iterrows()) >= cal_goal * 0.9
    prob += lpSum((r["calories_per_100g"]/100) * vars[r['food']] for _, r in foods_df.iterrows()) <= cal_goal * 1.1
    prob += lpSum((r["protein_g_per_100g"]/100) * vars[r['food']] for _, r in foods_df.iterrows()) >= prot_goal * 0.9
    prob += lpSum((r["protein_g_per_100g"]/100) * vars[r['food']] for _, r in foods_df.iterrows()) <= prot_goal * 1.1

    prob += lpSum(vars.values()) <= 6000

    limits = {"meat": 250, "dal": 100, "carb": 150, "veg": 150, "fat": 30, "garnish": 50}
    for _, r in foods_df.iterrows():
        max_g = limits.get(r['group'], 200)
        prob += vars[r['food']] <= max_g

    prob.solve(PULP_CBC_CMD(msg=0))
    return prob, vars

def format_meal_plan(total_cal, total_prot, total_cost, items, lang):
    lines = ["Optimized Meal Plan:"]
    for food, g, c, p, cost in items:
        lines.append(f"* {food}: {g:.0f}g -> {c:.0f} kcal, {p:.1f}g protein, Rs.{cost:.2f}")
    lines.append(f"\nTotal: {total_cal:.0f} kcal, {total_prot:.1f}g protein, Rs.{total_cost:.2f}")
    msg = "\n".join(lines)
    try:
        return translator.translate(msg, dest=lang).text
    except:
        return msg

@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    resp = MessagingResponse()
    msg = request.values.get('Body', '').strip()
    if not msg:
        resp.message("Send your request!")
        return str(resp)

    region, cal, prot, budget, lang = parse_user_input(msg)
    if not region:
        resp.message(translator.translate("Try: North 2000cal 120g cheap", dest=lang).text)
        return str(resp)

    foods = food_df[food_df["region"] == region].copy()
    if foods.empty:
        resp.message(translator.translate("No foods for this region.", dest=lang).text)
        return str(resp)

    prob, vars = solve_meal_plan(region, cal, prot, budget, foods)
    if prob.status != 1:
        resp.message(translator.translate("Can't make a plan. Try different goals.", dest=lang).text)
        return str(resp)

    total_cal = total_prot = total_cost = 0
    items = []
    for _, r in foods.iterrows():
        g = vars[r['food']].value()
        if g and g > 0:
            c = (g/100) * r["calories_per_100g"]
            p = (g/100) * r["protein_g_per_100g"]
            cost = (g/100) * r["approx_price_per_100g_INR"]
            total_cal += c
            total_prot += p
            total_cost += cost
            items.append((r['food'], g, c, p, cost))

    if not items:
        resp.message(translator.translate("No foods selected.", dest=lang).text)
        return str(resp)

    resp.message(format_meal_plan(total_cal, total_prot, total_cost, items, lang))
    return str(resp)

if __name__ == "__main__":
    app.run(port=5000, debug=True)