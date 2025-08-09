import streamlit as st
import pandas as pd
import gspread
import html
import requests
import base64
import io
import hashlib
from PIL import Image
from oauth2client.service_account import ServiceAccountCredentials

# ---------- CONFIG ----------
st.set_page_config(page_title="Dress Catalogue", layout="wide")

# ---------- NOTE ON REQUIRED SECRETS ----------
# Ensure your .streamlit/secrets.toml contains the required keys under:
# [gcp_service_account] (full JSON as keys)
# [sheet] id = "GOOGLE_SHEET_ID"
# [github] token, owner, repo, branch, images_path, placeholder_image, sold_stamp_url, max_repo_bytes
# (See earlier messages for the exact template)

# ---------- GOOGLE SHEETS CONNECTION ----------
def connect_to_gsheet():
    """
    Returns a Spreadsheet object so we can access named worksheets (catalogue, admins).
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet_id = st.secrets["sheet"]["id"]
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet

def get_gsheet_client():
    """
    Helper: returns the gspread client so we can access multiple worksheets (admins tab etc.)
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# ---------- LOAD DATA ----------
def load_data():
    """
    Loads catalogue worksheet into a pandas DataFrame and normalizes expected columns & types.
    """
    spreadsheet = connect_to_gsheet()
    try:
        sheet = spreadsheet.worksheet("catalogue")
    except Exception:
        # Fallback to first sheet if named worksheet not found
        sheet = spreadsheet.sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # Ensure expected columns exist
    expected_cols = ["id", "name", "price", "discount", "expected_price", "image_url", "sold", "likes"]
    for c in expected_cols:
        if c not in df.columns:
            df[c] = ""  # create missing columns
    # Normalize types
    df["sold"] = df["sold"].apply(lambda v: True if str(v).strip().lower() in ["true", "yes", "y", "1"] else False)
    df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)
    # Ensure id numeric where possible
    try:
        df["id"] = pd.to_numeric(df["id"], errors="coerce")
    except Exception:
        pass
    return df

# ---------- GITHUB HELPERS ----------
def github_api_headers():
    token = st.secrets["github"]["token"]
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

def get_images_folder_size():
    """
    Calculate total bytes in the images folder using GitHub API by listing repo tree.
    Returns size in bytes or 0 on failure.
    """
    owner = st.secrets["github"]["owner"]
    repo = st.secrets["github"]["repo"]
    branch = st.secrets["github"].get("branch", "main")
    images_path = st.secrets["github"].get("images_path", "images").strip("/")
    api = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    try:
        r = requests.get(api, headers=github_api_headers(), timeout=20)
        if r.status_code != 200:
            st.warning("Could not fetch repo tree (GitHub API). Skipping size check.")
            return 0
        tree = r.json().get("tree", [])
        total = 0
        for item in tree:
            if item.get("type") == "blob" and item.get("path", "").startswith(images_path + "/"):
                total += item.get("size", 0)
        return total
    except Exception as e:
        st.warning(f"Error checking repo size: {e}")
        return 0

def upload_image_to_github_bytes(image_bytes, filename, commit_message="Add image via Streamlit"):
    """
    Uploads given image bytes to GitHub repo/images/filename using Content API.
    Returns raw.githubusercontent.com URL or None.
    """
    owner = st.secrets["github"]["owner"]
    repo = st.secrets["github"]["repo"]
    branch = st.secrets["github"].get("branch", "main")
    images_path = st.secrets["github"].get("images_path", "images").strip("/")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{images_path}/{filename}"

    # First check if file exists to get sha (to update)
    get_r = requests.get(api_url + f"?ref={branch}", headers=github_api_headers(), timeout=20)
    encoded_content = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch
    }
    if get_r.status_code == 200:
        sha = get_r.json().get("sha")
        payload["sha"] = sha

    put_r = requests.put(api_url, json=payload, headers=github_api_headers(), timeout=30)
    if put_r.status_code in (200, 201):
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{images_path}/{filename}"
        return raw_url
    else:
        st.error(f"GitHub upload failed ({put_r.status_code}): {put_r.text}")
        return None

