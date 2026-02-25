import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import os

st.set_page_config(page_title="レシピ栄養計算アプリ")

# ==========================
# データ読み込み
# ==========================
@st.cache_data
def load_nutrition():
    df = pd.read_excel("nutrition.xlsx")
    return df.set_index("食材").to_dict(orient="index")

nutrition_dict = load_nutrition()

# ==========================
# 保存対応辞書
# ==========================
mapping_file = "food_mapping.json"

def load_mapping():
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_mapping(mapping):
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

food_mapping = load_mapping()

# ==========================
# 正規化
# ==========================
def normalize(text):
    return text.replace("\u3000", " ").replace(" ", "").strip()

def search_candidates(word):
    word = normalize(word)
    return [
        food for food in nutrition_dict
        if word in normalize(food)
    ]

# ==========================
# レシピ取得
# ==========================
def get_recipe_data(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    title = soup.title.get_text().split("|")[0].strip()

    ingredients = []
    for item in soup.select(".ingredient"):
        name = item.select_one(".ingredient-name").get_text(strip=True)
        amount = item.select_one(".ingredient-serving").get_text(strip=True)
        ingredients.append({"name": name, "amount": amount})

    return title, ingredients

# ==========================
# 分量パース
# ==========================
def parse_amount(amount):
    m = re.match(r'([\d/.]+)(.*)', amount)
    if not m:
        return 0, ""
    num = m.group(1)
    unit = m.group(2)
    try:
        value = eval(num)
    except:
        value = 0
    return value, unit

import streamlit as st
import json

# =====================
# マッピング保存読み込み
# =====================
def load_mapping():
    try:
        with open("food_mapping.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_mapping(mapping):
    with open("food_mapping.json", "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

food_mapping = load_mapping()

# ==========================
# UI
# ==========================
st.title("🍳 レシピ栄養計算アプリ")

url = st.text_input("レシピURLを入力")

if url:
    title, ingredients = get_recipe_data(url)
    st.subheader(title)

    scale = st.slider("倍率", 0.5, 3.0, 1.0, 0.5)

    total_cal = 0

    st.header("食材対応づけ")

    for ing in ingredients:

        name = ing["name"]
        st.subheader(f"■ {name}")

        if name in food_mapping:
            candidates = [food_mapping[name]]
        else:
            candidates = get_candidates(name)

        if not candidates:
            candidates = ["候補なし"]

        selected = st.selectbox(
            "候補",
            candidates,
            key=name
        )

        search_word = st.text_input(
            "候補がない場合ここで検索",
            key=f"search_{name}"
        )

        if st.button("検索", key=f"btn_{name}"):

            results = search_candidates(search_word, nutrition_dict)

            if results:
                new_choice = st.selectbox(
                    "検索結果",
                    results,
                    key=f"result_{name}"
                )

                if st.button("この対応を保存", key=f"save_{name}"):
                    food_mapping[name] = new_choice
                    save_mapping(food_mapping)
                    st.success("保存しました！")
                    st.experimental_rerun()

    for ing in ingredients:

        st.markdown("---")
        st.write("###", ing["name"])

        # 候補取得
        candidates = []

        if ing["name"] in food_mapping:
            candidates.append(food_mapping[ing["name"]])

        auto = search_candidates(ing["name"])
        for a in auto:
            if a not in candidates:
                candidates.append(a)

        if not candidates:
            st.warning("候補なし")
            continue

        selected = st.selectbox(
            "食品選択",
            candidates,
            key=ing["name"]
        )

        # 分量
        val, unit = parse_amount(ing["amount"])
        amount = st.number_input(
            f"分量 ({unit})",
            value=float(val),
            step=1.0,
            key=ing["name"]+"_amount"
        )

        amount *= scale

        # カロリー計算（100g基準想定）
        try:
            cal_per_100 = float(nutrition_dict[selected]["エネルギー"])
            cal = cal_per_100 * amount / 100
            total_cal += cal
            st.write(f"🔥 {round(cal,1)} kcal")
        except:
            st.write("カロリー計算不可")

    st.markdown("## 🧮 合計カロリー")
    st.success(f"{round(total_cal,1)} kcal")


