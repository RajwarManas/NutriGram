from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from googletrans import Translator
from langdetect import detect
import pandas as pd
from pulp import LpProblem, LpVariable, LpMinimize, lpSum, PULP_CBC_CMD
import re
import spacy
import en_core_web_sm

app = Flask(__name__)
translator = Translator()
nlp = en_core_web_sm.load()
supported_languages = {"en": "English", "hi": "Hindi", "ta": "Tamil", "bn": "Bengali"}

# Output format
def format_meal_plan(total_calories, total_protein, total_cost, foods, lang):
    output = "🍽️ Optimized Meal Plan:\n"
    for food, grams, cal, prot, cost in foods:
        output += f"• {food}: {grams:.0f}g → {cal:.0f} kcal, {prot:.1f}g protein, ₹{cost:.2f}\n"
    output += f"\n📊 Estimated Total: {total_calories:.0f} kcal, {total_protein:.1f}g protein, ₹{total_cost:.2f}"
    try:
        return translator.translate(output, dest=lang).text
    except Exception as e:
        print(f"Translation error: {e}. Returning in English.")
        return output

def solve_meal_plan(user_region, calorie_goal, protein_goal, budget_pref, regional_foods, user_lang):
    prob = LpProblem("NutritionOptimizer", LpMinimize)
    food_vars = {row['food']: LpVariable(row['food'], lowBound=0) for idx, row in regional_foods.iterrows()}
    if budget_pref in ["premium", "expensive"]:
        prob += lpSum([food_vars[row['food']] for idx, row in regional_foods.iterrows()])
    else:
        prob += lpSum([food_vars[row['food']] * row["approx_price_per_100g_INR"] for idx, row in regional_foods.iterrows()])
    # Constraints for creating a balanced meal
    prob += lpSum([(row["calories_per_100g"]/100) * food_vars[row['food']] for idx, row in regional_foods.iterrows()]) >= calorie_goal * 0.90
    prob += lpSum([(row["calories_per_100g"]/100) * food_vars[row['food']] for idx, row in regional_foods.iterrows()]) <= calorie_goal * 1.10
    prob += lpSum([(row["protein_g_per_100g"]/100) * food_vars[row['food']] for idx, row in regional_foods.iterrows()]) >= protein_goal * 0.90
    prob += lpSum([(row["protein_g_per_100g"]/100) * food_vars[row['food']] for idx, row in regional_foods.iterrows()]) <= protein_goal * 1.10
    prob += lpSum([food_vars[row['food']] for idx, row in regional_foods.iterrows()]) <= 6000
    min_group_grams = {"protein": 100, "carb": 150, "veg": 100, "fat": 10}
    max_group_grams = {"meat": 600, "dal": 200, "carb": 400, "veg": 300, "fat": 40}
    for group, min_g in min_group_grams.items():
        if any(row['group'] == group for idx, row in regional_foods.iterrows()):
            prob += lpSum([food_vars[row['food']] for idx, row in regional_foods.iterrows() if row['group'] == group]) >= min_g
    for group, max_g in max_group_grams.items():
        if any(row['group'] == group for idx, row in regional_foods.iterrows()):
            prob += lpSum([food_vars[row['food']] for idx, row in regional_foods.iterrows() if row['group'] == group]) <= max_g
    for idx, row in regional_foods.iterrows():
        if row['group'] == "meat":
            prob += food_vars[row['food']] <= 250
        elif row['group'] == "dal":
            prob += food_vars[row['food']] <= 100
        elif row['group'] == "carb":
            prob += food_vars[row['food']] <= 150
        elif row['group'] == "veg":
            prob += food_vars[row['food']] <= 150
        elif row['group'] == "fat":
            prob += food_vars[row['food']] <= 30
        elif row['group'] == "garnish":
            prob += food_vars[row['food']] <= 50
    prob.solve(PULP_CBC_CMD(msg=1))
    print(f"Solver status: {prob.status}, Region: {user_region}")
    return prob, food_vars

