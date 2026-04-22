import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF
from difflib import get_close_matches

st.set_page_config(page_title="MGVCL Cost Estimator", layout="wide")

MASTER_DATA_FILE = "master_rates_db.csv"

# --- STYLING & PDF CLASS ---
class MGVCL_PDF(FPDF):
    def header(self):
        # Company Branding Header
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Madhya Gujarat Vij Company Ltd.', 0, 1, 'C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 7, 'Detailed Work Expenditure Estimate', 0, 1, 'C')
        self.ln(5)
        self.line(10, 32, 200, 32) # Top Border Line

    def footer(self):
        self.set_y(-30)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
        
    def draw_signature_block(self):
        self.set_y(-45)
        self.set_font('Arial', 'B', 10)
        self.cell(95, 10, 'Prepared by (D.E./Jr.E.)', 0, 0, 'L')
        self.cell(95, 10, 'Verified by (E.E.)', 0, 1, 'R')

# --- DATA ENGINE ---
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
                    group_code = next((c for c in clean_row if re.match(r'^\d{8,12}$', c.replace(" ", ""))), None)
                    if group_code:
                        try:
                            all_rows.append({
                                "Group_Code": group_code,
                                "Particulars": clean_row[2],
                                "Unit": clean_row[3],
                                "Rate": clean_rate(clean_row[4])
                            })
                        except: continue
    return pd.DataFrame(all_rows)

# --- LOAD DATA ---
if os.path.exists(MASTER_DATA_FILE):
    master_df = pd.read_csv(MASTER_DATA_FILE)
else:
    master_df = pd.DataFrame()

# --- SIDEBAR: ADMIN ---
with st.sidebar:
    st.image("https://www.mgvcl.com/images/logo.png", width=100) # Optional placeholder
    st.title("Admin Console")
    new_pdfs = st.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Sync Database"):
        if new_pdfs:
            master_df = process_pdfs(new_pdfs)
            master_df.to_csv(MASTER_DATA_FILE, index=False)
            st.success("Database Updated!")
            st.rerun()

# --- MAIN APP ---
st.title("⚡ MGVCL Work Estimator")

if master_df.empty:
    st.warning("Please upload Cost Data PDFs in the sidebar once to initialize.")
    st.stop()

# Project Details
with st.expander("📝 Project Identification Details", expanded=True):
    c1, c2, c3 = st.columns(3)
    division = c1.text_input("Division", value="Vadodara")
    sub_division = c2.text_input("Sub-Division", value="Karachiya/Savli")
    feeder_name = c3.text_input("Feeder/Location Name")

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- FUZZY SEARCH ---
st.subheader("🔍 Smart Item Search")
search_query = st.text_input("Search Particulars (e.g., '11KV Line' or 'TC Installation')")

if search_query:
    choices = master_df['Particulars'].unique().tolist()
    matches = get_close_matches(search_query, choices, n=10, cutoff=0.3)
    
    if matches:
        selection = st.selectbox("Select exact item from matched results:", matches)
        item = master_df[master_df['Particulars'] == selection].iloc[0]
        
        col_q, col_b = st.columns([1, 1])
        qty = col_q.number_input(f"Enter Qty ({item['Unit']})", min_value=0.0, step=0.1)
        
        if col_b.button("➕ Add to Estimate", use_container_width=True):
            st.session_state.basket.append({
                "Code": str(item['Group_Code']),
                "Description": item['Particulars'],
                "Unit": item['Unit'],
                "Rate": item['Rate'],
                "Qty": qty,
                "Total": qty * item['Rate']
            })
            st.success("Item Added!")
            st.rerun()
    else:
        st.error("No similar items found. Try a different keyword.")

# --- ESTIMATE VIEW & EXPORT ---
if st.session_state.basket:
    st.divider()
    est_df = pd.DataFrame(st.session_state.basket)
    st.subheader(f"Current Breakdown: {feeder_name}")
    st.table(est_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    mat_total = est_df['Total'].sum()
    st.sidebar.metric("Material Cost", f"₹ {mat_total:,.2f}")

    def generate_pdf(df, div, sub, feeder, total):
        pdf = MGVCL_PDF()
        pdf.add_page()
        
        # Project Info Section
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(100, 7, f"Division: {div}", 0, 0)
        pdf.cell(90, 7, f"Sub-Division: {sub}", 0, 1, 'R')
        pdf.cell(0, 7, f"Feeder/Work: {feeder}", 0, 1)
        pdf.ln(5)

        # Table Header Styling
        pdf.set_fill_color(220, 230, 241)
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(25, 10, "Group Code", 1, 0, 'C', True)
        pdf.cell(90, 10, "Particulars", 1, 0, 'C', True)
        pdf.cell(20, 10, "Qty", 1, 0, 'C', True)
        pdf.cell(25, 10, "Rate (Rs)", 1, 0, 'C', True)
        pdf.cell(30, 10, "Total (Rs)", 1, 1, 'C', True)
        
        pdf.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            y_start = pdf.get_y()
            pdf.multi_cell(90, 8, str(row['Description']), 1)
            y_end = pdf.get_y()
            h = y_end - y_start
            
            pdf.set_y(y_start)
            pdf.cell(25, h, str(row['Code']), 1, 0, 'C')
            pdf.set_x(125)
            pdf.cell(20, h, str(row['Qty']), 1, 0, 'C')
            pdf.cell(25, h, f"{row['Rate']:,.2f}", 1, 0, 'R')
            pdf.cell(30, h, f"{row['Total']:,.2f}", 1, 1, 'R')
            
        # Summary
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(160, 10, "GRAND TOTAL MATERIAL COST", 1, 0, 'R')
        pdf.cell(30, 10, f"{total:,.2f}", 1, 1, 'R')
        
        pdf.draw_signature_block()
        return pdf.output()

    if st.button("🖨️ Generate Professional A4 Estimate"):
        pdf_out = generate_pdf(est_df, division, sub_division, feeder_name, mat_total)
        st.download_button("📥 Download PDF", data=bytes(pdf_out), file_name=f"Estimate_{feeder_name}.pdf", mime="application/pdf")

    if st.button("🗑️ Clear Estimate"):
        st.session_state.basket = []
        st.rerun()
