import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import os

st.set_page_config(page_title="レシピ栄養計算", layout="wide")

# =========================
# 栄養データ読み込み
# =========================
@st.cache_data
def load_nutrition():
    df = pd.read_excel("nutrition.xlsx")
    return df.set_index("食材").to_dict(orient="index")

nutrition_dict = load_nutrition()

# =========================
# マッピング保存読み込み
# =========================
MAPPING_FILE = "food_mapping.json"

def load_mapping():
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_mapping(mapping):
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

mapping = load_mapping()

# =========================
# 文字正規化
# =========================
def normalize(text):
    return str(text).replace("\u3000","").replace(" ","").strip()

# =========================
# 候補検索
# =========================
def get_candidates(word):
    word_n = normalize(word)

    # 保存済み対応を最優先
    if word in mapping:
        return [mapping[word]]

    return [
        food for food in nutrition_dict
        if word_n in normalize(food)
    ]

# =========================
# URL抽出 & レシピ取得
# =========================
def extract_url(text):
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def get_recipe_data(url):
    headers={"User-Agent":"Mozilla/5.0"}
    res=requests.get(url,headers=headers)
    soup=BeautifulSoup(res.text,"html.parser")

    title=soup.title.get_text().split("|")[0].strip()

    ingredients=[]
    for item in soup.select(".ingredient"):
        name=item.select_one(".ingredient-name").get_text(strip=True)
        amount=item.select_one(".ingredient-serving").get_text(strip=True)
        ingredients.append({"name":name,"amount":amount})

    return title, ingredients

# =========================
# 分量解析
# =========================
def parse_amount(text):
    if text is None:
        return 0

    text = str(text)

    if "g" in text:
        return float(re.findall(r"\d+", text)[0])

    if "本" in text or "個" in text:
        return float(re.findall(r"\d+", text)[0]) * 100

    if "丁" in text:
        return float(re.findall(r"\d+", text)[0]) * 300

    if "大さじ" in text:
        return float(re.findall(r"\d+", text)[0]) * 15

    if "小さじ" in text:
        return float(re.findall(r"\d+", text)[0]) * 5

    return 100

# =========================
# UI
# =========================
st.title("🍳 レシピ栄養計算")

url_text = st.text_input("レシピURLを貼る")

if url_text:
    url = extract_url(url_text)

    if url:
        title, ingredients = get_recipe_data(url)
        st.subheader(title)

        multiplier = st.number_input("🔢 分量倍率", value=1.0, step=0.5)

        total_cal = 0

        for i, ing in enumerate(ingredients):
            st.divider()
            st.write(f"### {ing['name']}")

            candidates = get_candidates(ing["name"])

            # ===== 候補がある場合 =====
            if candidates:
                selected = st.selectbox(
                    "候補",
                    candidates,
                    key=f"{i}_{ing['name']}"
                )
            else:
                st.warning("候補が見つかりません")

                search_word = st.text_input(
                    "🔎 食材名を入力して検索",
                    key=f"{i}_{ing['name']}_search"
                )

                selected = None

                if search_word:
                    results = [
                        food for food in nutrition_dict
                        if normalize(search_word) in normalize(food)
                    ]

                    if results:
                        selected = st.selectbox(
                            "検索結果",
                            results,
                            key=f"{i}_{ing['name']}_manual"
                        )

                        # 保存ボタン
                        if st.button("この対応を保存", key=ing["name"]+"_save"):
                            mapping[ing["name"]] = selected
                            save_mapping(mapping)
                            st.success("保存しました！次回から自動表示されます")

                    else:
                        st.error("見つかりません")

            if selected:
                default_g = parse_amount(ing["amount"])

                amount = st.number_input(
                    "グラム",
                    value=float(default_g),
                    key=f"{i}_{ing['name']}+"_amt"
                )

                amount *= multiplier

                kcal_per100 = float(nutrition_dict[selected]["エネルギー"])
                kcal = kcal_per100 * amount / 100

                st.write(f"👉 {kcal:.1f} kcal")
                total_cal += kcal

        st.divider()
        st.subheader(f"合計カロリー: {total_cal:.1f} kcal")


