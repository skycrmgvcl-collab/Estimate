import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF

st.set_page_config(page_title="MGVCL Estimate Tool", layout="wide")

MASTER_DATA_FILE = "master_rates_db.csv"

# --- REFINED PDF CLASS ---
class MGVCL_Official_PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, 'MADHYA GUJARAT VIJ COMPANY LIMITED', 0, 1, 'C')
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, 'Detailed Work Expenditure Estimate', 0, 1, 'C')
        self.ln(5)
        self.line(10, 28, 200, 28)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

# --- DATA PROCESSING ---
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

if os.path.exists(MASTER_DATA_FILE):
    master_df = pd.read_csv(MASTER_DATA_FILE)
else:
    master_df = pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.header("Database Update")
    new_pdfs = st.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Sync Data"):
        if new_pdfs:
            master_df = process_pdfs(new_pdfs)
            master_df.to_csv(MASTER_DATA_FILE, index=False)
            st.success("Synced!")
            st.rerun()

# --- MAIN INTERFACE ---
st.title("⚡ MGVCL Estimate System")

if master_df.empty:
    st.warning("Please upload PDFs in the sidebar once to initialize.")
    st.stop()

# Project Info
with st.expander("📝 Project Details", expanded=True):
    c1, c2, c3 = st.columns(3)
    scheme = c1.text_input("Name of Scheme")
    sub_div = c2.text_input("Sub Division", value="Karachiya/Savli")
    location = c3.text_input("Location/Village")

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- MULTI-WORD SMART SEARCH ---
st.subheader("🔍 Instant Item Search")
search_input = st.text_input("Search keywords (e.g., '11KV AAAC' or '3PH 5HP')")

if search_input:
    # Break input into separate words
    keywords = search_input.lower().split()
    # Find items that contain EVERY word in the search input
    mask = master_df['Particulars'].apply(lambda x: all(k in str(x).lower() for k in keywords))
    results = master_df[mask]
    
    if not results.empty:
        selection = st.selectbox(f"Found {len(results)} items:", results['Particulars'].unique())
        item = master_df[master_df['Particulars'] == selection].iloc[0]
        
        col_q, col_b = st.columns([1, 1])
        qty = col_q.number_input(f"Qty for {item['Unit']}", min_value=0.0, step=0.01)
        
        if col_b.button("➕ Add Item", use_container_width=True):
            st.session_state.basket.append({
                "Code": str(item['Group_Code']),
                "Description": item['Particulars'],
                "Unit": item['Unit'],
                "Rate": item['Rate'],
                "Qty": qty,
                "Total": qty * item['Rate']
            })
            st.rerun()
    else:
        st.error("No items match those keywords.")

# --- ESTIMATE & PRINT ---
if st.session_state.basket:
    st.divider()
    est_df = pd.DataFrame(st.session_state.basket)
    st.table(est_df.style.format({"Rate": "{:,.2f}", "Total": "{:,.2f}"}))
    
    total_amt = est_df['Total'].sum()
    st.subheader(f"Grand Total: Rs. {total_amt:,.2f}")

    # PDF Logic with "Direct Print" feel
    def create_direct_print_pdf(df, sch, sdiv, loc, grand_total):
        pdf = MGVCL_Official_PDF()
        pdf.add_page()
        
        # Header Box
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f" Scheme: {sch.upper()}", 1, 1)
        pdf.cell(95, 8, f" Sub Division: {sdiv}", 1, 0)
        pdf.cell(95, 8, f" Location: {loc}", 1, 1)
        pdf.ln(5)

        # Headers - Fixed widths to prevent overlap
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(25, 10, "Group Code", 1, 0, 'C', True)
        pdf.cell(90, 10, "Particulars / Description", 1, 0, 'C', True)
        pdf.cell(15, 10, "Unit", 1, 0, 'C', True)
        pdf.cell(20, 10, "Qty", 1, 0, 'C', True)
        pdf.cell(40, 10, "Amount (Rs.)", 1, 1, 'C', True)
        
        pdf.set_font('Arial', '', 9)
        for _, row in df.iterrows():
            # Calculate height for description to prevent overlap
            desc = str(row['Description'])
            num_lines = (len(desc) // 50) + 1 # Rough estimate for height
            h = num_lines * 6 if num_lines > 1 else 10
            
            y_curr = pdf.get_y()
            pdf.multi_cell(90, 6 if num_lines > 1 else 10, desc, 1) # Description
            y_end = pdf.get_y()
            row_h = y_end - y_curr
            
            pdf.set_y(y_curr)
            pdf.cell(25, row_h, str(row['Code']), 1, 0, 'C') # Code
            pdf.set_x(125) # Skip Particulars
            pdf.cell(15, row_h, str(row['Unit']), 1, 0, 'C') # Unit
            pdf.cell(20, row_h, str(row['Qty']), 1, 0, 'C') # Qty
            pdf.cell(40, row_h, f"{row['Total']:,.2f}", 1, 1, 'R') # Total

        # Total Row
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(150, 12, "TOTAL EXPENDITURE ", 1, 0, 'R')
        pdf.cell(40, 12, f"{grand_total:,.2f}", 1, 1, 'R')
        
        # Official Signatures
        pdf.ln(25)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(95, 10, "Prepared by: Junior Engineer", 0, 0, 'L')
        pdf.cell(95, 10, "Approved by: Deputy Engineer", 0, 1, 'R')
        
        return pdf.output()

    c1, c2 = st.columns(2)
    # Combined step: Clicking this provides the PDF immediately
    pdf_output = create_direct_print_pdf(est_df, scheme, sub_div, location, total_amt)
    c1.download_button(
        label="🖨️ Direct Print Estimate (PDF)",
        data=bytes(pdf_output),
        file_name=f"Estimate_{location}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
    
    if c2.button("🗑️ Clear & Start New", use_container_width=True):
        st.session_state.basket = []
        st.rerun()
