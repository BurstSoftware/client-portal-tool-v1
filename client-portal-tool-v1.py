import streamlit as st
import sqlite3
import pandas as pd
import datetime
from streamlit_chat import message
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import os

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("client_portal.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (project_id INTEGER PRIMARY KEY, client_username TEXT, name TEXT, status TEXT, milestone TEXT, last_updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS invoices 
                 (invoice_id INTEGER PRIMARY KEY, project_id INTEGER, amount REAL, status TEXT, due_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (message_id INTEGER PRIMARY KEY, project_id INTEGER, sender TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses 
                 (expense_id INTEGER PRIMARY KEY, project_id INTEGER, description TEXT, amount REAL)''')
    # Sample data
    c.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", ("client1", "pass123", "client"))
    c.execute("INSERT OR IGNORE INTO projects VALUES (?, ?, ?, ?, ?, ?)", 
              (1, "client1", "Roofing Project", "In Progress", "Foundation Complete", "2025-04-20"))
    c.execute("INSERT OR IGNORE INTO invoices VALUES (?, ?, ?, ?, ?)", 
              (1, 1, 5000.0, "Pending", "2025-05-01"))
    c.execute("INSERT OR IGNORE INTO expenses VALUES (?, ?, ?, ?)", 
              (1, 1, "Roof Tiles", 1200.0))
    conn.commit()
    conn.close()

init_db()

# --- Google Drive API Setup ---
# Note: Requires credentials.json from Google Cloud Console and token storage
def init_google_drive():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/drive"])
    if not creds or not creds.valid:
        st.error("Google Drive API credentials needed. Please set up credentials.json.")
        return None
    return build("drive", "v3", credentials=creds)

# --- Authentication ---
def check_login(username, password):
    conn = sqlite3.connect("client_portal.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()
    return user

# --- Streamlit App ---
st.title("Client Portal")

# Session state for login and chat
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.messages = []

# Login UI
if not st.session_state.logged_in:
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = check_login(username, password)
        if user:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Logged in successfully!")
        else:
            st.error("Invalid credentials")
else:
    st.sidebar.write(f"Welcome, {st.session_state.username}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.experimental_rerun()

    # --- Main Portal Features ---
    tabs = st.tabs(["Project Timeline", "Invoices", "Documents", "Messages", "Expenses"])

    # Project Timeline
    with tabs[0]:
        st.subheader("Project Timeline")
        conn = sqlite3.connect("client_portal.db")
        projects = pd.read_sql_query(
            f"SELECT * FROM projects WHERE client_username='{st.session_state.username}'", conn)
        conn.close()
        if not projects.empty:
            for _, project in projects.iterrows():
                st.markdown(f"**{project['name']}**")
                st.write(f"Status: {project['status']}")
                st.write(f"Current Milestone: {project['milestone']}")
                st.write(f"Last Updated: {project['last_updated']}")
                st.progress(0.5)  # Mock progress
        else:
            st.write("No projects assigned.")

    # Invoices
    with tabs[1]:
        st.subheader("Invoices")
        conn = sqlite3.connect("client_portal.db")
        invoices = pd.read_sql_query(
            f"SELECT i.* FROM invoices i JOIN projects p ON i.project_id=p.project_id WHERE p.client_username='{st.session_state.username}'", conn)
        conn.close()
        if not invoices.empty:
            for _, invoice in invoices.iterrows():
                st.markdown(f"**Invoice #{invoice['invoice_id']}**")
                st.write(f"Amount: ${invoice['amount']:.2f}")
                st.write(f"Status: {invoice['status']}")
                st.write(f"Due Date: {invoice['due_date']}")
                if invoice["status"] == "Pending":
                    if st.button(f"Pay Invoice #{invoice['invoice_id']}", key=f"pay_{invoice['invoice_id']}"):
                        st.write("Redirecting to Stripe/PayPal... (Placeholder)")
        else:
            st.write("No invoices found.")

    # Documents
    with tabs[2]:
        st.subheader("Documents")
        drive_service = init_google_drive()
        if drive_service:
            # Upload file
            uploaded_file = st.file_uploader("Upload Document", type=["pdf", "docx", "jpg"])
            if uploaded_file:
                file_metadata = {"name": uploaded_file.name}
                media = MediaFileUpload(uploaded_file, resumable=True)
                file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
                st.success(f"Uploaded {uploaded_file.name}")

            # List files
            results = drive_service.files().list(pageSize=10, fields="files(id, name)").execute()
            files = results.get("files", [])
            if files:
                st.write("Available Documents:")
                for file in files:
                    col1, col2 = st.columns([3, 1])
                    col1.write(file["name"])
                    if col2.button("Download", key=file["id"]):
                        request = drive_service.files().get_media(fileId=file["id"])
                        fh = io.BytesIO()
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                        fh.seek(0)
                        st.download_button(f"Download {file['name']}", fh, file["name"])
            else:
                st.write("No documents found.")
        else:
            st.write("Google Drive integration not available.")

    # Messages
    with tabs[3]:
        st.subheader("Messages")
        project_id = 1  # Hardcoded for demo
        conn = sqlite3.connect("client_portal.db")
        messages = pd.read_sql_query(f"SELECT * FROM messages WHERE project_id={project_id}", conn)
        
        # Display messages
        for _, msg in messages.iterrows():
            is_user = msg["sender"] == st.session_state.username
            message(msg["content"], is_user=is_user, key=msg["message_id"])
        
        # New message
        new_message = st.text_input("Type your message...")
        if st.button("Send"):
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c = conn.cursor()
            c.execute("INSERT INTO messages (project_id, sender, content, timestamp) VALUES (?, ?, ?, ?)",
                      (project_id, st.session_state.username, new_message, timestamp))
            conn.commit()
            st.experimental_rerun()
        conn.close()

    # Expenses (Receipts Input Tool Integration)
    with tabs[4]:
        st.subheader("Expenses")
        conn = sqlite3.connect("client_portal.db")
        expenses = pd.read_sql_query(
            f"SELECT e.* FROM expenses e JOIN projects p ON e.project_id=p.project_id WHERE p.client_username='{st.session_state.username}'", conn)
        conn.close()
        if not expenses.empty:
            for _, expense in expenses.iterrows():
                st.markdown(f"**Expense #{expense['expense_id']}**")
                st.write(f"Description: {expense['description']}")
                st.write(f"Amount: ${expense['amount']:.2f}")
        else:
            st.write("No expenses recorded.")
