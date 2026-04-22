import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF

st.set_page_config(page_title="MGVCL Cost Estimator", layout="wide")

MASTER_DATA_FILE = "master_rates_db.csv"

# --- PROFESSIONAL PDF DESIGN ---
class MGVCL_Report(FPDF):
    def header(self):
        # Company Header
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Madhya Gujarat Vij Company Ltd.', 0, 1, 'C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 7, 'Work Expenditure Estimate', 0, 1, 'C')
        self.ln(5)
        self.line(10, 32, 200, 32) # Header underline

    def footer(self):
        self.set_y(-25)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

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
                            # Positions based on RE Cost Data Index
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
    st.title("Admin Panel")
    new_pdfs = st.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Sync Database"):
        if new_pdfs:
            master_df = process_pdfs(new_pdfs)
            master_df.to_csv(MASTER_DATA_FILE, index=False)
            st.success("Database Saved!")
            st.rerun()

# --- MAIN APP ---
st.title("⚡ MGVCL Estimate Generator")

if master_df.empty:
    st.warning("Please upload Cost Data PDFs in the sidebar once to start.")
    st.stop()

# --- PROJECT DETAILS ---
with st.expander("📝 Project & Location Information", expanded=True):
    c1, c2 = st.columns(2)
    scheme_name = c1.text_input("Name of Scheme (e.g. RDSS, SCADA, RE)")
    sub_division = c2.text_input("Sub Division", value="Karachiya/Savli")
    
    c3, c4 = st.columns(2)
    location_name = c3.text_input("Location / Village")
    work_description = c4.text_input("General Work Description")

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- IMPROVED TOKENIZED SEARCH ---
st.subheader("🔍 Search Items")
search_input = st.text_input("Enter keywords (e.g., '11KV AAAC 34')")

if search_input:
    # Split search into words
    keywords = search_input.lower().split()
    
    # Logic: Item must contain ALL keywords entered (regardless of order)
    mask = master_df['Particulars'].apply(lambda x: all(k in str(x).lower() for k in keywords))
    filtered_results = master_df[mask]
    
    if not filtered_results.empty:
        selection = st.selectbox(f"Found {len(filtered_results)} items:", filtered_results['Particulars'].unique())
        item = master_df[master_df['Particulars'] == selection].iloc[0]
        
        col_qty, col_add = st.columns([1, 1])
        qty = col_qty.number_input(f"Enter Quantity ({item['Unit']})", min_value=0.0, step=0.01)
        
        if col_add.button("➕ Add to Estimate List", use_container_width=True):
            st.session_state.basket.append({
                "Code": str(item['Group_Code']),
                "Description": item['Particulars'],
                "Unit": item['Unit'],
                "Rate": item['Rate'],
                "Qty": qty,
                "Total": qty * item['Rate']
            })
            st.success("Added to list.")
            st.rerun()
    else:
        st.error("No items found. Try using simpler keywords.")

# --- DISPLAY ESTIMATE ---
if st.session_state.basket:
    st.divider()
    est_df = pd.DataFrame(st.session_state.basket)
    st.table(est_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    mat_total = est_df['Total'].sum()
    st.metric("Total Material Cost", f"Rs. {mat_total:,.2f}")

    # --- PDF GENERATOR ---
    def generate_professional_pdf(df, scheme, subdiv, loc, total):
        pdf = MGVCL_Report()
        pdf.add_page()
        
        # Project Info Header Box
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f" SCHEME: {scheme.upper()}", 1, 1, 'L', True)
        
        pdf.set_font('Arial', '', 10)
        pdf.cell(95, 8, f" Sub Division: {subdiv}", 1, 0, 'L')
        pdf.cell(95, 8, f" Location: {loc}", 1, 1, 'L')
        pdf.ln(5)

        # Table Headers
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(25, 10, "Group Code", 1, 0, 'C', True)
        pdf.cell(95, 10, "Particulars", 1, 0, 'C', True)
        pdf.cell(15, 10, "Unit", 1, 0, 'C', True)
        pdf.cell(20, 10, "Qty", 1, 0, 'C', True)
        pdf.cell(35, 10, "Total (Rs.)", 1, 1, 'C', True)
        
        pdf.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            y_start = pdf.get_y()
            pdf.multi_cell(95, 7, str(row['Description']), 1)
            y_end = pdf.get_y()
            h = y_end - y_start
            
            pdf.set_y(y_start)
            pdf.cell(25, h, str(row['Code']), 1, 0, 'C')
            pdf.set_x(130) # Move past particulars
            pdf.cell(15, h, str(row['Unit']), 1, 0, 'C')
            pdf.cell(20, h, str(row['Qty']), 1, 0, 'C')
            pdf.cell(35, h, f"{row['Total']:,.2f}", 1, 1, 'R')
            
        # Grand Total Row
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(155, 12, "GRAND TOTAL MATERIAL EXPENDITURE (Rs.)", 1, 0, 'R')
        pdf.cell(35, 12, f"{total:,.2f}", 1, 1, 'R')
        
        # Signatures
        pdf.ln(20)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(95, 10, "Prepared by (D.E./Jr. E.)", 0, 0, 'L')
        pdf.cell(95, 10, "Verified by (Executive Engineer)", 0, 1, 'R')

        return pdf.output()

    c1, c2 = st.columns(2)
    if c1.button("🖨️ Prepare A4 PDF Estimate"):
        pdf_bytes = generate_professional_pdf(est_df, scheme_name, sub_division, location_name, mat_total)
        st.download_button(
            label="📥 Download A4 PDF",
            data=bytes(pdf_bytes),
            file_name=f"Estimate_{location_name}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    if c2.button("🗑️ Reset All", use_container_width=True):
        st.session_state.basket = []
        st.rerun()