# ---------- IMAGE PROCESSING ----------
def compress_image_file(file_like, max_width=1200, quality=85):
    """
    Accepts file-like (from st.file_uploader). Returns bytes of compressed JPEG or None on failure.
    """
    try:
        img = Image.open(file_like).convert("RGB")
        w, h = img.size
        if w > max_width:
            new_h = int(max_width * h / w)
            img = img.resize((max_width, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.error(f"Image processing failed: {e}")
        return None

# ---------- SHEET HELPERS ----------
def append_row_to_sheet_dict(row_dict):
    """
    Append a row to the catalogue sheet. Keeps header order.
    row_dict keys should correspond to header names.
    """
    client = get_gsheet_client()
    sheet_id = st.secrets["sheet"]["id"]
    sh = client.open_by_key(sheet_id)
    try:
        sheet = sh.worksheet("catalogue")
    except Exception:
        sheet = sh.sheet1
    headers = sheet.row_values(1)
    row = [row_dict.get(h, "") for h in headers]
    sheet.append_row(row, value_input_option="USER_ENTERED")

def update_sheet_row_by_id(item_id, update_dict):
    """
    Find a row with id == item_id and update columns specified in update_dict.
    Returns True if updated, False otherwise.
    """
    client = get_gsheet_client()
    sheet_id = st.secrets["sheet"]["id"]
    sh = client.open_by_key(sheet_id)
    try:
        sheet = sh.worksheet("catalogue")
    except Exception:
        sheet = sh.sheet1
    records = sheet.get_all_records()
    for idx, r in enumerate(records, start=2):
        if str(r.get("id")) == str(item_id):
            headers = sheet.row_values(1)
            for k, v in update_dict.items():
                if k in headers:
                    col_idx = headers.index(k) + 1
                    sheet.update_cell(idx, col_idx, v)
            return True
    return False

# ---------- ADMIN (AUTH) HELPERS ----------
def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def admin_exists(username):
    """
    Returns True if username exists in admins worksheet.
    """
    client = get_gsheet_client()
    sheet_id = st.secrets["sheet"]["id"]
    sh = client.open_by_key(sheet_id)
    try:
        admin_ws = sh.worksheet("admins")
    except Exception:
        return False
    records = admin_ws.get_all_records()
    for r in records:
        if str(r.get("username")).strip() == str(username).strip():
            return True
    return False

def signup_admin(username, password):
    client = get_gsheet_client()
    sheet_id = st.secrets["sheet"]["id"]
    sh = client.open_by_key(sheet_id)
    try:
        admin_ws = sh.worksheet("admins")
    except Exception:
        # create admins worksheet with header
        admin_ws = sh.add_worksheet(title="admins", rows="100", cols="2")
        admin_ws.append_row(["username", "hashed_password"])
    hashed = hash_password(password)
    admin_ws.append_row([username, hashed])
    return True

def verify_admin_login(username, password):
    client = get_gsheet_client()
    sheet_id = st.secrets["sheet"]["id"]
    sh = client.open_by_key(sheet_id)
    try:
        admin_ws = sh.worksheet("admins")
    except Exception:
        return False
    records = admin_ws.get_all_records()
    hashed_input = hash_password(password)
    for r in records:
        if str(r.get("username")).strip() == str(username).strip() and str(r.get("hashed_password")) == hashed_input:
            return True
    return False

# ---------- DISPLAY CATALOG ----------
def display_catalog(df):
    sold_stamp_url = st.secrets["github"].get("sold_stamp_url", None)
    for _, row in df.iterrows():
        sold = row["sold"]
        opacity = 0.3 if sold else 1.0

        col1, col2 = st.columns([1, 2])
        with col1:
            img_url = str(row["image_url"]).strip()
            safe_url = html.escape(img_url)
            sold_style = "filter:grayscale(100%) opacity(0.35);" if sold else ""
            overlay_html = ""
            if sold and sold_stamp_url:
                overlay_html = f"""
                <div style="position:absolute; top:10px; left:10px; z-index:3;">
                  <img src="{html.escape(sold_stamp_url)}" style="width:120px; height:auto; opacity:0.9;" />
                </div>
                """
            st.markdown(
                f"""
                <div style="position:relative; display:inline-block; width:150px;">
                    <img src="{safe_url}" style="width:150px; height:auto; {sold_style}">
                    {overlay_html}
                </div>
                """,
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(f"**Name:** {row['name']}")
            st.markdown(f"**Price:** ₹{row['price']}")
            st.markdown(f"**Discount:** {row['discount']}%")
            st.markdown(f"**Expected Price:** ₹{row['expected_price']}")
            st.markdown(f"**Likes:** {row['likes']}")
            st.button("Interested", key=f"like_{row['id']}")
            st.button("Ask Price", key=f"ask_{row['id']}")

# ---------- ADMIN LOGIN (UI) ----------
def admin_login():
    st.subheader("Admin Access")
    mode = st.radio("Mode", ["Login", "Sign up"], index=0)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Submit"):
        if mode == "Sign up":
            if not username or not password:
                st.error("Provide username and password to sign up.")
            else:
                if admin_exists(username):
                    st.error("Username already exists.")
                else:
                    signup_admin(username, password)
                    st.success("Admin account created. Please log in.")
        else:  # Login
            if verify_admin_login(username, password):
                st.session_state["is_admin"] = True
                st.session_state["admin_user"] = username
                st.success("Logged in as admin.")
            else:
                st.error("Invalid credentials.")

# ---------- ADMIN PANEL ----------
def admin_panel():
    st.header("Admin Panel")

    # Upload form
    st.subheader("Add new dress")
    with st.form("upload_form"):
        input_name = st.text_input("Name")
        input_price = st.number_input("Price (₹)", min_value=0, step=1)
        input_discount = st.number_input("Discount (%)", min_value=0, max_value=100, step=1)
        input_sold = st.checkbox("Sold", value=False)
        uploaded_file = st.file_uploader("Upload dress image (jpg/png)", type=["jpg", "jpeg", "png"])
        submitted = st.form_submit_button("Upload & Add to Catalogue")

    if submitted:
        if not uploaded_file or not input_name:
            st.error("Please provide an image and name.")
        else:
            compressed = compress_image_file(uploaded_file, max_width=1200, quality=85)
            if not compressed:
                st.error("Image processing failed.")
            else:
                # Check repo size
                max_bytes = int(st.secrets["github"].get("max_repo_bytes", 500000000))
                current_size = get_images_folder_size()
                # create filename safe
                base_fn = input_name.strip().lower().replace(" ", "_")
                filename = f"{base_fn}.jpg"
                if current_size + len(compressed) > max_bytes:
                    st.warning("Repo storage limit reached — using placeholder image instead of uploading.")
                    image_url = st.secrets["github"].get("placeholder_image")
                else:
                    raw_url = upload_image_to_github_bytes(compressed, filename, commit_message=f"Add {filename} via admin")
                    if raw_url:
                        image_url = raw_url
                        st.success("Image uploaded to GitHub images folder.")
                    else:
                        st.error("Image upload failed; using placeholder.")
                        image_url = st.secrets["github"].get("placeholder_image")

                # Prepare row
                df = load_data()
                try:
                    max_id = int(df["id"].max())
                    new_id = max_id + 1
                except Exception:
                    new_id = 1
                expected_price = int(round(input_price * (1 - (input_discount / 100.0))))
                row_dict = {
                    "id": new_id,
                    "name": input_name,
                    "price": input_price,
                    "discount": input_discount,
                    "expected_price": expected_price,
                    "image_url": image_url,
                    "sold": "TRUE" if input_sold else "FALSE",
                    "likes": 0
                }
                append_row_to_sheet_dict(row_dict)
                st.success("New product added to catalogue (Google Sheet updated).")

    # Quick editor for sold status
    st.subheader("Mark item sold / unsold")
    df = load_data()
    st.dataframe(df)
    selected_id = st.text_input("Enter item id to toggle sold status")
    if st.button("Toggle Sold Status"):
        if not selected_id:
            st.error("Enter an id.")
        else:
            matches = df[df["id"].astype(str) == str(selected_id)]
            if matches.empty:
                st.error("ID not found.")
            else:
                cur = matches.iloc[0]
                new_status = not bool(cur["sold"])
                update_ok = update_sheet_row_by_id(selected_id, {"sold": "TRUE" if new_status else "FALSE"})
                if update_ok:
                    st.success(f"Updated sold status to {new_status} for id {selected_id}.")
                else:
                    st.error("Failed to update sheet.")

# ---------- MAIN APP ----------
def main():
    st.title("Dress Catalogue")

    # initialize
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False
    if "admin_user" not in st.session_state:
        st.session_state["admin_user"] = None

    menu = ["Public", "Admin"]
    choice = st.sidebar.selectbox("Menu", menu)

    df = load_data()

    if choice == "Public":
        display_catalog(df)

    elif choice == "Admin":
        if not st.session_state["is_admin"]:
            admin_login()
        else:
            st.write(f"Logged in as: {st.session_state.get('admin_user', 'admin')}")
            admin_panel()
            st.subheader("Current Catalogue (preview)")
            st.dataframe(load_data())

if __name__ == "__main__":
    main()
