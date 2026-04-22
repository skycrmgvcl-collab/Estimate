import streamlit as st
import pandas as pd
import re
import io

# Safe import for Streamlit Cloud
try:
    import pdfplumber
except ImportError:
    st.error("The library 'pdfplumber' is not installed. Please ensure you have a 'requirements.txt' file in your GitHub repo with 'pdfplumber' written inside it.")
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
                if table:
                    # Creating DF - treating first row as headers
                    df = pd.DataFrame(table[1:], columns=table[0])
                    for _, row in df.iterrows():
                        # Extracting based on your specific RE Cost Data headers
                        particulars = str(row.get('PARTICULARS\n', row.get('PARTICULARS', ''))).replace('\n', ' ')
                        rate_val = row.get('RATE\n Rs.\n', row.get('RATE\n Rs.', 0))
                        rate = clean_rate(rate_val)
                        
                        if particulars.strip() and rate > 0:
                            all_rows.append({
                                "Group_Code": str(row.get('Group Code\n', row.get('Group Code', ''))).strip(),
                                "Particulars": particulars.strip(),
                                "Unit": str(row.get('UNIT\n', row.get('UNIT', ''))).strip(),
                                "Rate": rate
                            })
    return pd.DataFrame(all_rows)

st.title("⚡ DISCOM Work Expenditure Estimator")

# Sidebar Upload
st.sidebar.header("Upload Data")
uploaded_pdfs = st.sidebar.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)

if not uploaded_pdfs:
    st.info("👈 Upload your Cost Data PDFs in the sidebar to begin.")
    st.stop()

master_df = process_pdfs(uploaded_pdfs)

if 'basket' not in st.session_state:
    st.session_state.basket = []

# Search and Select
st.subheader("Add Items")
search = st.text_input("Search (e.g., '11 KV', 'Transformer')")
filtered = master_df[master_df['Particulars'].str.contains(search, case=False, na=False)]

if not filtered.empty:
    selection = st.selectbox("Select Item", filtered['Particulars'].unique())
    item = master_df[master_df['Particulars'] == selection].iloc[0]
    
    c1, c2 = st.columns([2, 1])
    qty = c1.number_input(f"Quantity ({item['Unit']})", min_value=0.0, step=0.01)
    
    if c2.button("➕ Add to Estimate"):
        st.session_state.basket.append({
            "Group Code": item['Group_Code'],
            "Particulars": item['Particulars'],
            "Unit": item['Unit'],
            "Rate": item['Rate'],
            "Qty": qty,
            "Total": qty * item['Rate']
        })
        st.rerun()

# Results
if st.session_state.basket:
    st.divider()
    est_df = pd.DataFrame(st.session_state.basket)
    st.table(est_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    st.metric("Grand Total", f"Rs. {est_df['Total'].sum():,.2f}")
    
    if st.button("🗑️ Clear All"):
        st.session_state.basket = []
        st.rerun()
