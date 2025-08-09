import streamlit as st
import pandas as pd
import gspread
import html
from oauth2client.service_account import ServiceAccountCredentials

# ---------- CONFIG ----------
st.set_page_config(page_title="Dress Catalogue", layout="wide")

# ---------- GOOGLE SHEETS CONNECTION ----------
def connect_to_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet_id = st.secrets["sheet"]["id"]
    sheet = client.open_by_key(sheet_id).sheet1
    return sheet

# ---------- LOAD DATA ----------
def load_data():
    sheet = connect_to_gsheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

# ---------- DISPLAY CATALOG ----------
def display_catalog(df):
    for _, row in df.iterrows():
        sold = row["sold"]
        opacity = 0.3 if sold else 1.0

        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(
                f"""
                <div style="position:relative; display:inline-block; width:100%;">
                    <img src="{html.escape(row['image_url'].strip())}" style="width:100%; height:auto;{' filter: grayscale(100%);' if row['sold'] else ''}">
                </div>
                """,
                unsafe_allow_html=True
            )
            # st.write(f"DEBUG: {row['image_url']}")
            # st.image(row['image_url'].strip(), use_container_width=True)
            # st.image(row["image_url"], width=150, output_format="auto", caption=row["name"])
        with col2:
            st.markdown(f"**Price:** ₹{row['price']}")
            st.markdown(f"**Discount:** {row['discount']}%")
            st.markdown(f"**Expected Price:** ₹{row['expected_price']}")
            st.markdown(f"**Likes:** {row['likes']}")
            st.button("Interested", key=f"like_{row['id']}")
            st.button("Ask Price", key=f"ask_{row['id']}")

# ---------- ADMIN LOGIN ----------
def admin_login():
    password = st.text_input("Enter admin password", type="password")
    if password == st.secrets["admin"]["password"]:
        st.session_state["is_admin"] = True
        st.success("Logged in as Admin!")
    else:
        st.error("Incorrect password")

# ---------- MAIN APP ----------
def main():
    st.title("Dress Catalogue")

    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    menu = ["Public", "Admin"]
    choice = st.sidebar.selectbox("Menu", menu)

    df = load_data()

    if choice == "Public":
        display_catalog(df)

    elif choice == "Admin":
        if not st.session_state["is_admin"]:
            admin_login()
        else:
            st.write("Admin panel will be here (coming next step).")
            st.dataframe(df)

if __name__ == "__main__":
    main()
