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

    candidates = [
        food for food in nutrition_dict
        if word_n in normalize(food)
    ]

    return candidates

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
import re

def parse_amount(text, food_name=None, nutrition_dict=None):
    if text is None:
        return 0

    text = str(text)

    # 🔹① (250g) のような g表記を最優先取得
    g_match = re.search(r'(\d+(?:\.\d+)?)\s*g', text)
    if g_match:
        return float(g_match.group(1))

    # 🔹② 個・本・枚など → nutrition.xlsxの「1個(g)」参照
    unit_match = re.search(r'(\d+)', text)
    if unit_match and food_name and nutrition_dict:
        count = float(unit_match.group(1))

        if food_name in nutrition_dict:
            gram_per_unit = nutrition_dict[food_name].get("1個(g)", None)

            if gram_per_unit not in [None, "", "-", 0]:
                return count * float(gram_per_unit)

    # 🔹③ 大さじ・小さじ
    if "大さじ" in text:
        num = re.findall(r'\d+', text)
        return float(num[0]) * 15 if num else 15

    if "小さじ" in text:
        num = re.findall(r'\d+', text)
        return float(num[0]) * 5 if num else 5

    # 🔹④ fallback
    return 0
    
# =========================
# 候補を「選択回数順」にする関数
# =========================    

def get_sorted_candidates(original_name, candidates, mapping):
    if original_name not in mapping:
        return candidates

    history = mapping.get(original_name, {})

    if not isinstance(history, dict):
        return candidates

    return sorted(
        candidates,
        key=lambda x: history.get(x, 0),
        reverse=True
    )

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

            # ⭐ 過去データで並べ替え
            candidates = get_sorted_candidates(
                ing["name"],
                candidates,
                mapping
            )

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
                        #if st.button("この対応を保存", key=ing["name"]+"_save"):
                            #mapping[ing["name"]] = selected
                            #save_mapping(mapping)
                            #st.success("保存しました！次回から自動表示されます")

                    else:
                        st.error("見つかりません")

            if selected:
                default_g = parse_amount(
                ing["amount"],
                food_name=selected,
                nutrition_dict=nutrition_dict
                )

                amount = st.number_input(
                    "グラム",
                    value=float(default_g),
                    key=f"{i}_{ing['name']}_amt"
                )

                amount *= multiplier


                st.divider()

            if st.button("📌 レシピとして追加"):
            
                mapping = load_mapping()

                selected_foods = {}

                if selected:
                    selected_foods[ing["name"]] = selected
            
                    for original, selected in selected_foods.items():
                
                        if original not in mapping:
                            mapping[original] = {}
                
                        mapping[original][selected] = (
                            mapping[original].get(selected, 0) + 1
                        )
                
                    save_mapping(mapping)
            
                st.success("レシピを追加しました！✨")


                kcal_per100 = float(nutrition_dict[selected]["エネルギー"])
                kcal = kcal_per100 * amount / 100

                st.write(f"👉 {kcal:.1f} kcal")
                total_cal += kcal

        st.divider()
        st.subheader(f"合計カロリー: {total_cal:.1f} kcal")