@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    user_input = request.values.get('Body', '').strip()
    resp = MessagingResponse()
    try:
        user_lang = detect(user_input)
        if user_lang not in supported_languages:
            user_lang = "en"
            resp.message(translator.translate("Language not supported. Using English.", dest=user_lang).text)
            return str(resp)
        # Translating user input into English
        user_input_en = user_input if user_lang == "en" else translator.translate(user_input, dest="en").text
        print(f"Input: {user_input}, Translated: {user_input_en}")
        # Common translation issues fix
        user_input_en = (user_input_en.replace("Answer", "North")
                        .replace("northward", "North")
                        .replace("calorie", "kcal")
                        .replace("Calories", "kcal")
                        .replace("inexpensive", "cheap")
                        .replace("low cost", "cheap"))
        if "120" in user_input_en and "120g" not in user_input_en:
            user_input_en = user_input_en.replace("120", "120g")
        print(f"Fixed translation: {user_input_en}")
        # Parse user region
        regions = ["North", "South", "East", "West"]
        doc = nlp(user_input_en)
        user_region = next((token.text.title() for token in doc if token.text.title() in regions), None)
        if not user_region:
            print("No region detected")
            resp.message(translator.translate("Couldn't detect region. Reply with region (North/South/East/West).", dest=user_lang).text)
            return str(resp)
        # Parse calories and protein goals 
        calorie_match = re.search(r'(?:(\d+)\s*(?:kcal|cal|cals|calories?))|(?:(?:kcal|cal|cals|calories?)\s*(\d+))', user_input_en, re.IGNORECASE)
        protein_match = re.search(r'(?:(\d+)\s*g\s*(?:protein|pro)?)|(?:(?:protein|pro)\s*(\d+))', user_input_en, re.IGNORECASE)
        calorie_goal = int(calorie_match.group(1) or calorie_match.group(2)) if calorie_match else 2000
        protein_goal = int(protein_match.group(1) or protein_match.group(2)) if protein_match else 80
        budget_keywords = ["cheap", "affordable", "budget", "low cost", "expensive", "premium"]
        budget_pref = next((kw for kw in budget_keywords if kw in user_input_en.lower()), "affordable")
        print(f"Parsed: Region={user_region}, Calories={calorie_goal}, Protein={protein_goal}, Budget={budget_pref}")
        # Loading CSV
        df = pd.read_csv("fssai_food_data.csv")
        regional_foods = df[df["region"] == user_region].copy()
        print(f"Regional foods for {user_region}: {len(regional_foods)} foods found")
        if regional_foods.empty:
            print("No foods found for region")
            resp.message(translator.translate("No foods found for your region. Try a different region.", dest=user_lang).text)
            return str(resp)
        regional_foods["approx_price_per_100g_INR"] = regional_foods["approx_price_per_100g_INR"].replace(0, 0.01)
        # Optimizing meal plan
        prob, food_vars = solve_meal_plan(user_region, calorie_goal, protein_goal, budget_pref, regional_foods, user_lang)
        if prob.status != 1:
            print(f"Infeasible. Foods: {regional_foods['food'].tolist()}")
            resp.message(translator.translate("No meal plan possible with current foods. Try a different region or adjust goals.", dest=user_lang).text)
            return str(resp)
        # Building meal plan
        total_calories = 0
        total_protein = 0
        total_cost = 0
        foods = []
        for idx, row in regional_foods.iterrows():
            grams = food_vars[row['food']].value()
            if grams and grams > 0:
                cal = (grams/100) * row["calories_per_100g"]
                prot = (grams/100) * row["protein_g_per_100g"]
                cost = (grams/100) * row["approx_price_per_100g_INR"]
                total_calories += cal
                total_protein += prot
                total_cost += cost
                foods.append((row['food'], grams, cal, prot, cost))
        if not foods:
            print("No foods selected in solution")
            resp.message(translator.translate("No foods could be selected. Try a different region or check food data.", dest=user_lang).text)
            return str(resp)
        meal_plan = format_meal_plan(total_calories, total_protein, total_cost, foods, user_lang)
        resp.message(meal_plan)
    except Exception as e:
        print(f"Error: {e}")
        resp.message(translator.translate("Error: Try 'North 2000 kcal 80g protein cheap' in English, Hindi, Tamil, or Bengali.", dest=user_lang).text)
    return str(resp)

if __name__ == "__main__":
    app.run(port=5000)