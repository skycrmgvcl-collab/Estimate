import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

st.set_page_config(page_title="DISCOM Estimate Builder", layout="wide")

def clean_rate(rate_str):
    """Cleans currency strings like '314,561' into numbers."""
    if not rate_str: return 0.0
    cleaned = re.sub(r'[^\d.]', '', str(rate_str))
    return float(cleaned) if cleaned else 0.0

def process_pdfs(files):
    """Extracts cost data from multiple uploaded PDFs."""
    all_rows = []
    for uploaded_file in files:
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    # Creating DF - treating first row as headers
                    df = pd.DataFrame(table[1:], columns=table[0])
                    for _, row in df.iterrows():
                        # Cleaning columns based on your specific PDF headers
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
st.caption("Automated Estimation Tool for Sub-division Work")

# --- SIDEBAR: FILE UPLOAD ---
st.sidebar.header("Configuration")
uploaded_pdfs = st.sidebar.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)

if not uploaded_pdfs:
    st.info("👈 Please upload your Cost Data PDFs in the sidebar to start.")
    st.stop()

# Load and process data once
master_df = process_pdfs(uploaded_pdfs)

# --- ESTIMATE LOGIC ---
if 'basket' not in st.session_state:
    st.session_state.basket = []

with st.container():
    st.subheader("Add Work Items")
    search = st.text_input("Search (e.g., '11 KV', 'Transformer', 'Service')")
    
    # Filtering the master data based on search
    filtered = master_df[master_df['Particulars'].str.contains(search, case=False, na=False)]
    
    if not filtered.empty:
        selection = st.selectbox("Select exact item from list:", filtered['Particulars'].unique())
        item = master_df[master_df['Particulars'] == selection].iloc[0]
        
        c1, c2 = st.columns([2, 1])
        qty = c1.number_input(f"Enter Quantity ({item['Unit']})", min_value=0.0, step=0.01, format="%.2f")
        
        if c2.button("➕ Add to Estimate", use_container_width=True):
            st.session_state.basket.append({
                "Group Code": item['Group_Code'],
                "Particulars": item['Particulars'],
                "Unit": item['Unit'],
                "Rate": item['Rate'],
                "Qty": qty,
                "Total": qty * item['Rate']
            })
            st.success("Item added!")
            st.rerun()
    else:
        st.warning("No items found matching your search.")

# --- DISPLAY TABLE & EXPORT ---
if st.session_state.basket:
    st.divider()
    st.subheader("Current Estimate Breakdown")
    est_df = pd.DataFrame(st.session_state.basket)
    
    # Display table with formatted currency
    st.table(est_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    grand_total = est_df['Total'].sum()
    st.metric("Total Estimated Expenditure", f"Rs. {grand_total:,.2f}")
    
    col_ex, col_cl = st.columns([1, 4])
    
    # Excel Export
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        est_df.to_excel(writer, index=False, sheet_name='WorkEstimate')
    
    col_ex.download_button(
        label="📥 Download Excel",
        data=output.getvalue(),
        file_name="discom_estimate.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    if col_cl.button("🗑️ Clear All"):
        st.session_state.basket = []
        st.rerun()
