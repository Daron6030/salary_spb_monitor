import os
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st


# -------------------------------------------------
# Отключаем системные proxy/VPN-переменные для Python
# -------------------------------------------------
for proxy_var in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]:
    os.environ.pop(proxy_var, None)


st.set_page_config(
    page_title="Зарплаты HoReCa СПБ",
    layout="centered"
)

HH_API_URL = "https://api.hh.ru/vacancies"
SPB_AREA_ID = "2"

CATEGORIES = {
    "Повар": [
        "повар",
        "повар ресторан",
        "повар кафе",
        "повар горячего цеха",
        "повар холодного цеха",
        "су-шеф",
    ],
    "Официант": [
        "официант",
        "официант ресторан",
        "официант кафе",
    ],
    "Посудомойщица": [
        "посудомойщица",
        "мойщик посуды",
        "мойщица посуды",
        "кухонный работник",
    ],
    "Администратор": [
        "администратор ресторана",
        "администратор кафе",
        "менеджер ресторана",
        "менеджер кафе",
    ],
}


def format_money(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


def normalize_salary(salary):
    if not salary:
        return None

    if salary.get("currency") != "RUR":
        return None

    salary_from = salary.get("from")
    salary_to = salary.get("to")

    if salary_from and salary_to:
        return (salary_from + salary_to) / 2

    if salary_from:
        return salary_from

    if salary_to:
        return salary_to * 0.85

    return None


def get_requests_session():
    session = requests.Session()

    # Важно: не брать proxy из Windows / VPN / старых переменных окружения
    session.trust_env = False

    session.headers.update({
        "User-Agent": "salary-monitor-spb/1.0",
        "Accept": "application/json",
    })

    return session


def fetch_vacancies(query, max_pages=5):
    vacancies = []
    session = get_requests_session()

    for page in range(max_pages):
        params = {
            "text": query,
            "area": SPB_AREA_ID,
            "per_page": 100,
            "page": page,
            "search_field": "name",
        }

        try:
            response = session.get(
                HH_API_URL,
                params=params,
                timeout=20,
            )
        except Exception as e:
            st.warning(f"Ошибка соединения с HH по запросу «{query}»: {e}")
            break

        if response.status_code != 200:
            st.warning(
                f"HH API вернул ошибку {response.status_code} по запросу «{query}»"
            )
            break

        data = response.json()
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            salary_data = item.get("salary")

            if not salary_data:
                continue

            salary_value = normalize_salary(salary_data)

            if salary_value:
                vacancies.append({
                    "name": item.get("name", ""),
                    "employer": item.get("employer", {}).get("name", ""),
                    "salary": salary_value,
                    "url": item.get("alternate_url", ""),
                })

        time.sleep(0.2)

    return vacancies


def analyze_category(category_name, queries):
    all_vacancies = []

    for query in queries:
        vacancies = fetch_vacancies(query)
        all_vacancies.extend(vacancies)

    if not all_vacancies:
        return {
            "Категория": category_name,
            "Вакансий": 0,
            "Медиана": None,
            "Средняя": None,
            "Мин": None,
            "Макс": None,
        }, pd.DataFrame()

    df = pd.DataFrame(all_vacancies)
    df = df.drop_duplicates(subset=["name", "employer", "salary"])

    salaries = df["salary"]

    return {
        "Категория": category_name,
        "Вакансий": len(df),
        "Медиана": salaries.median(),
        "Средняя": salaries.mean(),
        "Мин": salaries.min(),
        "Макс": salaries.max(),
    }, df


st.title("💰 Зарплаты HoReCa СПБ")
st.caption("Данные автоматически собираются с HH.ru по Санкт-Петербургу")

st.info(
    "Считаем только вакансии, где указана зарплата. "
    "Если указана вилка — берем середину. "
    "Если указано только «до» — берем 85% от суммы."
)

if st.button("🔄 Обновить данные", use_container_width=True):
    results = []
    details = {}

    progress = st.progress(0)

    for index, (category, queries) in enumerate(CATEGORIES.items()):
        result, category_df = analyze_category(category, queries)

        results.append(result)
        details[category] = category_df

        progress.progress((index + 1) / len(CATEGORIES))

    df = pd.DataFrame(results)
    display_df = df.copy()

    for column in ["Медиана", "Средняя", "Мин", "Макс"]:
        display_df[column] = display_df[column].apply(format_money)

    st.subheader("Итоговая таблица")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Детализация по категориям")

    for category, category_df in details.items():
        with st.expander(category):
            if category_df.empty:
                st.write("Вакансии с зарплатой не найдены.")
            else:
                show_df = category_df.copy()
                show_df["salary"] = show_df["salary"].apply(format_money)

                show_df = show_df.rename(
                    columns={
                        "name": "Вакансия",
                        "employer": "Компания",
                        "salary": "Зарплата",
                        "url": "Ссылка",
                    }
                )

                st.dataframe(
                    show_df,
                    use_container_width=True,
                    hide_index=True,
                )

    st.success(
        f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

else:
    st.write("Нажмите кнопку **Обновить данные**, чтобы получить свежую статистику.")