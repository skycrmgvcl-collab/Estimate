import streamlit as st
import pandas as pd
import re
import io

# Safe import for Streamlit Cloud
try:
    import pdfplumber
except ImportError:
    st.error("The library 'pdfplumber' is not installed. Check your requirements.txt.")
    st.stop()

st.set_page_config(page_title="DISCOM Estimator", layout="wide")

def clean_rate(val):
    """Extracts only numbers from a string, handling newlines and commas."""
    if not val: return 0.0
    # Removes all non-numeric characters except the decimal point
    cleaned = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def process_pdfs(files):
    all_rows = []
    for uploaded_file in files:
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table or len(table) < 2:
                    continue
                
                for row in table:
                    # Clean all cells in the row: remove newlines and extra spaces
                    clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                    
                    # Logic to identify the right row:
                    # 1. Group Code usually starts with '9601' or is a 10-digit number
                    # 2. Rate is usually a large number in one of the last columns
                    
                    group_code = ""
                    particulars = ""
                    unit = ""
                    rate = 0.0
                    
                    # Search for Group Code (usually the first long number found)
                    for cell in clean_row:
                        if re.match(r'^\d{8,12}$', cell.replace(" ", "")):
                            group_code = cell
                            break
                    
                    if not group_code:
                        continue # Skip rows that don't have a valid Group Code
                    
                    # Based on your specific PDF structure:
                    # Index 0: Group Code, Index 2: Particulars, Index 3: Unit, Index 4: Rate
                    try:
                        particulars = clean_row[2]
                        unit = clean_row[3]
                        rate = clean_rate(clean_row[4])
                    except IndexError:
                        continue

                    if particulars and rate > 0:
                        all_rows.append({
                            "Group_Code": group_code,
                            "Particulars": particulars,
                            "Unit": unit,
                            "Rate": rate
                        })
    
    return pd.DataFrame(all_rows)

st.title("⚡ DISCOM Work Expenditure Estimator")

# --- SIDEBAR ---
st.sidebar.header("Data Sources")
uploaded_pdfs = st.sidebar.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)

if not uploaded_pdfs:
    st.info("👈 Please upload your Cost Data PDFs in the sidebar.")
    st.stop()

# --- DATA PROCESSING ---
master_df = process_pdfs(uploaded_pdfs)

if master_df.empty:
    st.error("Still unable to find data. Please ensure the PDF contains the 'Group Code' and 'Rate' table.")
    # Debug: show what the script sees
    with st.expander("Debug: See Raw PDF Content"):
        with pdfplumber.open(io.BytesIO(uploaded_pdfs[0].read())) as pdf:
            st.write(pdf.pages[0].extract_table())
    st.stop()

# --- ESTIMATE LOGIC ---
if 'basket' not in st.session_state:
    st.session_state.basket = []

st.subheader("Add Items to Estimate")
search = st.text_input("Search (e.g., 'Transformer', '11 KV', 'Connection')")
filtered = master_df[master_df['Particulars'].str.contains(search, case=False, na=False)]

if not filtered.empty:
    selection = st.selectbox("Select exact item:", filtered['Particulars'].unique())
    item = master_df[master_df['Particulars'] == selection].iloc[0]
    
    col1, col2 = st.columns([2, 1])
    qty = col1.number_input(f"Quantity for {item['Unit']}", min_value=0.0, step=0.01)
    
    if col2.button("➕ Add to Estimate", use_container_width=True):
        st.session_state.basket.append({
            "Code": item['Group_Code'],
            "Particulars": item['Particulars'],
            "Unit": item['Unit'],
            "Rate": item['Rate'],
            "Qty": qty,
            "Total": qty * item['Rate']
        })
        st.rerun()

# --- DISPLAY TABLE ---
if st.session_state.basket:
    st.divider()
    res_df = pd.DataFrame(st.session_state.basket)
    st.table(res_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    st.metric("Total Estimate", f"Rs. {res_df['Total'].sum():,.2f}")
    
    if st.button("🗑️ Clear All"):
        st.session_state.basket = []
        st.rerun()
