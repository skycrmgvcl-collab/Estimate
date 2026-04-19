import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

st.set_page_config(page_title="DISCOM Estimator", layout="wide")

def clean_rate(rate_str):
    if not rate_str: return 0.0
    # Removes commas and non-numeric characters
    return float(re.sub(r'[^\d.]', '', str(rate_str)))

def process_uploaded_files(files):
    all_rows = []
    for uploaded_file in files:
        # Open PDF from memory
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    # Creating DF - assuming first row is headers
                    df = pd.DataFrame(table[1:], columns=table[0])
                    for _, row in df.iterrows():
                        # Use .get() to avoid errors if column names vary slightly
                        particulars = str(row.get('PARTICULARS', '')).replace('\n', ' ')
                        rate = clean_rate(row.get('RATE\n Rs.', 0))
                        if particulars and rate > 0:
                            all_rows.append({
                                "Group_Code": str(row.get('Group Code', '')).strip(),
                                "Particulars": particulars,
                                "Unit": row.get('UNIT', ''),
                                "Rate": rate
                            })
    return pd.DataFrame(all_rows)

st.title("⚡ DISCOM Work Expenditure Estimator")

# --- STEP 1: UPLOAD ---
st.sidebar.header("Data Sources")
uploaded_pdfs = st.sidebar.file_uploader(
    "Upload Cost Data PDFs", 
    type="pdf", 
    accept_multiple_files=True
)

if not uploaded_pdfs:
    st.info("Please upload one or more Cost Data PDFs in the sidebar to begin.")
    st.stop()

# Process data
master_df = process_uploaded_files(uploaded_pdfs)

# --- STEP 2: ESTIMATE LOGIC ---
if 'estimate_basket' not in st.session_state:
    st.session_state.estimate_basket = []

with st.container():
    st.subheader("Add Work Items")
    search = st.text_input("Search Particulars (e.g. 'Transformer', '11KV')")
    
    filtered_df = master_df[master_df['Particulars'].str.contains(search, case=False, na=False)]
    
    if not filtered_df.empty:
        selection = st.selectbox("Select Item", filtered_df['Particulars'].unique())
        item_row = master_df[master_df['Particulars'] == selection].iloc[0]
        
        c1, c2 = st.columns(2)
        qty = c1.number_input(f"Quantity ({item_row['Unit']})", min_value=0.0, step=1.0)
        
        if c2.button("Add to Estimate", use_container_width=True):
            st.session_state.estimate_basket.append({
                "Group Code": item_row['Group_Code'],
                "Description": item_row['Particulars'],
                "Unit": item_row['Unit'],
                "Rate": item_row['Rate'],
                "Qty": qty,
                "Total": qty * item_row['Rate']
            })
            st.rerun()

# --- STEP 3: DISPLAY & EXPORT ---
if st.session_state.estimate_basket:
    st.divider()
    final_df = pd.DataFrame(st.session_state.estimate_basket)
    st.dataframe(final_df, use_container_width=True)
    
    total = final_df['Total'].sum()
    st.metric("Grand Total Expenditure", f"Rs. {total:,.2f}")
    
    if st.button("Clear All"):
        st.session_state.estimate_basket = []
        st.rerun()
