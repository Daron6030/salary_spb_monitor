import os
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st


# -------------------------------------------------
# Настройки страницы
# -------------------------------------------------
st.set_page_config(
    page_title="Зарплаты HoReCa СПБ",
    layout="centered"
)

# -------------------------------------------------
# HH API
# -------------------------------------------------
HH_API_URL = "https://api.hh.ru/vacancies"
SPB_AREA_ID = "2"

# ВАЖНО:
# укажи свою реальную почту
HH_USER_AGENT_EMAIL = "yourmail@gmail.com"

HH_USER_AGENT = (
    f"salary-spb-monitor/1.0 "
    f"(contact: {HH_USER_AGENT_EMAIL})"
)

# -------------------------------------------------
# Категории
# -------------------------------------------------
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

# -------------------------------------------------
# Удаляем локальные proxy windows/vpn
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


# -------------------------------------------------
# Форматирование денег
# -------------------------------------------------
def format_money(value):

    if value is None or pd.isna(value):
        return "—"

    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


# -------------------------------------------------
# Нормализация зарплаты
# -------------------------------------------------
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


# -------------------------------------------------
# Session requests
# -------------------------------------------------
def get_session():

    session = requests.Session()

    session.trust_env = False

    session.headers.update({
        "User-Agent": HH_USER_AGENT,
        "HH-User-Agent": HH_USER_AGENT,
        "Accept": "application/json",
    })

    # ---------------------------------------------
    # PROXY из Streamlit Secrets
    # ---------------------------------------------
    proxy = st.secrets.get("PROXY_URL")

    if proxy:
        session.proxies.update({
            "http": proxy,
            "https": proxy,
        })

    return session


# -------------------------------------------------
# Получение вакансий
# -------------------------------------------------
def fetch_vacancies(query, max_pages=3):

    session = get_session()

    vacancies = []
    errors = []

    for page in range(max_pages):

        params = {
            "text": query,
            "area": SPB_AREA_ID,
            "only_with_salary": "true",
            "per_page": 100,
            "page": page,
            "search_field": "name",
        }

        try:

            response = session.get(
                HH_API_URL,
                params=params,
                timeout=30,
            )

        except Exception as e:

            errors.append(
                f"Ошибка соединения по запросу «{query}»: {e}"
            )

            break

        # -----------------------------------------
        # Ошибки HH
        # -----------------------------------------
        if response.status_code != 200:

            body = response.text[:500]

            errors.append(
                f"HH API вернул {response.status_code} "
                f"по запросу «{query}». "
                f"Ответ: {body}"
            )

            break

        data = response.json()

        items = data.get("items", [])

        if not items:
            break

        for item in items:

            salary_data = item.get("salary")

            salary_value = normalize_salary(salary_data)

            if not salary_value:
                continue

            vacancies.append({
                "id": item.get("id", ""),
                "Вакансия": item.get("name", ""),
                "Компания": item.get("employer", {}).get("name", ""),
                "Город": item.get("area", {}).get("name", ""),
                "Зарплата": salary_value,
                "Ссылка": item.get("alternate_url", ""),
                "Запрос": query,
            })

        time.sleep(0.3)

    return vacancies, errors


# -------------------------------------------------
# Анализ категории
# -------------------------------------------------
def analyze_category(category_name, queries):

    all_vacancies = []
    all_errors = []

    for query in queries:

        vacancies, errors = fetch_vacancies(query)

        all_vacancies.extend(vacancies)
        all_errors.extend(errors)

    if not all_vacancies:

        result = {
            "Категория": category_name,
            "Вакансий": 0,
            "Медиана": None,
            "Средняя": None,
            "Мин": None,
            "Макс": None,
        }

        return result, pd.DataFrame(), all_errors

    df = pd.DataFrame(all_vacancies)

    # удаляем дубли
    df = df.drop_duplicates(subset=["id"])

    salaries = df["Зарплата"]

    result = {
        "Категория": category_name,
        "Вакансий": len(df),
        "Медиана": salaries.median(),
        "Средняя": salaries.mean(),
        "Мин": salaries.min(),
        "Макс": salaries.max(),
    }

    return result, df, all_errors


# -------------------------------------------------
# Интерфейс
# -------------------------------------------------
st.title("💰 Зарплаты HoReCa СПБ")

st.caption(
    "Данные собираются через HH API "
    "по Санкт-Петербургу"
)

st.info(
    "Считаем только вакансии, где указана зарплата. "
    "Если указана вилка — берем середину. "
    "Если указано только «до» — берем 85% от суммы."
)

with st.expander("⚙️ Диагностика"):

    st.write("Источник: HH API")
    st.write("Город: Санкт-Петербург")
    st.write("Area ID:", SPB_AREA_ID)
    st.write("User-Agent:", HH_USER_AGENT)

    if "PROXY_URL" in st.secrets:
        st.success("Proxy подключен")
    else:
        st.warning("Proxy НЕ подключен")


# -------------------------------------------------
# Кнопка обновления
# -------------------------------------------------
if st.button(
    "🔄 Обновить данные",
    use_container_width=True
):

    results = []
    details = {}
    errors_by_category = {}

    progress = st.progress(0)

    for i, (category, queries) in enumerate(CATEGORIES.items()):

        result, detail_df, errors = analyze_category(
            category,
            queries
        )

        results.append(result)

        details[category] = detail_df

        errors_by_category[category] = errors

        progress.progress(
            (i + 1) / len(CATEGORIES)
        )

    # ---------------------------------------------
    # Итоговая таблица
    # ---------------------------------------------
    result_df = pd.DataFrame(results)

    display_df = result_df.copy()

    for col in [
        "Медиана",
        "Средняя",
        "Мин",
        "Макс"
    ]:

        display_df[col] = display_df[col].apply(
            format_money
        )

    st.subheader("Итоговая таблица")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    # ---------------------------------------------
    # Детализация
    # ---------------------------------------------
    st.subheader("Детализация")

    for category, detail_df in details.items():

        with st.expander(category):

            if detail_df.empty:

                st.write(
                    "Вакансии с зарплатой не найдены."
                )

            else:

                show_df = detail_df.copy()

                show_df["Зарплата расчет"] = (
                    show_df["Зарплата"]
                    .apply(format_money)
                )

                show_df = show_df.drop(
                    columns=["Зарплата", "id"],
                    errors="ignore"
                )

                st.dataframe(
                    show_df,
                    use_container_width=True,
                    hide_index=True,
                )

    # ---------------------------------------------
    # Ошибки
    # ---------------------------------------------
    all_errors = []

    for category, errors in errors_by_category.items():

        for err in errors:

            all_errors.append(
                f"{category}: {err}"
            )

    if all_errors:

        with st.expander("⚠️ Ошибки HH API"):

            for err in all_errors:
                st.warning(err)

    st.success(
        f"Обновлено: "
        f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

else:

    st.write(
        "Нажмите **Обновить данные**, "
        "чтобы получить свежую статистику."
    )
