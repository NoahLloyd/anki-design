#!/usr/bin/env python3
"""Seed an isolated demo Anki base with ~4 years of believable review history.

Built for showcasing Anki Design's heatmap, progress bar, and reviewer chrome:
the demo decks match the largest Anki user groups (med students using the
AnKing-style workflow, language learners, geography buffs, CS students), and
each card carries a per-day revlog history that lights up the heatmap.

Safety
------
- Default target is a separate base at
  ~/Library/Application Support/Anki2-dev/anki-design-demo
  that is touched ONLY by this script. Your real ~/Library/Application
  Support/Anki2 collection is never opened, read, or modified.
- The script refuses to run if the resolved target is the real Anki2 base.
- If the target already contains a non-empty collection, the script refuses
  to proceed unless --force is passed.

Usage
-----
    # From the anki-design worktree root:
    "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" \\
        scripts/seed_demo.py

    # Customize:
    ... scripts/seed_demo.py --base /custom/base --years 6 --force
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Anki ships its own venv; this script must run inside it so `import anki`
# resolves to the Rust-backed library that owns the unicase collation.
try:
    from anki.collection import Collection
except ImportError:  # pragma: no cover - friendly error for wrong interpreter
    sys.stderr.write(
        "error: cannot import anki — run with Anki's bundled python:\n"
        '  "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" '
        "scripts/seed_demo.py\n"
    )
    raise SystemExit(2)


REAL_BASE = Path.home() / "Library" / "Application Support" / "Anki2"
DEFAULT_DEMO_BASE = (
    Path.home() / "Library" / "Application Support" / "Anki2-dev" / "anki-design-demo"
)
PROFILE_NAME = "User 1"

DAY = 86_400


# ---------------------------------------------------------------------------
# Deck content. Five themes spanning the biggest Anki user populations:
#   - Medical students (USMLE-style anatomy, pathology, pharmacology)
#   - Spanish language learners (1k-most-common-words style)
#   - Japanese language learners (JLPT N5 hiragana + vocab)
#   - Geography / general knowledge
#   - CS students (Big-O, data structures, algorithms)
#
# Each entry is (front, back). Light by design: enough variety to feel real
# without bloating the script. Card counts per deck land around 40–80, total
# ~300 cards — enough to make scheduling/revlog look impressive without
# slowing the seed.
# ---------------------------------------------------------------------------

MEDICAL_PATHOLOGY = [
    ("Tachycardia", "Heart rate > 100 bpm"),
    ("Bradycardia", "Heart rate < 60 bpm"),
    ("Hypertension (stage 1)", "Systolic 130–139 or diastolic 80–89 mmHg"),
    ("Hypotension", "Systolic < 90 or diastolic < 60 mmHg"),
    ("Atrial fibrillation", "Irregularly irregular rhythm; loss of P waves"),
    ("ST elevation MI (STEMI)", "Transmural ischemia; ST elevation in ≥2 contiguous leads"),
    ("Anemia (men)", "Hemoglobin < 13.5 g/dL"),
    ("Anemia (women)", "Hemoglobin < 12.0 g/dL"),
    ("Leukocytosis", "WBC > 11,000 / µL"),
    ("Thrombocytopenia", "Platelets < 150,000 / µL"),
    ("DKA triad", "Hyperglycemia, ketonemia, anion-gap metabolic acidosis"),
    ("Cushing's triad", "Bradycardia, hypertension, irregular respirations (↑ICP)"),
    ("Virchow's triad", "Stasis, endothelial injury, hypercoagulability"),
    ("Charcot's triad", "Fever, jaundice, RUQ pain (cholangitis)"),
    ("Beck's triad", "Hypotension, JVD, muffled heart sounds (tamponade)"),
    ("Cushing's syndrome", "Chronic hypercortisolism — moon facies, buffalo hump, striae"),
    ("Addison's disease", "Primary adrenal insufficiency — hyperpigmentation, hyponatremia"),
    ("Graves' disease", "Autoimmune hyperthyroidism (TSI antibodies)"),
    ("Hashimoto's thyroiditis", "Autoimmune hypothyroidism (anti-TPO antibodies)"),
    ("Type 1 diabetes", "Autoimmune β-cell destruction; absolute insulin deficiency"),
    ("Type 2 diabetes", "Insulin resistance + relative insulin deficiency"),
    ("Crohn's disease", "Transmural inflammation, skip lesions, anywhere mouth → anus"),
    ("Ulcerative colitis", "Continuous mucosal inflammation limited to colon"),
    ("Celiac disease", "Gluten-induced villous atrophy; anti-tTG antibodies"),
    ("Pancreatitis (acute)", "Lipase > 3× ULN + epigastric pain radiating to back"),
    ("COPD spirometry", "FEV1/FVC < 0.70 post-bronchodilator"),
    ("Asthma spirometry", "Reversible obstruction: FEV1 ↑ ≥12% post-bronchodilator"),
    ("Pneumothorax sign", "Absent breath sounds, hyperresonance, tracheal deviation"),
    ("Pulmonary embolism", "Sudden dyspnea, pleuritic chest pain, elevated D-dimer"),
    ("CKD definition", "GFR < 60 mL/min/1.73m² for ≥ 3 months"),
    ("Nephrotic syndrome", "Proteinuria > 3.5 g/day, hypoalbuminemia, edema, hyperlipidemia"),
    ("Nephritic syndrome", "Hematuria, RBC casts, hypertension, mild proteinuria"),
    ("SLE criteria (one)", "Malar rash, oral ulcers, arthritis, ANA+, anti-dsDNA"),
    ("Rheumatoid arthritis", "Symmetric small-joint arthritis; anti-CCP, RF"),
    ("Osteoarthritis", "Asymmetric weight-bearing joint pain; worse with activity"),
    ("Multiple sclerosis", "Demyelinating CNS lesions disseminated in space + time"),
    ("Parkinson's disease", "Resting tremor, rigidity, bradykinesia, postural instability"),
    ("Alzheimer's disease", "Cortical atrophy + β-amyloid plaques + tau tangles"),
    ("Stroke (ischemic)", "Focal deficit > 24h; thrombotic/embolic occlusion"),
    ("TIA", "Focal deficit < 24h, no infarct on imaging"),
    ("Meningitis (bacterial)", "Fever, headache, neck stiffness, photophobia; ↑CSF neutrophils"),
    ("Sepsis (Sepsis-3)", "Life-threatening organ dysfunction from dysregulated host response"),
]

PHARMACOLOGY = [
    ("Metformin", "Biguanide; ↓ hepatic gluconeogenesis (first-line T2DM)"),
    ("Lisinopril", "ACE inhibitor; ↓ angiotensin II"),
    ("Losartan", "ARB; blocks AT1 receptor"),
    ("Amlodipine", "Dihydropyridine CCB; arterial vasodilation"),
    ("Atorvastatin", "HMG-CoA reductase inhibitor (statin)"),
    ("Warfarin", "Vitamin K epoxide reductase inhibitor"),
    ("Heparin (unfractionated)", "Activates antithrombin III → inactivates IIa, Xa"),
    ("Aspirin", "Irreversible COX-1/2 inhibitor"),
    ("Acetaminophen", "Analgesic/antipyretic; weak COX inhibition"),
    ("Ibuprofen", "Reversible non-selective COX inhibitor"),
    ("Omeprazole", "Proton pump inhibitor (PPI)"),
    ("Ranitidine", "H2 receptor antagonist"),
    ("Albuterol", "Short-acting β2-agonist (SABA)"),
    ("Prednisone", "Systemic glucocorticoid"),
    ("Levothyroxine", "Synthetic T4"),
    ("Sertraline", "SSRI"),
    ("Fluoxetine", "SSRI (long half-life)"),
    ("Amoxicillin", "β-lactam aminopenicillin"),
    ("Ceftriaxone", "3rd-generation cephalosporin"),
    ("Azithromycin", "Macrolide; blocks 50S ribosomal subunit"),
    ("Ciprofloxacin", "Fluoroquinolone; inhibits DNA gyrase"),
    ("Vancomycin", "Glycopeptide; binds D-Ala-D-Ala"),
    ("Furosemide", "Loop diuretic; blocks Na-K-2Cl in TAL"),
    ("Hydrochlorothiazide", "Thiazide; blocks Na-Cl in DCT"),
    ("Spironolactone", "Aldosterone antagonist; K+-sparing"),
    ("Digoxin", "Na/K-ATPase inhibitor; positive inotrope"),
    ("Metoprolol", "Cardioselective β1-blocker"),
    ("Insulin (rapid)", "Lispro, aspart, glulisine"),
    ("Insulin (long)", "Glargine, detemir"),
    ("Methotrexate", "DHFR inhibitor; folate antagonist"),
]

SPANISH_VOCAB = [
    ("hola", "hello"),
    ("adiós", "goodbye"),
    ("gracias", "thank you"),
    ("por favor", "please"),
    ("de nada", "you're welcome"),
    ("sí", "yes"),
    ("no", "no"),
    ("buenos días", "good morning"),
    ("buenas noches", "good night"),
    ("amigo", "friend (m)"),
    ("amiga", "friend (f)"),
    ("casa", "house"),
    ("perro", "dog"),
    ("gato", "cat"),
    ("agua", "water"),
    ("comida", "food"),
    ("hombre", "man"),
    ("mujer", "woman"),
    ("niño", "child / boy"),
    ("niña", "girl"),
    ("libro", "book"),
    ("escuela", "school"),
    ("trabajo", "work / job"),
    ("ciudad", "city"),
    ("país", "country"),
    ("tiempo", "time / weather"),
    ("día", "day"),
    ("noche", "night"),
    ("año", "year"),
    ("hora", "hour"),
    ("hoy", "today"),
    ("mañana", "tomorrow / morning"),
    ("ayer", "yesterday"),
    ("ahora", "now"),
    ("siempre", "always"),
    ("nunca", "never"),
    ("hablar", "to speak"),
    ("comer", "to eat"),
    ("beber", "to drink"),
    ("dormir", "to sleep"),
    ("trabajar", "to work"),
    ("estudiar", "to study"),
    ("vivir", "to live"),
    ("ir", "to go"),
    ("venir", "to come"),
    ("hacer", "to do / make"),
    ("ser", "to be (essence)"),
    ("estar", "to be (state)"),
    ("tener", "to have"),
    ("querer", "to want / love"),
    ("rojo", "red"),
    ("azul", "blue"),
    ("verde", "green"),
    ("amarillo", "yellow"),
    ("blanco", "white"),
    ("negro", "black"),
    ("grande", "big"),
    ("pequeño", "small"),
    ("bueno", "good"),
    ("malo", "bad"),
    ("rápido", "fast"),
    ("lento", "slow"),
    ("nuevo", "new"),
    ("viejo", "old"),
    ("uno", "one"),
    ("dos", "two"),
    ("tres", "three"),
    ("cuatro", "four"),
    ("cinco", "five"),
    ("seis", "six"),
    ("siete", "seven"),
    ("ocho", "eight"),
    ("nueve", "nine"),
    ("diez", "ten"),
    ("once", "eleven"),
    ("doce", "twelve"),
    ("quince", "fifteen"),
    ("veinte", "twenty"),
    ("treinta", "thirty"),
    ("cien", "one hundred"),
    ("mil", "one thousand"),
    ("lunes", "Monday"),
    ("martes", "Tuesday"),
    ("miércoles", "Wednesday"),
    ("jueves", "Thursday"),
    ("viernes", "Friday"),
    ("sábado", "Saturday"),
    ("domingo", "Sunday"),
    ("enero", "January"),
    ("febrero", "February"),
    ("marzo", "March"),
    ("abril", "April"),
    ("mayo", "May"),
    ("junio", "June"),
    ("julio", "July"),
    ("agosto", "August"),
    ("septiembre", "September"),
    ("octubre", "October"),
    ("noviembre", "November"),
    ("diciembre", "December"),
    ("familia", "family"),
    ("padre", "father"),
    ("madre", "mother"),
    ("hijo", "son"),
    ("hija", "daughter"),
    ("hermano", "brother"),
    ("hermana", "sister"),
    ("abuelo", "grandfather"),
    ("abuela", "grandmother"),
    ("esposo", "husband"),
    ("esposa", "wife"),
    ("cabeza", "head"),
    ("ojo", "eye"),
    ("nariz", "nose"),
    ("boca", "mouth"),
    ("oreja", "ear"),
    ("brazo", "arm"),
    ("mano", "hand"),
    ("dedo", "finger"),
    ("pierna", "leg"),
    ("pie", "foot"),
    ("corazón", "heart"),
    ("pan", "bread"),
    ("leche", "milk"),
    ("queso", "cheese"),
    ("carne", "meat"),
    ("pescado", "fish"),
    ("pollo", "chicken"),
    ("arroz", "rice"),
    ("huevo", "egg"),
    ("manzana", "apple"),
    ("naranja", "orange"),
    ("plátano", "banana"),
    ("café", "coffee"),
    ("té", "tea"),
    ("vino", "wine"),
    ("cerveza", "beer"),
    ("calle", "street"),
    ("coche", "car"),
    ("autobús", "bus"),
    ("tren", "train"),
    ("avión", "airplane"),
    ("hospital", "hospital"),
    ("médico", "doctor"),
    ("profesor", "teacher"),
    ("estudiante", "student"),
    ("dinero", "money"),
    ("trabajo", "work"),
    ("sol", "sun"),
    ("luna", "moon"),
    ("cielo", "sky"),
    ("mar", "sea"),
    ("río", "river"),
    ("montaña", "mountain"),
    ("playa", "beach"),
    ("calor", "heat"),
    ("frío", "cold"),
    ("lluvia", "rain"),
    ("nieve", "snow"),
    ("viento", "wind"),
    ("número", "number"),
    ("nombre", "name"),
    ("pregunta", "question"),
    ("respuesta", "answer"),
    ("verdad", "truth"),
    ("mentira", "lie"),
    ("camino", "way / path"),
    ("vida", "life"),
    ("muerte", "death"),
    ("amor", "love"),
    ("paz", "peace"),
    ("guerra", "war"),
    ("feliz", "happy"),
    ("triste", "sad"),
    ("enojado", "angry"),
    ("cansado", "tired"),
    ("hambriento", "hungry"),
    ("sediento", "thirsty"),
    ("enfermo", "sick"),
    ("sano", "healthy"),
    ("rico", "rich"),
    ("pobre", "poor"),
    ("fácil", "easy"),
    ("difícil", "difficult"),
    ("fuerte", "strong"),
    ("débil", "weak"),
    ("alto", "tall"),
    ("bajo", "short"),
    ("largo", "long"),
    ("corto", "short (length)"),
    ("ancho", "wide"),
    ("estrecho", "narrow"),
    ("caliente", "hot"),
    ("frío (adj)", "cold"),
    ("cerrar", "to close"),
    ("abrir", "to open"),
    ("comprar", "to buy"),
    ("vender", "to sell"),
    ("pagar", "to pay"),
    ("dar", "to give"),
    ("recibir", "to receive"),
    ("buscar", "to look for"),
    ("encontrar", "to find"),
    ("perder", "to lose"),
    ("ganar", "to win / earn"),
    ("salir", "to leave / go out"),
    ("entrar", "to enter"),
    ("subir", "to go up / climb"),
    ("bajar", "to go down"),
    ("caminar", "to walk"),
    ("correr", "to run"),
    ("nadar", "to swim"),
    ("volar", "to fly"),
    ("conducir", "to drive"),
    ("escribir", "to write"),
    ("leer", "to read"),
    ("escuchar", "to listen"),
    ("ver", "to see / watch"),
    ("pensar", "to think"),
    ("creer", "to believe"),
    ("entender", "to understand"),
    ("aprender", "to learn"),
    ("enseñar", "to teach"),
    ("recordar", "to remember"),
    ("olvidar", "to forget"),
]

JAPANESE_N5 = [
    ("こんにちは", "hello (afternoon)"),
    ("おはよう", "good morning"),
    ("こんばんは", "good evening"),
    ("ありがとう", "thank you"),
    ("すみません", "excuse me / sorry"),
    ("はい", "yes"),
    ("いいえ", "no"),
    ("私 (わたし)", "I / me"),
    ("あなた", "you"),
    ("猫 (ねこ)", "cat"),
    ("犬 (いぬ)", "dog"),
    ("水 (みず)", "water"),
    ("食べ物 (たべもの)", "food"),
    ("学校 (がっこう)", "school"),
    ("先生 (せんせい)", "teacher"),
    ("学生 (がくせい)", "student"),
    ("本 (ほん)", "book"),
    ("家 (いえ)", "house / home"),
    ("車 (くるま)", "car"),
    ("電車 (でんしゃ)", "train"),
    ("今日 (きょう)", "today"),
    ("明日 (あした)", "tomorrow"),
    ("昨日 (きのう)", "yesterday"),
    ("時間 (じかん)", "time / hour"),
    ("食べる (たべる)", "to eat"),
    ("飲む (のむ)", "to drink"),
    ("行く (いく)", "to go"),
    ("来る (くる)", "to come"),
    ("見る (みる)", "to see / watch"),
    ("聞く (きく)", "to listen / ask"),
    ("話す (はなす)", "to speak"),
    ("読む (よむ)", "to read"),
    ("書く (かく)", "to write"),
    ("する", "to do"),
    ("一 (いち)", "one"),
    ("二 (に)", "two"),
    ("三 (さん)", "three"),
    ("四 (し / よん)", "four"),
    ("五 (ご)", "five"),
    ("十 (じゅう)", "ten"),
    ("百 (ひゃく)", "hundred"),
    ("千 (せん)", "thousand"),
    ("大きい (おおきい)", "big"),
    ("小さい (ちいさい)", "small"),
    ("赤い (あかい)", "red"),
    ("青い (あおい)", "blue"),
    ("白い (しろい)", "white"),
    ("黒い (くろい)", "black"),
    ("新しい (あたらしい)", "new"),
    ("古い (ふるい)", "old (not for people)"),
    ("月曜日 (げつようび)", "Monday"),
    ("火曜日 (かようび)", "Tuesday"),
    ("水曜日 (すいようび)", "Wednesday"),
    ("木曜日 (もくようび)", "Thursday"),
    ("金曜日 (きんようび)", "Friday"),
    ("土曜日 (どようび)", "Saturday"),
    ("日曜日 (にちようび)", "Sunday"),
    ("一月 (いちがつ)", "January"),
    ("七月 (しちがつ)", "July"),
    ("十二月 (じゅうにがつ)", "December"),
    ("朝 (あさ)", "morning"),
    ("夜 (よる)", "night"),
    ("今 (いま)", "now"),
    ("時 (とき)", "time / when"),
    ("年 (とし)", "year"),
    ("月 (つき)", "moon / month"),
    ("日 (ひ)", "sun / day"),
    ("週 (しゅう)", "week"),
    ("父 (ちち)", "father (one's own)"),
    ("母 (はは)", "mother (one's own)"),
    ("兄 (あに)", "older brother (own)"),
    ("姉 (あね)", "older sister (own)"),
    ("弟 (おとうと)", "younger brother"),
    ("妹 (いもうと)", "younger sister"),
    ("友達 (ともだち)", "friend"),
    ("子供 (こども)", "child"),
    ("男 (おとこ)", "man"),
    ("女 (おんな)", "woman"),
    ("人 (ひと)", "person"),
    ("名前 (なまえ)", "name"),
    ("国 (くに)", "country"),
    ("町 (まち)", "town"),
    ("駅 (えき)", "train station"),
    ("空港 (くうこう)", "airport"),
    ("病院 (びょういん)", "hospital"),
    ("銀行 (ぎんこう)", "bank"),
    ("郵便局 (ゆうびんきょく)", "post office"),
    ("店 (みせ)", "shop / store"),
    ("会社 (かいしゃ)", "company"),
    ("仕事 (しごと)", "job / work"),
    ("お金 (おかね)", "money"),
    ("ご飯 (ごはん)", "meal / cooked rice"),
    ("パン", "bread"),
    ("肉 (にく)", "meat"),
    ("魚 (さかな)", "fish"),
    ("野菜 (やさい)", "vegetable"),
    ("果物 (くだもの)", "fruit"),
    ("お茶 (おちゃ)", "tea"),
    ("コーヒー", "coffee"),
    ("ビール", "beer"),
    ("ワイン", "wine"),
    ("頭 (あたま)", "head"),
    ("目 (め)", "eye"),
    ("耳 (みみ)", "ear"),
    ("口 (くち)", "mouth"),
    ("鼻 (はな)", "nose"),
    ("手 (て)", "hand"),
    ("足 (あし)", "foot / leg"),
    ("心 (こころ)", "heart / mind"),
    ("熱い (あつい)", "hot (to touch)"),
    ("寒い (さむい)", "cold (weather)"),
    ("暖かい (あたたかい)", "warm"),
    ("涼しい (すずしい)", "cool"),
    ("高い (たかい)", "high / expensive"),
    ("安い (やすい)", "cheap"),
    ("速い (はやい)", "fast"),
    ("遅い (おそい)", "slow / late"),
    ("難しい (むずかしい)", "difficult"),
    ("簡単 (かんたん)", "easy"),
    ("面白い (おもしろい)", "interesting"),
    ("つまらない", "boring"),
    ("おいしい", "delicious"),
    ("まずい", "bad-tasting"),
    ("好き (すき)", "liked / favorite"),
    ("嫌い (きらい)", "disliked"),
    ("勉強する (べんきょうする)", "to study"),
    ("買う (かう)", "to buy"),
    ("売る (うる)", "to sell"),
    ("作る (つくる)", "to make"),
    ("使う (つかう)", "to use"),
    ("待つ (まつ)", "to wait"),
    ("立つ (たつ)", "to stand"),
    ("座る (すわる)", "to sit"),
    ("起きる (おきる)", "to wake up"),
    ("寝る (ねる)", "to sleep / go to bed"),
    ("走る (はしる)", "to run"),
    ("歩く (あるく)", "to walk"),
    ("泳ぐ (およぐ)", "to swim"),
    ("乗る (のる)", "to ride / get on"),
    ("降りる (おりる)", "to get off"),
    ("着く (つく)", "to arrive"),
    ("出る (でる)", "to leave / exit"),
    ("入る (はいる)", "to enter"),
    ("開ける (あける)", "to open"),
    ("閉める (しめる)", "to close"),
    ("付ける (つける)", "to turn on / attach"),
    ("消す (けす)", "to turn off / erase"),
    ("分かる (わかる)", "to understand"),
    ("忘れる (わすれる)", "to forget"),
    ("覚える (おぼえる)", "to remember / learn"),
    ("教える (おしえる)", "to teach / tell"),
]

GEOGRAPHY = [
    ("France", "Paris"),
    ("Germany", "Berlin"),
    ("Spain", "Madrid"),
    ("Italy", "Rome"),
    ("Portugal", "Lisbon"),
    ("United Kingdom", "London"),
    ("Ireland", "Dublin"),
    ("Netherlands", "Amsterdam"),
    ("Belgium", "Brussels"),
    ("Switzerland", "Bern"),
    ("Austria", "Vienna"),
    ("Sweden", "Stockholm"),
    ("Norway", "Oslo"),
    ("Denmark", "Copenhagen"),
    ("Finland", "Helsinki"),
    ("Iceland", "Reykjavík"),
    ("Poland", "Warsaw"),
    ("Czech Republic", "Prague"),
    ("Hungary", "Budapest"),
    ("Greece", "Athens"),
    ("Turkey", "Ankara"),
    ("Russia", "Moscow"),
    ("Ukraine", "Kyiv"),
    ("Japan", "Tokyo"),
    ("China", "Beijing"),
    ("South Korea", "Seoul"),
    ("North Korea", "Pyongyang"),
    ("India", "New Delhi"),
    ("Pakistan", "Islamabad"),
    ("Bangladesh", "Dhaka"),
    ("Thailand", "Bangkok"),
    ("Vietnam", "Hanoi"),
    ("Indonesia", "Jakarta"),
    ("Philippines", "Manila"),
    ("Malaysia", "Kuala Lumpur"),
    ("Australia", "Canberra"),
    ("New Zealand", "Wellington"),
    ("Egypt", "Cairo"),
    ("South Africa", "Pretoria (admin)"),
    ("Nigeria", "Abuja"),
    ("Kenya", "Nairobi"),
    ("Morocco", "Rabat"),
    ("Ethiopia", "Addis Ababa"),
    ("Brazil", "Brasília"),
    ("Argentina", "Buenos Aires"),
    ("Chile", "Santiago"),
    ("Peru", "Lima"),
    ("Colombia", "Bogotá"),
    ("Mexico", "Mexico City"),
    ("Canada", "Ottawa"),
    ("United States", "Washington, D.C."),
    ("Cuba", "Havana"),
    ("Saudi Arabia", "Riyadh"),
    ("Israel", "Jerusalem"),
    ("UAE", "Abu Dhabi"),
    ("Iran", "Tehran"),
    ("Iraq", "Baghdad"),
]

PERIODIC_TABLE = [
    ("H", "Hydrogen (Z=1)"),
    ("He", "Helium (Z=2)"),
    ("Li", "Lithium (Z=3)"),
    ("Be", "Beryllium (Z=4)"),
    ("B", "Boron (Z=5)"),
    ("C", "Carbon (Z=6)"),
    ("N", "Nitrogen (Z=7)"),
    ("O", "Oxygen (Z=8)"),
    ("F", "Fluorine (Z=9)"),
    ("Ne", "Neon (Z=10)"),
    ("Na", "Sodium (Z=11)"),
    ("Mg", "Magnesium (Z=12)"),
    ("Al", "Aluminium (Z=13)"),
    ("Si", "Silicon (Z=14)"),
    ("P", "Phosphorus (Z=15)"),
    ("S", "Sulfur (Z=16)"),
    ("Cl", "Chlorine (Z=17)"),
    ("Ar", "Argon (Z=18)"),
    ("K", "Potassium (Z=19)"),
    ("Ca", "Calcium (Z=20)"),
    ("Sc", "Scandium (Z=21)"),
    ("Ti", "Titanium (Z=22)"),
    ("V", "Vanadium (Z=23)"),
    ("Cr", "Chromium (Z=24)"),
    ("Mn", "Manganese (Z=25)"),
    ("Fe", "Iron (Z=26)"),
    ("Co", "Cobalt (Z=27)"),
    ("Ni", "Nickel (Z=28)"),
    ("Cu", "Copper (Z=29)"),
    ("Zn", "Zinc (Z=30)"),
    ("Ga", "Gallium (Z=31)"),
    ("Ge", "Germanium (Z=32)"),
    ("As", "Arsenic (Z=33)"),
    ("Se", "Selenium (Z=34)"),
    ("Br", "Bromine (Z=35)"),
    ("Kr", "Krypton (Z=36)"),
    ("Rb", "Rubidium (Z=37)"),
    ("Sr", "Strontium (Z=38)"),
    ("Y", "Yttrium (Z=39)"),
    ("Zr", "Zirconium (Z=40)"),
    ("Nb", "Niobium (Z=41)"),
    ("Mo", "Molybdenum (Z=42)"),
    ("Tc", "Technetium (Z=43)"),
    ("Ru", "Ruthenium (Z=44)"),
    ("Rh", "Rhodium (Z=45)"),
    ("Pd", "Palladium (Z=46)"),
    ("Ag", "Silver (Z=47)"),
    ("Cd", "Cadmium (Z=48)"),
    ("In", "Indium (Z=49)"),
    ("Sn", "Tin (Z=50)"),
    ("Sb", "Antimony (Z=51)"),
    ("Te", "Tellurium (Z=52)"),
    ("I", "Iodine (Z=53)"),
    ("Xe", "Xenon (Z=54)"),
    ("Cs", "Cesium (Z=55)"),
    ("Ba", "Barium (Z=56)"),
    ("La", "Lanthanum (Z=57)"),
    ("Ce", "Cerium (Z=58)"),
    ("Pr", "Praseodymium (Z=59)"),
    ("Nd", "Neodymium (Z=60)"),
    ("Pm", "Promethium (Z=61)"),
    ("Sm", "Samarium (Z=62)"),
    ("Eu", "Europium (Z=63)"),
    ("Gd", "Gadolinium (Z=64)"),
    ("Tb", "Terbium (Z=65)"),
    ("Dy", "Dysprosium (Z=66)"),
    ("Ho", "Holmium (Z=67)"),
    ("Er", "Erbium (Z=68)"),
    ("Tm", "Thulium (Z=69)"),
    ("Yb", "Ytterbium (Z=70)"),
    ("Lu", "Lutetium (Z=71)"),
    ("Hf", "Hafnium (Z=72)"),
    ("Ta", "Tantalum (Z=73)"),
    ("W", "Tungsten (Z=74)"),
    ("Re", "Rhenium (Z=75)"),
    ("Os", "Osmium (Z=76)"),
    ("Ir", "Iridium (Z=77)"),
    ("Pt", "Platinum (Z=78)"),
    ("Au", "Gold (Z=79)"),
    ("Hg", "Mercury (Z=80)"),
    ("Tl", "Thallium (Z=81)"),
    ("Pb", "Lead (Z=82)"),
    ("Bi", "Bismuth (Z=83)"),
    ("Po", "Polonium (Z=84)"),
    ("At", "Astatine (Z=85)"),
    ("Rn", "Radon (Z=86)"),
    ("Fr", "Francium (Z=87)"),
    ("Ra", "Radium (Z=88)"),
    ("Ac", "Actinium (Z=89)"),
    ("Th", "Thorium (Z=90)"),
    ("Pa", "Protactinium (Z=91)"),
    ("U", "Uranium (Z=92)"),
    ("Np", "Neptunium (Z=93)"),
    ("Pu", "Plutonium (Z=94)"),
    ("Am", "Americium (Z=95)"),
    ("Cm", "Curium (Z=96)"),
    ("Bk", "Berkelium (Z=97)"),
    ("Cf", "Californium (Z=98)"),
    ("Es", "Einsteinium (Z=99)"),
    ("Fm", "Fermium (Z=100)"),
    ("Md", "Mendelevium (Z=101)"),
    ("No", "Nobelium (Z=102)"),
    ("Lr", "Lawrencium (Z=103)"),
    ("Rf", "Rutherfordium (Z=104)"),
    ("Db", "Dubnium (Z=105)"),
    ("Sg", "Seaborgium (Z=106)"),
    ("Bh", "Bohrium (Z=107)"),
    ("Hs", "Hassium (Z=108)"),
    ("Mt", "Meitnerium (Z=109)"),
    ("Ds", "Darmstadtium (Z=110)"),
    ("Rg", "Roentgenium (Z=111)"),
    ("Cn", "Copernicium (Z=112)"),
    ("Nh", "Nihonium (Z=113)"),
    ("Fl", "Flerovium (Z=114)"),
    ("Mc", "Moscovium (Z=115)"),
    ("Lv", "Livermorium (Z=116)"),
    ("Ts", "Tennessine (Z=117)"),
    ("Og", "Oganesson (Z=118)"),
]

US_STATE_CAPITALS = [
    ("Alabama", "Montgomery"),
    ("Alaska", "Juneau"),
    ("Arizona", "Phoenix"),
    ("Arkansas", "Little Rock"),
    ("California", "Sacramento"),
    ("Colorado", "Denver"),
    ("Connecticut", "Hartford"),
    ("Delaware", "Dover"),
    ("Florida", "Tallahassee"),
    ("Georgia", "Atlanta"),
    ("Hawaii", "Honolulu"),
    ("Idaho", "Boise"),
    ("Illinois", "Springfield"),
    ("Indiana", "Indianapolis"),
    ("Iowa", "Des Moines"),
    ("Kansas", "Topeka"),
    ("Kentucky", "Frankfort"),
    ("Louisiana", "Baton Rouge"),
    ("Maine", "Augusta"),
    ("Maryland", "Annapolis"),
    ("Massachusetts", "Boston"),
    ("Michigan", "Lansing"),
    ("Minnesota", "Saint Paul"),
    ("Mississippi", "Jackson"),
    ("Missouri", "Jefferson City"),
    ("Montana", "Helena"),
    ("Nebraska", "Lincoln"),
    ("Nevada", "Carson City"),
    ("New Hampshire", "Concord"),
    ("New Jersey", "Trenton"),
    ("New Mexico", "Santa Fe"),
    ("New York", "Albany"),
    ("North Carolina", "Raleigh"),
    ("North Dakota", "Bismarck"),
    ("Ohio", "Columbus"),
    ("Oklahoma", "Oklahoma City"),
    ("Oregon", "Salem"),
    ("Pennsylvania", "Harrisburg"),
    ("Rhode Island", "Providence"),
    ("South Carolina", "Columbia"),
    ("South Dakota", "Pierre"),
    ("Tennessee", "Nashville"),
    ("Texas", "Austin"),
    ("Utah", "Salt Lake City"),
    ("Vermont", "Montpelier"),
    ("Virginia", "Richmond"),
    ("Washington", "Olympia"),
    ("West Virginia", "Charleston"),
    ("Wisconsin", "Madison"),
    ("Wyoming", "Cheyenne"),
]

GREEK_ALPHABET = [
    ("α / Α", "Alpha"),
    ("β / Β", "Beta"),
    ("γ / Γ", "Gamma"),
    ("δ / Δ", "Delta"),
    ("ε / Ε", "Epsilon"),
    ("ζ / Ζ", "Zeta"),
    ("η / Η", "Eta"),
    ("θ / Θ", "Theta"),
    ("ι / Ι", "Iota"),
    ("κ / Κ", "Kappa"),
    ("λ / Λ", "Lambda"),
    ("μ / Μ", "Mu"),
    ("ν / Ν", "Nu"),
    ("ξ / Ξ", "Xi"),
    ("ο / Ο", "Omicron"),
    ("π / Π", "Pi"),
    ("ρ / Ρ", "Rho"),
    ("σ / Σ", "Sigma"),
    ("τ / Τ", "Tau"),
    ("υ / Υ", "Upsilon"),
    ("φ / Φ", "Phi"),
    ("χ / Χ", "Chi"),
    ("ψ / Ψ", "Psi"),
    ("ω / Ω", "Omega"),
]

AMINO_ACIDS = [
    ("Alanine", "A — Ala — nonpolar"),
    ("Arginine", "R — Arg — positively charged"),
    ("Asparagine", "N — Asn — polar"),
    ("Aspartate", "D — Asp — negatively charged"),
    ("Cysteine", "C — Cys — polar (disulfide)"),
    ("Glutamate", "E — Glu — negatively charged"),
    ("Glutamine", "Q — Gln — polar"),
    ("Glycine", "G — Gly — nonpolar (smallest)"),
    ("Histidine", "H — His — positively charged"),
    ("Isoleucine", "I — Ile — nonpolar"),
    ("Leucine", "L — Leu — nonpolar"),
    ("Lysine", "K — Lys — positively charged"),
    ("Methionine", "M — Met — nonpolar (start codon)"),
    ("Phenylalanine", "F — Phe — aromatic"),
    ("Proline", "P — Pro — nonpolar (rigid)"),
    ("Serine", "S — Ser — polar"),
    ("Threonine", "T — Thr — polar"),
    ("Tryptophan", "W — Trp — aromatic"),
    ("Tyrosine", "Y — Tyr — aromatic / polar"),
    ("Valine", "V — Val — nonpolar"),
]

BONES = [
    ("Cranium", "Skull (frontal, parietal, temporal, occipital)"),
    ("Mandible", "Lower jaw"),
    ("Maxilla", "Upper jaw"),
    ("Clavicle", "Collar bone"),
    ("Scapula", "Shoulder blade"),
    ("Humerus", "Upper arm bone"),
    ("Radius", "Forearm, lateral / thumb side"),
    ("Ulna", "Forearm, medial / pinky side"),
    ("Carpals", "Wrist bones (8)"),
    ("Metacarpals", "Hand bones (5)"),
    ("Phalanges (hand)", "Finger bones (14)"),
    ("Sternum", "Breast bone"),
    ("Ribs", "12 pairs"),
    ("Vertebrae (cervical)", "C1–C7"),
    ("Vertebrae (thoracic)", "T1–T12"),
    ("Vertebrae (lumbar)", "L1–L5"),
    ("Sacrum", "Fused S1–S5"),
    ("Coccyx", "Tailbone"),
    ("Pelvis (ilium)", "Upper, flared portion of hip bone"),
    ("Pelvis (ischium)", "Lower posterior portion of hip bone"),
    ("Pelvis (pubis)", "Anterior portion of hip bone"),
    ("Femur", "Thigh bone (longest)"),
    ("Patella", "Knee cap"),
    ("Tibia", "Shin bone"),
    ("Fibula", "Lateral lower leg bone"),
    ("Tarsals", "Ankle bones (7)"),
    ("Metatarsals", "Foot bones (5)"),
    ("Phalanges (foot)", "Toe bones (14)"),
    ("Calcaneus", "Heel bone"),
    ("Talus", "Ankle bone (articulates with tibia)"),
    ("Hyoid", "U-shaped neck bone, no articulation"),
    ("Malleus", "Hammer (middle ear)"),
    ("Incus", "Anvil (middle ear)"),
    ("Stapes", "Stirrup (smallest bone in body)"),
]

MUSCLES = [
    ("Biceps brachii", "Forearm flexion + supination (long & short heads)"),
    ("Triceps brachii", "Forearm extension (long, lateral, medial heads)"),
    ("Deltoid", "Shoulder abduction (anterior/lateral/posterior fibers)"),
    ("Pectoralis major", "Shoulder flexion + adduction + medial rotation"),
    ("Pectoralis minor", "Scapular protraction + depression"),
    ("Latissimus dorsi", "Shoulder extension + adduction + medial rotation"),
    ("Trapezius", "Scapular elevation + retraction + rotation"),
    ("Rhomboid major / minor", "Scapular retraction"),
    ("Serratus anterior", "Scapular protraction (winging if injured)"),
    ("Rotator cuff (SITS)", "Supraspinatus, Infraspinatus, Teres minor, Subscapularis"),
    ("Brachialis", "Pure forearm flexion (primary)"),
    ("Brachioradialis", "Forearm flexion in mid-pronation"),
    ("Flexor carpi radialis", "Wrist flexion + radial deviation"),
    ("Extensor carpi ulnaris", "Wrist extension + ulnar deviation"),
    ("Rectus abdominis", "Trunk flexion (the 'six-pack' muscle)"),
    ("External oblique", "Trunk flexion + contralateral rotation"),
    ("Internal oblique", "Trunk flexion + ipsilateral rotation"),
    ("Transversus abdominis", "Compresses abdominal contents"),
    ("Erector spinae", "Spinal extension (iliocostalis, longissimus, spinalis)"),
    ("Diaphragm", "Primary muscle of inspiration (C3-C5: phrenic n.)"),
    ("Quadriceps femoris", "Knee extension (rectus femoris + 3 vastus muscles)"),
    ("Hamstrings", "Knee flexion + hip extension (semi-T, semi-M, biceps femoris)"),
    ("Gluteus maximus", "Hip extension (largest muscle in the body)"),
    ("Gluteus medius / minimus", "Hip abduction (Trendelenburg if weak)"),
    ("Iliopsoas", "Hip flexion (iliacus + psoas major)"),
    ("Sartorius", "Hip flexion + abduction + external rotation (longest)"),
    ("Adductor longus / brevis / magnus", "Hip adduction"),
    ("Gracilis", "Hip adduction + knee flexion"),
    ("Gastrocnemius", "Plantar flexion (two-headed, crosses knee)"),
    ("Soleus", "Plantar flexion (deep to gastrocnemius)"),
    ("Tibialis anterior", "Ankle dorsiflexion + inversion"),
    ("Peroneus longus / brevis", "Ankle eversion"),
    ("Sternocleidomastoid", "Head ipsilateral tilt + contralateral rotation"),
    ("Masseter", "Mandibular elevation (jaw closing) — strongest by weight"),
    ("Temporalis", "Mandibular elevation + retraction"),
    ("Orbicularis oculi", "Eyelid closure"),
    ("Orbicularis oris", "Lip closure / pursing"),
    ("Zygomaticus major", "Elevates angle of mouth (smiling)"),
]

MICROBIOLOGY = [
    ("Staphylococcus aureus", "Gram+ cocci, clusters; coagulase+; many infections"),
    ("Streptococcus pyogenes", "Group A strep; β-hemolytic; pharyngitis, rheumatic fever"),
    ("Streptococcus pneumoniae", "α-hemolytic, optochin-sensitive; pneumonia, meningitis"),
    ("Enterococcus faecalis", "Gram+ cocci; UTI, endocarditis; bile-resistant"),
    ("Bacillus anthracis", "Gram+ rod; anthrax; bioterror agent"),
    ("Clostridium difficile", "Anaerobic Gram+ rod; pseudomembranous colitis"),
    ("Clostridium tetani", "Tetanus toxin; muscle spasm via GABA blockade"),
    ("Clostridium botulinum", "Botulinum toxin; flaccid paralysis (ACh blockade)"),
    ("Listeria monocytogenes", "Gram+ rod; meningitis in neonates/elderly"),
    ("Mycobacterium tuberculosis", "Acid-fast bacillus; granulomatous lung disease"),
    ("Mycobacterium leprae", "Acid-fast; leprosy (Hansen disease)"),
    ("Neisseria meningitidis", "Gram- diplococci; meningitis + petechial rash"),
    ("Neisseria gonorrhoeae", "Gram- diplococci; gonorrhea; doesn't ferment maltose"),
    ("Escherichia coli", "Gram- rod; UTI, gastroenteritis (ETEC, EHEC, etc.)"),
    ("Klebsiella pneumoniae", "Gram- rod; 'currant jelly' sputum pneumonia"),
    ("Pseudomonas aeruginosa", "Gram- rod; CF lung, burn wounds; green pigment"),
    ("Helicobacter pylori", "Curved Gram- rod; gastric ulcers, urease+"),
    ("Salmonella typhi", "Gram- rod; typhoid fever; rose spots"),
    ("Shigella dysenteriae", "Gram- rod; bloody dysentery; very low ID50"),
    ("Vibrio cholerae", "Curved Gram- rod; rice-water diarrhea"),
    ("Treponema pallidum", "Spirochete; syphilis; dark-field microscopy"),
    ("Borrelia burgdorferi", "Spirochete; Lyme disease; tick-borne"),
    ("Chlamydia trachomatis", "Obligate intracellular; STI, trachoma"),
    ("Rickettsia rickettsii", "Obligate intracellular; Rocky Mountain spotted fever"),
    ("Influenza A virus", "Orthomyxovirus; segmented (-)ssRNA; H+N antigens"),
    ("HIV", "Retrovirus; reverse transcriptase; CD4 T-cell destruction"),
    ("Hepatitis B virus", "DNA virus; serum hepatitis; carrier state"),
    ("Hepatitis C virus", "Flavivirus; chronic hepatitis → cirrhosis"),
    ("EBV", "Mononucleosis; Burkitt lymphoma; nasopharyngeal Ca"),
    ("HSV-1 / HSV-2", "Herpes simplex; cold sores / genital herpes"),
    ("Varicella-zoster virus", "Chickenpox / shingles; reactivates in DRG"),
    ("Rabies virus", "(-)ssRNA bullet-shaped; Negri bodies; encephalitis"),
    ("Candida albicans", "Yeast; thrush, vaginitis; pseudohyphae"),
    ("Aspergillus fumigatus", "Mold; ABPA, aspergilloma; 45° branching"),
    ("Cryptococcus neoformans", "Encapsulated yeast; meningitis in HIV; India ink"),
    ("Pneumocystis jirovecii", "Atypical pneumonia in AIDS; silver stain"),
    ("Plasmodium falciparum", "Malaria; most lethal species; RBC ring forms"),
    ("Toxoplasma gondii", "Cat feces; congenital triad: hydrocephalus, calcifications, chorioretinitis"),
]

FRENCH_VOCAB = [
    ("bonjour", "hello / good day"),
    ("bonsoir", "good evening"),
    ("au revoir", "goodbye"),
    ("merci", "thank you"),
    ("s'il vous plaît", "please"),
    ("oui", "yes"),
    ("non", "no"),
    ("excusez-moi", "excuse me"),
    ("pardon", "pardon / sorry"),
    ("je", "I"),
    ("tu", "you (informal)"),
    ("vous", "you (formal / plural)"),
    ("il", "he / it"),
    ("elle", "she / it"),
    ("nous", "we"),
    ("ils / elles", "they"),
    ("homme", "man"),
    ("femme", "woman"),
    ("enfant", "child"),
    ("ami / amie", "friend (m / f)"),
    ("maison", "house"),
    ("école", "school"),
    ("travail", "work"),
    ("ville", "city"),
    ("pays", "country"),
    ("chien", "dog"),
    ("chat", "cat"),
    ("eau", "water"),
    ("pain", "bread"),
    ("vin", "wine"),
    ("café", "coffee"),
    ("thé", "tea"),
    ("livre", "book"),
    ("temps", "time / weather"),
    ("jour", "day"),
    ("nuit", "night"),
    ("matin", "morning"),
    ("soir", "evening"),
    ("aujourd'hui", "today"),
    ("demain", "tomorrow"),
    ("hier", "yesterday"),
    ("maintenant", "now"),
    ("toujours", "always"),
    ("jamais", "never"),
    ("être", "to be"),
    ("avoir", "to have"),
    ("aller", "to go"),
    ("venir", "to come"),
    ("faire", "to do / make"),
    ("dire", "to say"),
    ("voir", "to see"),
    ("savoir", "to know (a fact)"),
    ("connaître", "to know (a person)"),
    ("pouvoir", "to be able to"),
    ("vouloir", "to want"),
    ("devoir", "must / to have to"),
    ("parler", "to speak"),
    ("manger", "to eat"),
    ("boire", "to drink"),
    ("dormir", "to sleep"),
    ("vivre", "to live"),
    ("travailler", "to work"),
    ("étudier", "to study"),
    ("aimer", "to like / love"),
    ("rouge", "red"),
    ("bleu", "blue"),
    ("vert", "green"),
    ("jaune", "yellow"),
    ("blanc", "white"),
    ("noir", "black"),
    ("grand", "big / tall"),
    ("petit", "small"),
    ("bon", "good"),
    ("mauvais", "bad"),
    ("beau / belle", "beautiful (m / f)"),
    ("nouveau / nouvelle", "new (m / f)"),
    ("vieux / vieille", "old (m / f)"),
    ("un", "one"),
    ("deux", "two"),
    ("trois", "three"),
    ("quatre", "four"),
    ("cinq", "five"),
    ("six", "six"),
    ("sept", "seven"),
    ("huit", "eight"),
    ("neuf", "nine"),
    ("dix", "ten"),
]

GERMAN_VOCAB = [
    ("hallo", "hello"),
    ("guten Morgen", "good morning"),
    ("guten Tag", "good day"),
    ("guten Abend", "good evening"),
    ("auf Wiedersehen", "goodbye"),
    ("tschüss", "bye"),
    ("danke", "thank you"),
    ("bitte", "please / you're welcome"),
    ("ja", "yes"),
    ("nein", "no"),
    ("Entschuldigung", "excuse me / sorry"),
    ("ich", "I"),
    ("du", "you (informal)"),
    ("Sie", "you (formal)"),
    ("er", "he"),
    ("sie", "she / they"),
    ("wir", "we"),
    ("ihr", "you (plural informal)"),
    ("Mann", "man"),
    ("Frau", "woman"),
    ("Kind", "child"),
    ("Freund / Freundin", "friend (m / f)"),
    ("Haus", "house"),
    ("Schule", "school"),
    ("Arbeit", "work"),
    ("Stadt", "city"),
    ("Land", "country"),
    ("Hund", "dog"),
    ("Katze", "cat"),
    ("Wasser", "water"),
    ("Brot", "bread"),
    ("Bier", "beer"),
    ("Kaffee", "coffee"),
    ("Buch", "book"),
    ("Zeit", "time"),
    ("Tag", "day"),
    ("Nacht", "night"),
    ("Morgen", "morning / tomorrow"),
    ("Abend", "evening"),
    ("heute", "today"),
    ("morgen", "tomorrow"),
    ("gestern", "yesterday"),
    ("jetzt", "now"),
    ("immer", "always"),
    ("nie", "never"),
    ("sein", "to be"),
    ("haben", "to have"),
    ("gehen", "to go"),
    ("kommen", "to come"),
    ("machen", "to do / make"),
    ("sagen", "to say"),
    ("sehen", "to see"),
    ("wissen", "to know (fact)"),
    ("kennen", "to know (person)"),
    ("können", "can / be able to"),
    ("wollen", "to want"),
    ("müssen", "must / have to"),
    ("sprechen", "to speak"),
    ("essen", "to eat"),
    ("trinken", "to drink"),
    ("schlafen", "to sleep"),
    ("leben", "to live"),
    ("arbeiten", "to work"),
    ("studieren", "to study"),
    ("lieben", "to love"),
    ("rot", "red"),
    ("blau", "blue"),
    ("grün", "green"),
    ("gelb", "yellow"),
    ("weiß", "white"),
    ("schwarz", "black"),
    ("groß", "big / tall"),
    ("klein", "small"),
    ("gut", "good"),
    ("schlecht", "bad"),
    ("neu", "new"),
    ("alt", "old"),
    ("eins", "one"),
    ("zwei", "two"),
    ("drei", "three"),
    ("vier", "four"),
    ("fünf", "five"),
    ("sechs", "six"),
    ("sieben", "seven"),
    ("acht", "eight"),
    ("neun", "nine"),
    ("zehn", "ten"),
]

HISTORY_DATES = [
    ("Fall of the Western Roman Empire", "476 AD"),
    ("Magna Carta signed", "1215"),
    ("Black Death peak in Europe", "1347–1351"),
    ("Gutenberg printing press", "1440"),
    ("Columbus reaches the Americas", "1492"),
    ("95 Theses (Luther)", "1517"),
    ("Spanish Armada defeated", "1588"),
    ("Mayflower lands at Plymouth", "1620"),
    ("English Civil War", "1642–1651"),
    ("Newton publishes Principia", "1687"),
    ("Battle of Plassey (start of British Raj)", "1757"),
    ("US Declaration of Independence", "1776"),
    ("French Revolution begins", "1789"),
    ("Louisiana Purchase", "1803"),
    ("Battle of Waterloo", "1815"),
    ("US Civil War", "1861–1865"),
    ("Meiji Restoration (Japan)", "1868"),
    ("Unification of Germany", "1871"),
    ("First powered flight (Wright brothers)", "1903"),
    ("World War I", "1914–1918"),
    ("Russian Revolution", "1917"),
    ("Treaty of Versailles", "1919"),
    ("Stock market crash → Great Depression", "1929"),
    ("World War II", "1939–1945"),
    ("Pearl Harbor", "Dec 7, 1941"),
    ("D-Day (Normandy)", "June 6, 1944"),
    ("Atomic bombs on Hiroshima & Nagasaki", "Aug 1945"),
    ("UN founded", "1945"),
    ("Indian independence", "1947"),
    ("Founding of People's Republic of China", "1949"),
    ("Korean War", "1950–1953"),
    ("Sputnik launched", "1957"),
    ("Cuban Missile Crisis", "1962"),
    ("MLK 'I have a dream'", "Aug 28, 1963"),
    ("JFK assassination", "Nov 22, 1963"),
    ("Apollo 11 — Moon landing", "July 20, 1969"),
    ("Watergate scandal breaks", "1972"),
    ("Fall of Saigon (end of Vietnam War)", "April 30, 1975"),
    ("Fall of the Berlin Wall", "Nov 9, 1989"),
    ("Dissolution of the USSR", "Dec 26, 1991"),
    ("World Wide Web public", "1991"),
    ("Apartheid ends in South Africa", "1994"),
    ("Euro currency launched", "1999"),
    ("9/11 attacks", "Sept 11, 2001"),
    ("Global financial crisis", "2008"),
    ("First iPhone released", "June 29, 2007"),
    ("COVID-19 pandemic declared", "March 11, 2020"),
]

CHEMISTRY = [
    ("Avogadro's number", "6.022 × 10²³ / mol"),
    ("Speed of light in vacuum", "c ≈ 2.998 × 10⁸ m/s"),
    ("Gas constant R", "8.314 J/(mol·K)"),
    ("Boltzmann constant k", "1.381 × 10⁻²³ J/K"),
    ("Planck constant h", "6.626 × 10⁻³⁴ J·s"),
    ("Ideal gas law", "PV = nRT"),
    ("Combined gas law", "P₁V₁/T₁ = P₂V₂/T₂"),
    ("Boyle's law", "PV = constant (isothermal)"),
    ("Charles's law", "V/T = constant (isobaric)"),
    ("pH definition", "−log₁₀ [H⁺]"),
    ("Water Kw at 25 °C", "1.0 × 10⁻¹⁴"),
    ("Standard temperature & pressure (STP)", "0 °C (273.15 K) and 1 atm"),
    ("Molar volume of gas at STP", "22.4 L/mol"),
    ("Density formula", "ρ = m / V"),
    ("Molarity", "M = mol solute / L solution"),
    ("Strong acid", "Fully dissociates (HCl, HBr, HI, HNO₃, H₂SO₄, HClO₄)"),
    ("Strong base", "Fully dissociates (NaOH, KOH, Ca(OH)₂…)"),
    ("Buffer (Henderson-Hasselbalch)", "pH = pKa + log([A⁻]/[HA])"),
    ("Oxidation", "Loss of electrons (LEO)"),
    ("Reduction", "Gain of electrons (GER)"),
    ("Electronegativity (most)", "Fluorine (3.98 Pauling)"),
    ("Diatomic elements", "H₂, N₂, O₂, F₂, Cl₂, Br₂, I₂"),
    ("Noble gases", "He, Ne, Ar, Kr, Xe, Rn — group 18, very stable"),
    ("Alkali metals", "Group 1 — Li, Na, K, Rb, Cs, Fr — very reactive"),
    ("Halogens", "Group 17 — F, Cl, Br, I, At — diatomic, reactive"),
    ("Catalyst", "Lowers activation energy; not consumed"),
    ("Exothermic", "Releases heat (ΔH < 0)"),
    ("Endothermic", "Absorbs heat (ΔH > 0)"),
    ("Equilibrium constant Kc", "Products / reactants at equilibrium (raised to coefficients)"),
    ("Le Chatelier's principle", "System shifts to counteract applied stress"),
]

CS_TERMS = [
    ("Binary search complexity", "O(log n) — sorted array, halve each step"),
    ("Linear search complexity", "O(n) — scan each element"),
    ("Bubble sort (worst)", "O(n²)"),
    ("Merge sort (worst)", "O(n log n) — stable, divide & conquer"),
    ("Quick sort (avg / worst)", "O(n log n) avg / O(n²) worst"),
    ("Heap sort", "O(n log n) — in-place, not stable"),
    ("Insertion sort (best)", "O(n) on nearly-sorted input"),
    ("Hash table lookup (avg)", "O(1) amortized"),
    ("Hash table lookup (worst)", "O(n) — pathological collisions"),
    ("Balanced BST insert", "O(log n)"),
    ("Linked list access by index", "O(n)"),
    ("Array access by index", "O(1)"),
    ("Stack operations", "LIFO — push/pop O(1)"),
    ("Queue operations", "FIFO — enqueue/dequeue O(1)"),
    ("BFS time complexity", "O(V + E)"),
    ("DFS time complexity", "O(V + E)"),
    ("Dijkstra (binary heap)", "O((V + E) log V)"),
    ("Bellman-Ford", "O(V · E) — handles negative edges"),
    ("Floyd-Warshall", "O(V³) — all-pairs shortest paths"),
    ("Topological sort", "O(V + E) on a DAG"),
    ("Union-Find (path compression)", "Near O(α(n)) ≈ O(1) amortized"),
    ("Dynamic programming idea", "Overlapping subproblems + optimal substructure"),
    ("Greedy idea", "Local choice → global optimum (when applicable)"),
    ("Memoization", "Cache subproblem results (top-down DP)"),
    ("Recursion base case", "Terminating condition to stop recursive descent"),
    ("Trie lookup", "O(k) where k = key length"),
    ("Segment tree query/update", "O(log n)"),
    ("LRU cache get/put", "O(1) — hashmap + doubly linked list"),
    ("Big-O of for-each over n", "O(n)"),
    ("Big-O of nested loops over n", "O(n²)"),
    ("Master theorem case", "T(n) = a·T(n/b) + f(n) — compare f(n) with n^log_b(a)"),
    ("CAP theorem", "Pick 2 of: Consistency, Availability, Partition tolerance"),
    ("Idempotency", "Same input → same effect, regardless of repetition"),
    ("Mutex vs semaphore", "Mutex: exclusive lock. Semaphore: counted permits."),
    ("ACID", "Atomicity, Consistency, Isolation, Durability"),
]


# ---------------------------------------------------------------------------
# Deck layout. Each entry: (deck name, notetype, [(front, back), ...]).
# Notetype is "Basic" (Q→A) or "Basic (and reversed card)" (Q↔A) — the
# reversed type matches how language-learners actually use Anki and doubles
# the card count for vocab decks, which makes the heatmap denser.
# ---------------------------------------------------------------------------

DECKS = [
    ("Medicine::Pathology & Clinical", "Basic", MEDICAL_PATHOLOGY),
    ("Medicine::Pharmacology", "Basic", PHARMACOLOGY),
    ("Medicine::Anatomy — Bones", "Basic (and reversed card)", BONES),
    ("Medicine::Anatomy — Muscles", "Basic", MUSCLES),
    ("Medicine::Biochem — Amino Acids", "Basic (and reversed card)", AMINO_ACIDS),
    ("Medicine::Microbiology", "Basic", MICROBIOLOGY),
    ("Languages::Spanish — Top words", "Basic (and reversed card)", SPANISH_VOCAB),
    ("Languages::Japanese — JLPT N5", "Basic (and reversed card)", JAPANESE_N5),
    ("Languages::French — Top words", "Basic (and reversed card)", FRENCH_VOCAB),
    ("Languages::German — Top words", "Basic (and reversed card)", GERMAN_VOCAB),
    ("Languages::Greek Alphabet", "Basic (and reversed card)", GREEK_ALPHABET),
    ("Geography::World Capitals", "Basic", GEOGRAPHY),
    ("Geography::US State Capitals", "Basic", US_STATE_CAPITALS),
    ("Science::Periodic Table", "Basic (and reversed card)", PERIODIC_TABLE),
    ("Science::Chemistry — Constants & Laws", "Basic", CHEMISTRY),
    ("History::Key Dates", "Basic", HISTORY_DATES),
    ("CS::Algorithms & Big-O", "Basic", CS_TERMS),
]


# ---------------------------------------------------------------------------
# Revlog simulation — DAY-DRIVEN, PHASED.
#
# Models a real Anki power-user trajectory across multiple years:
#
#   Phase 0 — SLOW START (months 0 → ~14)
#     The user is just discovering Anki. Studies sporadically, introduces
#     few new cards per day, takes frequent breaks (vacations + skip days).
#     Daily volume averages ~30-60 reviews.
#
#   Phase 1 — RAMP (~14 → ~30 months)
#     The user commits. Larger daily new-card batches, fewer skipped days,
#     occasional cram sessions. Daily volume averages ~150-200 reviews.
#
#   Phase 2 — MATURE STREAK (~30 months → now)
#     Daily Anki has become routine. NO skipped days. Daily volume averages
#     ~400-500 reviews — driven by a sizeable due-card pile plus near-daily
#     mature-card "bonus" reviews (intentional re-practice). Intensity still
#     varies (some "light weeks" of 100-200/day, some cram days hitting 800+),
#     but the streak is unbroken.
#
# Ease growth stays conservative (effective factor cap ~1900) so cards
# revisit often. Lapse rate ~15% feeds the relearn queue. Cram days add
# 400-600 mature-card bonus reviews without advancing scheduling.
# ---------------------------------------------------------------------------


# Phase boundaries in *months from start*. Designed for the default 5.5-year
# window so the mature streak fills ~3 years at the end of the timeline.
_PHASE_BREAKS_MONTHS = (14.0, 30.0)


def _phase_for_day(day_idx: int) -> int:
    months = day_idx / 30.4375
    if months < _PHASE_BREAKS_MONTHS[0]:
        return 0
    if months < _PHASE_BREAKS_MONTHS[1]:
        return 1
    return 2


_PHASE_PARAMS = {
    0: {  # slow start
        "skip_prob": 0.18,
        "vacation_prob": 0.08, "vacation_len": (1, 7),
        "new_mean": 6, "new_sd": 4,
        "bonus_prob": 0.22, "bonus_pct": (0.04, 0.10),
        "cram_prob": 0.01, "cram_extras": (60, 130),
    },
    1: {  # ramp
        "skip_prob": 0.08,
        "vacation_prob": 0.03, "vacation_len": (1, 4),
        "new_mean": 22, "new_sd": 8,
        "bonus_prob": 0.55, "bonus_pct": (0.08, 0.18),
        "cram_prob": 0.025, "cram_extras": (220, 380),
    },
    2: {  # mature daily streak — no skips
        "skip_prob": 0.0,
        "vacation_prob": 0.0, "vacation_len": (0, 0),
        "new_mean": 14, "new_sd": 5,
        "bonus_prob": 0.96, "bonus_pct": (0.14, 0.32),
        "cram_prob": 0.045, "cram_extras": (560, 780),
    },
}


@dataclass
class CardState:
    introduced_day: int = -1     # day index since sim start; -1 = unintroduced
    factor: int = 2500           # permille
    ivl_days: int = 0            # current interval
    due_day: int = -1            # day index of next review
    reps: int = 0
    lapses: int = 0


def _revlog_row(ts_seconds: int, card_id: int, seq: int, *, ease: int,
                ivl: int, last_ivl: int, factor: int, time_ms: int,
                rtype: int) -> tuple:
    """Build a revlog INSERT tuple.

    revlog.id is a PRIMARY KEY in milliseconds. With high-volume days
    (~800 reviews) we can't trust a per-second timestamp to be unique,
    so we encode the within-day sequence directly into the low 16 bits
    of the millisecond id. That's safe because reviews still land on the
    correct local day (the heatmap groups by `id / 86_400_000`).
    """
    ms = ts_seconds * 1000 + seq
    return (ms, card_id, -1, ease, ivl, last_ivl, factor, time_ms, rtype)


def _pick_ease(rng: random.Random) -> int:
    """Realistic ease distribution: 15% Again, 18% Hard, 62% Good, 5% Easy.

    Higher Again/Hard than Anki defaults — matches the real distribution for
    big rote-memorization decks (USMLE step decks see ~14% lapse rates) and
    keeps cards cycling more often, which densifies the heatmap.
    """
    r = rng.random()
    if r < 0.15:
        return 1
    if r < 0.33:
        return 2
    if r < 0.95:
        return 3
    return 4


def _next_ivl(prev_ivl: int, factor: int, ease: int,
              rng: random.Random) -> tuple[int, int]:
    """Given prior ivl/factor and the button pressed, return (new_ivl, new_factor).

    We cap the *effective* growth multiplier at 2.0 (lower than Anki's 2.5)
    so cards revisit more often over a multi-year window — this is what
    turns ~3 reviews/day into ~50 reviews/day across the heatmap.
    """
    capped_factor = min(factor, 2000)
    if ease == 1:  # Again — lapse, reset interval
        return 0, max(1300, factor - 200)
    if ease == 2:  # Hard
        return max(1, round(prev_ivl * 1.15 * rng.uniform(0.92, 1.08))), max(1300, factor - 150)
    if ease == 4:  # Easy
        return (max(3, round(prev_ivl * (capped_factor / 1000) * 1.25
                             * rng.uniform(0.95, 1.10))),
                min(3000, factor + 150))
    # Good (3)
    return (max(2, round(prev_ivl * (capped_factor / 1000) * rng.uniform(0.92, 1.08))),
            factor)


def simulate_days(
    card_ids: list[int],
    start_ts: int,
    end_ts: int,
    rng: random.Random,
) -> tuple[list[tuple], dict[int, CardState]]:
    """Day-driven simulation across the entire study window.

    Returns (revlog_rows, final_states_by_card_id).
    """
    # +1 so the loop's final day lands ON end_ts's calendar day, not the
    # day before — keeps the heatmap streak alive through "today".
    num_days = max(1, (end_ts - start_ts) // DAY + 1)

    new_pool = list(card_ids)
    rng.shuffle(new_pool)
    state: dict[int, CardState] = {cid: CardState() for cid in card_ids}
    rows: list[tuple] = []

    skip_streak = 0
    # "Light week" within the mature phase: occasionally drop volume for
    # a stretch of days (school break, busy week at work) without breaking
    # the streak. Gives the heatmap visible low-density patches inside the
    # otherwise-saturated mature streak.
    light_week_remaining = 0
    light_factor = 1.0

    for d in range(num_days):
        day_start_ts = start_ts + d * DAY
        days_from_end = num_days - 1 - d
        phase = _phase_for_day(d)
        p = _PHASE_PARAMS[phase]

        # Skip-day decision. Suppressed for the last 10 days regardless of
        # phase so the heatmap shows a live current streak. In phase 2 the
        # streak is structurally unbroken anyway.
        protect_streak = days_from_end <= 10
        if not protect_streak and phase < 2:
            if skip_streak > 0:
                skip_streak -= 1
                continue
            if rng.random() < p["vacation_prob"]:
                lo, hi = p["vacation_len"]
                skip_streak = rng.randint(lo, hi)
                continue
            if rng.random() < p["skip_prob"]:
                continue

        # Mature-phase "light week" mechanic: occasionally start a 4-7 day
        # stretch of reduced volume. Streak stays unbroken but bonus/cram
        # rates drop substantially. ~6% of mature days kick off a light week.
        if phase == 2:
            if light_week_remaining > 0:
                light_week_remaining -= 1
                light_factor = rng.uniform(0.20, 0.45)
            elif rng.random() < 0.012:
                light_week_remaining = rng.randint(4, 7)
                light_factor = rng.uniform(0.20, 0.45)
            else:
                light_factor = 1.0

        # How many new cards to introduce today.
        if new_pool:
            base = max(0, int(rng.gauss(p["new_mean"], p["new_sd"])))
            # Occasional larger new-card batches: ~5% of days in phase 0/1.
            if phase < 2 and rng.random() < 0.05:
                base += rng.randint(20, 40)
            base = int(base * (light_factor if phase == 2 else 1.0))
            new_today_n = min(base, len(new_pool))
            today_new = [new_pool.pop() for _ in range(new_today_n)]
        else:
            today_new = []

        # Due reviews: every card whose due_day ≤ today.
        due_today = [
            cid for cid, st in state.items()
            if st.introduced_day != -1 and 0 <= st.due_day <= d
        ]
        rng.shuffle(due_today)

        # Cram days — phase-dependent. The big spikes on the heatmap.
        cram_extras: list[int] = []
        cram_p = p["cram_prob"] * (0.4 if phase == 2 and light_factor < 1.0 else 1.0)
        if rng.random() < cram_p:
            introduced = [cid for cid, st in state.items()
                          if st.introduced_day != -1 and st.ivl_days >= 4]
            if introduced:
                lo, hi = p["cram_extras"]
                cram_n = rng.randint(lo, hi)
                cram_extras = rng.sample(introduced,
                                         min(cram_n, len(introduced)))

        # Bonus / regular study-session extras — the dominant volume driver
        # in the mature phase. Sample a percentage of mature cards for
        # extra practice (rtype=4, no scheduling change).
        bonus_extras: list[int] = []
        if not cram_extras and rng.random() < p["bonus_prob"]:
            introduced = [cid for cid, st in state.items()
                          if st.introduced_day != -1 and st.ivl_days >= 5]
            if introduced:
                lo, hi = p["bonus_pct"]
                pct = rng.uniform(lo, hi) * (light_factor if phase == 2 else 1.0)
                bonus_n = max(5, int(len(introduced) * pct))
                bonus_extras = rng.sample(introduced,
                                          min(bonus_n, len(introduced)))

        # Cap due-review queue per day. Mature phase tolerates much bigger
        # queues than slow start — real users in their groove blow through
        # 200+ due cards without flinching.
        DAILY_CAP = (140, 320, 450)[phase]
        if len(due_today) > DAILY_CAP:
            overflow = due_today[DAILY_CAP:]
            due_today = due_today[:DAILY_CAP]
            for cid in overflow:
                state[cid].due_day = d + 1

        seq = 0

        # 1) Process today's due reviews
        for cid in due_today:
            st = state[cid]
            ease = _pick_ease(rng)
            last_ivl = st.ivl_days
            new_ivl, new_factor = _next_ivl(st.ivl_days, st.factor, ease, rng)

            ts = day_start_ts + rng.randint(8 * 3600, 22 * 3600)
            if ease == 1:
                rtype = 2  # relearn
                st.lapses += 1
                rows.append(_revlog_row(ts, cid, seq, ease=ease, ivl=-600,
                                        last_ivl=last_ivl, factor=new_factor,
                                        time_ms=rng.randint(3000, 14000),
                                        rtype=rtype))
                st.ivl_days = 1
                st.due_day = d + 1
            else:
                rtype = 1  # review
                rows.append(_revlog_row(ts, cid, seq, ease=ease, ivl=new_ivl,
                                        last_ivl=last_ivl, factor=new_factor,
                                        time_ms=rng.randint(2500, 16000),
                                        rtype=rtype))
                st.ivl_days = new_ivl
                # Add ±15% fuzz to scheduled next due (mimics Anki's fuzz).
                fuzz = max(1, int(new_ivl * 0.15))
                st.due_day = d + max(1, new_ivl + rng.randint(-fuzz, fuzz))
            st.factor = new_factor
            st.reps += 1
            seq += 1

        # 1b) Cram + bonus reviews on mature cards (no due-date update —
        # these are extra practice, not scheduler events).
        for cid in (*cram_extras, *bonus_extras):
            st = state[cid]
            ease = 3 if rng.random() > 0.05 else 2
            ts = day_start_ts + rng.randint(8 * 3600, 23 * 3600)
            rows.append(_revlog_row(ts, cid, seq, ease=ease,
                                    ivl=st.ivl_days, last_ivl=st.ivl_days,
                                    factor=st.factor,
                                    time_ms=rng.randint(1500, 7000),
                                    rtype=4))  # 4 = manual / cram
            st.reps += 1
            seq += 1

        # 2) Introduce new cards: two learning steps in the same day.
        for cid in today_new:
            st = state[cid]
            st.introduced_day = d
            # Step 1: ease=3 ("Good"), small lapse chance
            ease1 = 3 if rng.random() > 0.10 else 1
            ts1 = day_start_ts + rng.randint(8 * 3600, 21 * 3600)
            rows.append(_revlog_row(ts1, cid, seq, ease=ease1, ivl=-600,
                                    last_ivl=0, factor=2500,
                                    time_ms=rng.randint(4000, 14000),
                                    rtype=0))
            seq += 1
            # Step 2: graduate to 1-day interval
            ease2 = 3 if rng.random() > 0.05 else 1
            ts2 = ts1 + rng.randint(600, 1800)  # 10-30 min later
            rows.append(_revlog_row(ts2, cid, seq, ease=ease2,
                                    ivl=1 if ease2 != 1 else -600,
                                    last_ivl=-600, factor=2500,
                                    time_ms=rng.randint(3000, 12000),
                                    rtype=0))
            seq += 1
            st.factor = 2500
            st.reps = 2
            st.ivl_days = 1 if ease2 != 1 else 0
            st.due_day = d + (1 if ease2 != 1 else 1)

    return rows, state


# ---------------------------------------------------------------------------
# Main seeding logic.
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", type=Path, default=DEFAULT_DEMO_BASE,
                   help=f"Anki base dir (default: {DEFAULT_DEMO_BASE})")
    p.add_argument("--profile", default=PROFILE_NAME,
                   help=f"Profile inside the base (default: {PROFILE_NAME})")
    p.add_argument("--years", type=float, default=5.5,
                   help="Span of simulated history, in years (default: 5.5)")
    p.add_argument("--seed", type=int, default=20260521,
                   help="RNG seed for reproducible runs")
    p.add_argument("--force", action="store_true",
                   help="Overwrite an existing demo collection at --base")
    return p.parse_args()


def assert_safe_target(base: Path) -> None:
    """Refuse to write into the real Anki2 base, or anywhere ambiguous."""
    resolved = base.expanduser().resolve()
    real = REAL_BASE.resolve()
    if resolved == real or real in resolved.parents:
        raise SystemExit(
            f"refusing to seed: target {resolved} is inside your real Anki base "
            f"({real}). Pick a different --base (default is the safe demo path)."
        )


def prepare_base(base: Path, profile: str, force: bool) -> Path:
    """Ensure base/profile exists and return the collection.anki2 path.

    If a collection already exists, abort unless --force. With --force, wipe
    ONLY the demo base (assert_safe_target() has already proved this is not
    the real Anki base).
    """
    profile_dir = base / profile
    col_path = profile_dir / "collection.anki2"

    if col_path.exists():
        if not force:
            # The file exists. We don't try to OPEN it to count notes — if a
            # running Anki has it locked, the open would crash with a noisy
            # backtrace. Just point at the file and require explicit opt-in.
            raise SystemExit(
                f"refusing to seed: collection already exists at\n"
                f"  {col_path}\n"
                f"  → pass --force to wipe & re-seed the demo base.\n"
                f"  → if a demo Anki is running, quit it first."
            )
        # --force: blow it away. We already verified this isn't the real
        # base, so this is safe.
        print(f"  --force: wiping existing demo base {base}")
        shutil.rmtree(base)

    profile_dir.mkdir(parents=True, exist_ok=True)
    return col_path


def seed_collection(col_path: Path, years: float, rng: random.Random) -> dict:
    """Open a fresh collection at col_path and populate it.

    Returns a stats dict for the caller to print.
    """
    col = Collection(str(col_path))
    try:
        # Build all decks + notes
        deck_ids_by_name: dict[str, int] = {}
        all_card_ids: list[int] = []

        for deck_name, notetype_name, entries in DECKS:
            did = col.decks.id(deck_name)
            assert did is not None
            deck_ids_by_name[deck_name] = did
            nt = col.models.by_name(notetype_name)
            if nt is None:
                # Fall back to Basic if a (reversed) variant is missing.
                nt = col.models.by_name("Basic")
                assert nt is not None
            for front, back in entries:
                note = col.new_note(nt)
                note["Front"] = front
                note["Back"] = back
                col.add_note(note, did)
                all_card_ids.extend(note.card_ids())

        # Carve off a small "still new" pool from the freshly-added cards
        # so the reviewer has untouched cards to introduce when the user
        # opens the app. Everything else feeds the day-driven simulator.
        rng.shuffle(all_card_ids)
        new_pool_size = max(20, len(all_card_ids) // 8)
        sim_cards = all_card_ids[new_pool_size:]
        leave_new = all_card_ids[:new_pool_size]

        end_ts = int(time.time())
        # Align the simulator so its FINAL day starts at today's UTC midnight.
        # Without this, the last loop iteration's day_start_ts lands on
        # yesterday and "today" stays empty on the heatmap — no live streak.
        sim_days = max(1, int(years * 365.25) + 1)
        today_midnight = (end_ts // DAY) * DAY
        start_ts = today_midnight - (sim_days - 1) * DAY

        print(f"  simulating {years:g} years of daily study "
              f"across {len(sim_cards)} cards…")
        revlog_rows, final_state = simulate_days(sim_cards, start_ts, end_ts, rng)

        # Translate final per-card state into UPDATE rows.
        col_crt = col.db.scalar("select crt from col") or 0
        today_idx = (end_ts - col_crt) // DAY
        sim_today_idx = (end_ts - start_ts) // DAY  # day index inside the sim

        card_updates: list[tuple] = []
        for cid, st in final_state.items():
            if st.introduced_day == -1:
                # Got allocated to sim but never picked up by a day → leave new.
                continue
            # Translate sim's day index → Anki's "days since col.crt".
            days_until_due = max(0, st.due_day - sim_today_idx)
            due_days_since_crt = today_idx + days_until_due
            ivl = max(1, min(st.ivl_days, 36500))
            factor = max(1300, min(3500, st.factor))
            card_updates.append((
                2,                 # type = review
                2,                 # queue = review
                due_days_since_crt,
                ivl,
                factor,
                st.reps,
                st.lapses,
                0,                 # left
                end_ts,            # mod
                cid,
            ))

        # Bulk insert revlog and update cards.
        print(f"  inserting {len(revlog_rows):,} revlog rows…")
        col.db.executemany(
            "INSERT INTO revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            revlog_rows,
        )
        print(f"  updating scheduling state on {len(card_updates):,} cards…")
        col.db.executemany(
            "UPDATE cards SET type=?, queue=?, due=?, ivl=?, factor=?, "
            "reps=?, lapses=?, left=?, mod=? WHERE id=?",
            card_updates,
        )

        # Force a meaningful "due now" pile so the reviewer has work to do
        # when the user opens the app. Pick ~30-60 already-reviewed cards
        # and snap their due day to today (or just before).
        cards_with_history = [cid for cid in final_state
                              if final_state[cid].introduced_day != -1]
        due_now_count = min(40, max(20, len(cards_with_history) // 12))
        for cid in rng.sample(cards_with_history, due_now_count):
            col.db.execute(
                "UPDATE cards SET due=?, queue=2, type=2 WHERE id=?",
                today_idx + rng.randint(-1, 1), cid,
            )

        col.db.execute("ANALYZE")

        earliest_ms = col.db.scalar("select min(id) from revlog") or end_ts * 1000
        latest_ms = col.db.scalar("select max(id) from revlog") or end_ts * 1000
        active_days = col.db.scalar(
            "select count(distinct cast(id/86400000 as int)) from revlog"
        ) or 0

        stats = {
            "decks": len(DECKS),
            "notes": col.db.scalar("select count(*) from notes") or 0,
            "cards": col.db.scalar("select count(*) from cards") or 0,
            "revlog": col.db.scalar("select count(*) from revlog") or 0,
            "due_today": col.db.scalar(
                "select count(*) from cards where queue=2 and due <= ?",
                today_idx,
            ) or 0,
            "new_remaining": col.db.scalar(
                "select count(*) from cards where queue=0"
            ) or 0,
            "active_days": active_days,
            "history_start": dt.date.fromtimestamp(earliest_ms / 1000).isoformat(),
            "history_end": dt.date.fromtimestamp(latest_ms / 1000).isoformat(),
        }
        return stats
    finally:
        col.close()


def main() -> int:
    args = parse_args()
    assert_safe_target(args.base)

    print(f"seed_demo → base: {args.base}")
    print(f"           profile: {args.profile}")
    print(f"           history span: {args.years:g} years")
    if args.force:
        print(f"           --force: existing demo data will be removed")

    col_path = prepare_base(args.base, args.profile, args.force)

    rng = random.Random(args.seed)
    t0 = time.monotonic()
    stats = seed_collection(col_path, args.years, rng)
    elapsed = time.monotonic() - t0

    print()
    print(f"  ✓ seeded in {elapsed:.1f}s")
    print(f"    decks   : {stats['decks']}")
    print(f"    notes   : {stats['notes']:,}")
    print(f"    cards   : {stats['cards']:,}")
    print(f"    revlog  : {stats['revlog']:,} rows over {stats['active_days']} active days")
    print(f"              ({stats['history_start']} → {stats['history_end']})")
    print(f"    due now : {stats['due_today']:,}")
    print(f"    new     : {stats['new_remaining']:,}")
    print()
    print(f"  launch with:  make demo-run")
    print(f"  (or wipe & re-seed via:  make demo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
