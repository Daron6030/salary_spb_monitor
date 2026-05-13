import re
import time
from datetime import datetime
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(
    page_title="Зарплаты HoReCa СПБ",
    layout="centered"
)

SPB_AREA_ID = "2"

CATEGORIES = {
    "Повар": ["повар", "повар ресторан", "повар кафе"],
    "Официант": ["официант", "официант ресторан", "официант кафе"],
    "Посудомойщица": ["посудомойщица", "мойщик посуды", "мойщица посуды"],
    "Администратор": ["администратор ресторана", "администратор кафе", "менеджер ресторана"],
}


def format_money(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


def parse_salary_text(text):
    if not text:
        return None

    text = text.replace("\xa0", " ").replace("₽", "руб").lower()

    if "руб" not in text and "rur" not in text:
        return None

    numbers = re.findall(r"\d[\d\s]*", text)
    numbers = [int(n.replace(" ", "")) for n in numbers if int(n.replace(" ", "")) >= 1000]

    if not numbers:
        return None

    if len(numbers) >= 2:
        return (numbers[0] + numbers[1]) / 2

    value = numbers[0]

    if "до" in text:
        return value * 0.85

    return value


def get_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    })
    return session


def fetch_from_hh_page(query, pages=3):
    session = get_session()
    vacancies = []

    for page in range(pages):
        url = (
            "https://spb.hh.ru/search/vacancy"
            f"?text={quote_plus(query)}"
            f"&area={SPB_AREA_ID}"
            f"&only_with_salary=true"
            f"&page={page}"
        )

        try:
            response = session.get(url, timeout=20)
        except Exception as e:
            st.warning(f"Ошибка соединения по запросу «{query}»: {e}")
            break

        if response.status_code != 200:
            st.warning(f"HH вернул ошибку {response.status_code} по запросу «{query}»")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select('[data-qa="vacancy-serp__vacancy"]')

        if not cards:
            cards = soup.select("div.serp-item")

        if not cards:
            break

        for card in cards:
            title_el = card.select_one('[data-qa="serp-item__title"]')
            salary_el = card.select_one('[data-qa="vacancy-serp__vacancy-compensation"]')
            employer_el = card.select_one('[data-qa="vacancy-serp__vacancy-employer"]')

            title = title_el.get_text(" ", strip=True) if title_el else ""
            salary_text = salary_el.get_text(" ", strip=True) if salary_el else ""
            employer = employer_el.get_text(" ", strip=True) if employer_el else ""

            salary_value = parse_salary_text(salary_text)

            if salary_value:
                vacancies.append({
                    "Вакансия": title,
                    "Компания": employer,
                    "Зарплата": salary_value,
                    "Зарплата текст": salary_text,
                })

        time.sleep(0.5)

    return vacancies


def analyze_category(category, queries):
    rows = []

    for query in queries:
        rows.extend(fetch_from_hh_page(query))

    if not rows:
        return {
            "Категория": category,
            "Вакансий": 0,
            "Медиана": None,
            "Средняя": None,
            "Мин": None,
            "Макс": None,
        }, pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["Вакансия", "Компания", "Зарплата текст"])

    salaries = df["Зарплата"]

    result = {
        "Категория": category,
        "Вакансий": len(df),
        "Медиана": salaries.median(),
        "Средняя": salaries.mean(),
        "Мин": salaries.min(),
        "Макс": salaries.max(),
    }

    return result, df


st.title("💰 Зарплаты HoReCa СПБ")
st.caption("Данные собираются с публичной выдачи HH.ru по Санкт-Петербургу")

st.info(
    "Считаем только вакансии, где указана зарплата. "
    "Если указана вилка — берем середину. "
    "Если указано только «до» — берем 85% от суммы."
)

if st.button("🔄 Обновить данные", use_container_width=True):
    results = []
    details = {}

    progress = st.progress(0)

    for i, (category, queries) in enumerate(CATEGORIES.items()):
        result, detail_df = analyze_category(category, queries)

        results.append(result)
        details[category] = detail_df

        progress.progress((i + 1) / len(CATEGORIES))

    result_df = pd.DataFrame(results)
    display_df = result_df.copy()

    for col in ["Медиана", "Средняя", "Мин", "Макс"]:
        display_df[col] = display_df[col].apply(format_money)

    st.subheader("Итоговая таблица")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Детализация")

    for category, detail_df in details.items():
        with st.expander(category):
            if detail_df.empty:
                st.write("Вакансии с зарплатой не найдены.")
            else:
                show_df = detail_df.copy()
                show_df["Зарплата расчет"] = show_df["Зарплата"].apply(format_money)
                show_df = show_df.drop(columns=["Зарплата"])

                st.dataframe(
                    show_df,
                    use_container_width=True,
                    hide_index=True,
                )

    st.success(f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

else:
    st.write("Нажмите **Обновить данные**, чтобы получить свежую статистику.")
