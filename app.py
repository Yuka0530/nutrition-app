import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import gspread
from google.oauth2.service_account import Credentials

def connect_gsheet():

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )

    client = gspread.authorize(credentials)
    return client
# =========================
# マッピング保存読み込み
# =========================
def save_to_gsheet(original, selected):
    client = connect_gsheet()
    sheet = client.open("food_mapping").sheet1

    data = sheet.get_all_values()

    # ヘッダー除外
    rows = data[1:]

    for i, row in enumerate(rows, start=2):
        if row[0] == original and row[1] == selected:
            count = int(row[2]) if len(row) > 2 and row[2] else 0
            sheet.update_cell(i, 3, count + 1)
            return

    # 新規追加
    sheet.append_row([original, selected, 1])

def load_mapping():
    client = connect_gsheet()
    sheet = client.open("food_mapping").sheet1

    data = sheet.get_all_values()[1:]

    mapping = {}

    for original, selected, count in data:
        count = int(count) if count else 0

        if original not in mapping:
            mapping[original] = {}

        mapping[original][selected] = count

    return mapping

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
# 文字正規化
# =========================
def normalize(text):
    return str(text).replace("\u3000","").replace(" ","").strip()

# =========================
# 候補検索
# =========================
def get_candidates(word, mapping):
    word_n = normalize(word)

    candidates = [
        food for food in nutrition_dict
        if word_n in normalize(food)
    ]

    # 🔥 mappingに履歴があるなら必ず追加
    if word in mapping:
        for saved_food in mapping[word].keys():
            if saved_food not in candidates:
                candidates.append(saved_food)

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
# 調味料 大さじ・小さじ 重量
# =========================

SPOON_WEIGHT = {
    "しょうゆ": {"tbsp": 18, "tsp": 6},
    "醤油": {"tbsp": 18, "tsp": 6},
    "砂糖": {"tbsp": 9, "tsp": 3},
    "みりん": {"tbsp": 18, "tsp": 6},
    "酒": {"tbsp": 15, "tsp": 5},
    "酢": {"tbsp": 15, "tsp": 5},
    "マヨネーズ": {"tbsp": 14, "tsp": 5},
    "ケチャップ": {"tbsp": 18, "tsp": 6},
    "油": {"tbsp": 12, "tsp": 4},
    "オリーブオイル": {"tbsp": 12, "tsp": 4},
    "＜でん粉・でん粉製品＞　（でん粉類）　じゃがいもでん粉": {"tbsp": 9, "tsp": 3},
}

def get_spoon_weight(food_name, spoon_type):

    if food_name is None:
        return None

    for key in SPOON_WEIGHT:
        if key in food_name:
            return SPOON_WEIGHT[key][spoon_type]

    return None


# =========================
# 分量解析
# =========================
import re

def parse_amount(text, food_name=None, nutrition_dict=None):

    if text is None:
        return 0

    text = str(text)

    # ① g表記
    g_match = re.search(r'(\d+(?:\.\d+)?)\s*g', text)
    if g_match:
        return float(g_match.group(1))

    # ② 大さじ
    if "大さじ" in text:
    
        # ⭐ 分数チェック
        frac_match = re.search(r'(\d+)\s*/\s*(\d+)', text)
        if frac_match:
            count = float(frac_match.group(1)) / float(frac_match.group(2))
        else:
            num = re.findall(r'\d+(?:\.\d+)?', text)
            count = float(num[0]) if num else 1
    
        gram = get_spoon_weight(food_name, "tbsp")
    
        if gram is None:
            gram = 15
    
        return count * gram

    # ③ 小さじ
    if "小さじ" in text:
    
        frac_match = re.search(r'(\d+)\s*/\s*(\d+)', text)
        if frac_match:
            count = float(frac_match.group(1)) / float(frac_match.group(2))
        else:
            num = re.findall(r'\d+(?:\.\d+)?', text)
            count = float(num[0]) if num else 1
    
        gram = get_spoon_weight(food_name, "tsp")
    
        if gram is None:
            gram = 5
    
        return count * gram

    # ④ 個数変換
    unit_match = re.search(r'(\d+(?:\.\d+)?)', text)

    if unit_match and food_name and nutrition_dict:

        count = float(unit_match.group(1))

        if food_name in nutrition_dict:

            gram_per_unit = nutrition_dict[food_name].get("1個(g)", None)

            if gram_per_unit is None or pd.isna(gram_per_unit) or gram_per_unit in ["", "-", 0]:
                return 0.0
    
            return count * float(gram_per_unit)

    return 0.0
    
# =========================
# 候補を「選択回数順」にする関数
# =========================    
mapping = load_mapping()

def get_sorted_candidates(original_name, candidates, mapping):
    if original_name not in mapping:
        return candidates

    history = mapping.get(original_name, {})
    #st.write("original_name:", original_name)
    #st.write("mapping:", mapping)
    #st.write("history:", mapping.get(original_name))


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
        selected_foods = {}
        if "selected_foods" not in st.session_state:
            st.session_state.selected_foods = {}

        for i, ing in enumerate(ingredients):
            st.divider()
            st.write(f"### {ing['name']}")

            candidates = get_candidates(ing["name"], mapping)

            # ⭐ 過去データで並べ替え
            
            candidates = get_sorted_candidates(
                ing["name"],
                candidates,
                mapping
            )

            selected = None

            # ===== 候補 =====
            if candidates:
                selected = st.selectbox(
                    "候補",
                    candidates,
                    key=f"{i}_{ing['name']}_candidate"
                )
            else:
                st.warning("候補が見つかりません")
            
            # ===== 常に検索欄 =====
            search_word = st.text_input(
                "🔎 食材名を検索（候補に無い場合）",
                key=f"{i}_{ing['name']}_search"
            )
            
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
                else:
                    st.error("見つかりません")

            #st.write("selected:", selected)
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
                st.session_state.selected_foods[ing["name"]] = selected

                st.caption(f"📖 レシピ分量：{ing['amount']}")
             
                st.divider()


                kcal_per100 = float(nutrition_dict[selected]["エネルギー"])
                kcal = kcal_per100 * amount / 100

                st.write(f"👉 {kcal:.1f} kcal")
                total_cal += kcal

        st.divider()
        st.subheader(f"合計カロリー: {total_cal:.1f} kcal")


        if st.button("📌 レシピとして追加"):
        
            for original, selected in st.session_state.selected_foods.items():
                save_to_gsheet(original, selected)
        
            st.success("Google Sheetsに保存しました！✨")














































