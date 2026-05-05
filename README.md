# NutriGram

## Overview

NutriGram is an AI-powered meal recommendation system that generates cost-efficient, nutritionally balanced meal plans based on user input. The system integrates natural language processing, multilingual support, and linear programming optimization, and is accessible via WhatsApp.

## Features

* 📱 WhatsApp-based interaction using Twilio API
* 🌍 Multilingual input support (Hindi, English, and regional languages)
* 🧠 NLP-based parsing of user requirements (calories, protein, region, budget)
* ⚙️ Linear Programming optimization using PuLP
* 💰 Cost-efficient or premium meal plan generation
* 📊 Region-based food filtering (North, South, East, West India)

## Tech Stack

* **Backend:** Python (Flask)
* **APIs:** Twilio WhatsApp API
* **NLP:** spaCy, langdetect, Google Translate API
* **Optimization:** PuLP (Linear Programming)
* **Data Handling:** Pandas
* **Dataset:** FSSAI-based food dataset

## How It Works

1. User sends a message via WhatsApp (e.g., "North 2000 calories 120g protein cheap")
2. System detects language and translates input to English
3. NLP extracts key parameters (region, calories, protein, budget)
4. Food dataset is filtered based on region
5. Linear programming model optimizes food selection:

   * Meets calorie & protein constraints
   * Minimizes cost (or weight for premium mode)
6. Optimized meal plan is generated and sent back in the user's language

## Optimization Model

* Objective:

  * Minimize cost (cheap mode)
  * Minimize quantity (premium mode)
* Constraints:

  * Calorie range (±10%)
  * Protein range (±10%)
  * Food group limits (meat, carbs, etc.)
  * Total weight limit (≤ 6kg)

## Installation & Setup

```bash
git clone https://github.com/RajwarManas/NutriGram.git
cd NutriGram
pip install -r requirements.txt
python app.py
```

## Example Input

```
South 1800 calories 100g protein cheap
```

## Example Output

```
Optimized Meal Plan:
* Rice: 200g -> 260 kcal, 5g protein, Rs.20
* Chicken: 150g -> 300 kcal, 30g protein, Rs.90
...
Total: 1800 kcal, 100g protein, Rs.150
```

## What I Learned

* Applying **linear programming** to real-world optimization problems
* Building NLP pipelines for extracting structured data from text
* Handling multilingual input using translation + language detection
* Designing constraint-based systems with trade-offs (cost vs nutrition)
* Integrating backend logic with messaging platforms (WhatsApp APIs)

## Limitations

* Relies on static dataset (no real-time nutrition updates)
* Limited personalization (no taste preferences or allergies)
* NLP parsing may fail for ambiguous inputs

## Future Improvements

* Add user preference modeling (taste, allergies)
* Expand dataset with real-time APIs
* Build a web/mobile UI
* Improve NLP accuracy with custom models

## Author

Manas Rajwar
GitHub: https://github.com/RajwarManas
