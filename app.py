import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF

st.set_page_config(page_title="DISCOM Estimator", layout="wide")

# --- DATA PERSISTENCE LOGIC ---
SAVE_FILE = "master_rates.csv"

def clean_rate(val):
    if not val: return 0.0
    cleaned = re.sub(r'[^\d.]', '', str(val))
    try: return float(cleaned)
    except: return 0.0

def process_pdfs(files):
    all_rows = []
    for uploaded_file in files:
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table: continue
                for row in table:
                    clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                    # Identify Group Code (10 digits)
                    group_code = next((c for c in clean_row if re.match(r'^\d{8,12}$', c.replace(" ", ""))), None)
                    if group_code:
                        try:
                            # Index mapping based on your sample PDF
                            all_rows.append({
                                "Group_Code": group_code,
                                "Particulars": clean_row[2],
                                "Unit": clean_row[3],
                                "Rate": clean_rate(clean_row[4])
                            })
                        except: continue
    return pd.DataFrame(all_rows)

# --- PDF GENERATION (A4) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'DISCOM WORK EXPENDITURE ESTIMATE', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, 'Estimate for Distribution Network Works', 0, 1, 'C')
        self.ln(10)

# --- LOAD DATA ---
if os.path.exists(SAVE_FILE):
    master_df = pd.read_csv(SAVE_FILE)
else:
    master_df = pd.DataFrame()

# --- SIDEBAR: ONE-TIME UPLOAD ---
with st.sidebar:
    st.header("Admin: Data Management")
    uploaded_files = st.file_uploader("Upload PDFs to Update Master Database", type="pdf", accept_multiple_files=True)
    if st.button("Sync & Save to Server"):
        if uploaded_files:
            new_data = process_pdfs(uploaded_files)
            new_data.to_csv(SAVE_FILE, index=False)
            st.success("Database Updated! You don't need to upload again.")
            st.rerun()

# --- MAIN APP ---
st.title("⚡ MGVCL Work Estimator")

if master_df.empty:
    st.warning("No data found. Please upload your Cost Data PDFs in the sidebar once to begin.")
    st.stop()

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- SEARCHABLE INPUT ---
st.subheader("Select Items")
# Using a text search to filter the dropdown list
search_term = st.text_input("Type to search (e.g. 'Transformer', '11 KV')")
filtered_df = master_df[master_df['Particulars'].str.contains(search_term, case=False, na=False)]

if not filtered_df.empty:
    selected_item = st.selectbox("Choose Item", filtered_df['Particulars'].unique())
    item_details = master_df[master_df['Particulars'] == selected_item].iloc[0]
    
    col1, col2 = st.columns([2, 1])
    qty = col1.number_input(f"Quantity ({item_details['Unit']})", min_value=0.0, step=0.01)
    
    if col2.button("➕ Add to Estimate"):
        st.session_state.basket.append({
            "Code": str(item_details['Group_Code']),
            "Particulars": item_details['Particulars'],
            "Unit": item_details['Unit'],
            "Rate": item_details['Rate'],
            "Qty": qty,
            "Total": qty * item_details['Rate']
        })
        st.rerun()

# --- DISPLAY & PDF ---
if st.session_state.basket:
    st.divider()
    res_df = pd.DataFrame(st.session_state.basket)
    st.table(res_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    grand_total = res_df['Total'].sum()
    st.metric("Grand Total Expenditure", f"Rs. {grand_total:,.2f}")

    # Generate PDF Function
    def generate_pdf(df, total):
        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 10)
        # Headers
        pdf.cell(30, 10, "Code", 1)
        pdf.cell(85, 10, "Particulars", 1)
        pdf.cell(20, 10, "Qty", 1)
        pdf.cell(25, 10, "Rate", 1)
        pdf.cell(30, 10, "Total", 1)
        pdf.ln()
        
        pdf.set_font("Arial", '', 9)
        for _, row in df.iterrows():
            # Handle long text in particulars
            start_y = pdf.get_y()
            pdf.multi_cell(85, 10, str(row['Particulars']), 1)
            end_y = pdf.get_y()
            h = end_y - start_y
            
            pdf.set_y(start_y)
            pdf.cell(30, h, str(row['Code']), 1)
            pdf.set_x(125) # Move past particulars
            pdf.cell(20, h, str(row['Qty']), 1)
            pdf.cell(25, h, f"{row['Rate']:,.2f}", 1)
            pdf.cell(30, h, f"{row['Total']:,.2f}", 1)
            pdf.ln(h)
            
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(160, 10, "GRAND TOTAL", 1, 0, 'R')
        pdf.cell(30, 10, f"{total:,.2f}", 1, 1, 'R')
        return pdf.output()

    c1, c2 = st.columns(2)
    
    pdf_data = generate_pdf(res_df, grand_total)
    c1.download_button(
        label="📄 Print Estimate (PDF)",
        data=bytes(pdf_data),
        file_name="work_estimate.pdf",
        mime="application/pdf"
    )
    
    if c2.button("🗑️ Reset Estimate"):
        st.session_state.basket = []
        st.rerun()
