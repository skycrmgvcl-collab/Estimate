import streamlit as st
import pandas as pd
import re
import io

# Safe import for Streamlit Cloud
try:
    import pdfplumber
except ImportError:
    st.error("The library 'pdfplumber' is not installed. Ensure your 'requirements.txt' is correct.")
    st.stop()

st.set_page_config(page_title="DISCOM Estimator", layout="wide")

def clean_rate(rate_str):
    if not rate_str: return 0.0
    cleaned = re.sub(r'[^\d.]', '', str(rate_str))
    return float(cleaned) if cleaned else 0.0

def process_pdfs(files):
    all_rows = []
    for uploaded_file in files:
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table: continue
                
                # Get the header row and clean it
                headers = [str(h).strip().upper().replace('\n', ' ') for h in table[0]]
                df_temp = pd.DataFrame(table[1:], columns=headers)
                
                # Dynamically find column names even if they change slightly
                col_map = {
                    'CODE': next((c for c in headers if 'GROUP' in c or 'CODE' in c), None),
                    'DESC': next((c for c in headers if 'PARTICULARS' in c or 'DESCRIPTION' in c), None),
                    'UNIT': next((c for c in headers if 'UNIT' in c), None),
                    'RATE': next((c for c in headers if 'RATE' in c), None)
                }

                for _, row in df_temp.iterrows():
                    p_val = row.get(col_map['DESC'], '')
                    r_val = row.get(col_map['RATE'], 0)
                    
                    particulars = str(p_val).replace('\n', ' ').strip() if p_val else ""
                    rate = clean_rate(r_val)
                    
                    if particulars and rate > 0:
                        all_rows.append({
                            "Group_Code": str(row.get(col_map['CODE'], '')).strip().replace('\n', ''),
                            "Particulars": particulars,
                            "Unit": str(row.get(col_map['UNIT'], '')).strip(),
                            "Rate": rate
                        })
    return pd.DataFrame(all_rows)

st.title("⚡ DISCOM Work Expenditure Estimator")

# Sidebar Upload
st.sidebar.header("Upload Data")
uploaded_pdfs = st.sidebar.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)

if not uploaded_pdfs:
    st.info("👈 Please upload your Cost Data PDFs in the sidebar to begin.")
    st.stop()

# Load data
master_df = process_pdfs(uploaded_pdfs)

if master_df.empty:
    st.warning("No valid data found in the uploaded PDFs. Check the column headers.")
    st.stop()

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- Search and Select ---
st.subheader("Add Items to Estimate")
search = st.text_input("Search by Name (e.g., 'Transformer', '11 KV')")

# The fix: Case-insensitive search on the 'Particulars' column we created
filtered = master_df[master_df['Particulars'].str.contains(search, case=False, na=False)]

if not filtered.empty:
    selection = st.selectbox("Select Item", filtered['Particulars'].unique())
    item = master_df[master_df['Particulars'] == selection].iloc[0]
    
    c1, c2 = st.columns([2, 1])
    qty = c1.number_input(f"Quantity ({item['Unit']})", min_value=0.0, step=0.01)
    
    if c2.button("➕ Add to Estimate", use_container_width=True):
        st.session_state.basket.append({
            "Code": item['Group_Code'],
            "Particulars": item['Particulars'],
            "Unit": item['Unit'],
            "Rate": item['Rate'],
            "Qty": qty,
            "Total": qty * item['Rate']
        })
        st.rerun()

# --- Results ---
if st.session_state.basket:
    st.divider()
    est_df = pd.DataFrame(st.session_state.basket)
    st.table(est_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    st.metric("Grand Total Expenditure", f"Rs. {est_df['Total'].sum():,.2f}")
    
    if st.button("🗑️ Clear All"):
        st.session_state.basket = []
        st.rerun()
