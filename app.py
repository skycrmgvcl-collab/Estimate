import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF

st.set_page_config(page_title="MGVCL Estimate System", layout="wide")

MASTER_DATA_FILE = "master_rates_db.csv"

# --- PDF DESIGN (A4) ---
class MGVCL_Official_PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, 'MADHYA GUJARAT VIJ COMPANY LIMITED', 0, 1, 'C')
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, 'Work Expenditure Estimate (2024-25)', 0, 1, 'C')
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

# --- SIDEBAR DATABASE ---
with st.sidebar:
    st.header("Admin Settings")
    new_pdfs = st.file_uploader("Sync New Cost Data PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Update Database"):
        if new_pdfs:
            master_df = process_pdfs(new_pdfs)
            master_df.to_csv(MASTER_DATA_FILE, index=False)
            st.success("Database Updated!")
            st.rerun()

# --- PROJECT HEADER ---
st.title("⚡ MGVCL Smart Estimator")

with st.expander("📝 Step 1: Project Details", expanded=True):
    c1, c2 = st.columns(2)
    scheme = c1.text_input("Name of Scheme (RDSS / RE / etc.)")
    sub_div = c2.text_input("Sub Division", value="Karachiya/Savli")
    
    c3, c4 = st.columns(2)
    location = c3.text_input("Location / Village")
    work_title = c4.text_input("Work Name")

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- STEP 2: SEARCH & ADD ---
st.subheader("🔍 Step 2: Search & Add Materials")
search_input = st.text_input("Type words to filter (e.g. '11KV AAAC' or '3PH CONNECTION')")

if search_input:
    # Logic: Match all words in any order
    keywords = search_input.lower().split()
    mask = master_df['Particulars'].apply(lambda x: all(k in str(x).lower() for k in keywords))
    results = master_df[mask]
    
    if not results.empty:
        # Show results in a clean table or selection box
        selected_desc = st.selectbox(f"Matches Found ({len(results)}):", results['Particulars'].unique())
        item = master_df[master_df['Particulars'] == selected_desc].iloc[0]
        
        # Immediate Quantity Request
        with st.form("add_form", clear_on_submit=True):
            col_info, col_qty, col_btn = st.columns([2,1,1])
            col_info.info(f"**Code:** {item['Group_Code']} | **Rate:** {item['Rate']:,.2f}")
            qty = col_qty.number_input(f"Enter Quantity ({item['Unit']})", min_value=0.0, step=0.01)
            if col_btn.form_submit_button("Add to Estimate"):
                st.session_state.basket.append({
                    "Code": str(item['Group_Code']),
                    "Description": item['Particulars'],
                    "Unit": item['Unit'],
                    "Rate": item['Rate'],
                    "Qty": qty,
                    "Total": qty * item['Rate']
                })
                st.success(f"Added {qty} {item['Unit']}")
                st.rerun()
    else:
        st.error("No items found matching those keywords.")

# --- STEP 3: PREVIEW & PRINT ---
if st.session_state.basket:
    st.divider()
    st.subheader("📋 Step 3: Preview & Print")
    est_df = pd.DataFrame(st.session_state.basket)
    st.dataframe(est_df[["Code", "Description", "Unit", "Qty", "Total"]], use_container_width=True)
    
    total_amt = est_df['Total'].sum()
    st.subheader(f"Total Estimate: ₹ {total_amt:,.2f}")

    # Generate PDF Function
    def generate_pdf(df, sch, sdiv, loc, g_total):
        pdf = MGVCL_Official_PDF()
        pdf.add_page()
        
        # Project Info Box
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f" SCHEME: {sch.upper()}", 1, 1)
        pdf.cell(95, 8, f" SUB DIVISION: {sdiv.upper()}", 1, 0)
        pdf.cell(95, 8, f" LOCATION: {loc.upper()}", 1, 1)
        pdf.ln(4)

        # Headers
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(25, 10, "Group Code", 1, 0, 'C', True)
        pdf.cell(95, 10, "Particulars / Description", 1, 0, 'C', True)
        pdf.cell(15, 10, "Unit", 1, 0, 'C', True)
        pdf.cell(15, 10, "Qty", 1, 0, 'C', True)
        pdf.cell(40, 10, "Amount (Rs.)", 1, 1, 'C', True)
        
        pdf.set_font('Arial', '', 9)
        for _, row in df.iterrows():
            desc = str(row['Description'])
            # Dynamic height calculation to prevent column overlap
            # 55 characters width for description box
            h = (len(desc) // 55 + 1) * 6
            if h < 10: h = 10
            
            curr_y = pdf.get_y()
            pdf.multi_cell(95, 6 if h > 10 else 10, desc, 1)
            end_y = pdf.get_y()
            row_h = end_y - curr_y
            
            pdf.set_y(curr_y)
            pdf.cell(25, row_h, str(row['Code']), 1, 0, 'C')
            pdf.set_x(130) # Skip Multi-cell area
            pdf.cell(15, row_h, str(row['Unit']), 1, 0, 'C')
            pdf.cell(15, row_h, str(row['Qty']), 1, 0, 'C')
            pdf.cell(40, row_h, f"{row['Total']:,.2f}", 1, 1, 'R')

        # Summary
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(150, 12, "GRAND TOTAL ESTIMATE (Rs.) ", 1, 0, 'R')
        pdf.cell(40, 12, f"{g_total:,.2f}", 1, 1, 'R')
        
        # Official Authorities
        pdf.ln(20)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(95, 10, "Prepared by: Junior Engineer", 0, 0, 'L')
        pdf.cell(95, 10, "Approved by: Deputy Engineer", 0, 1, 'R')
        
        return pdf.output()

    c1, c2 = st.columns(2)
    # Direct Download
    pdf_out = generate_pdf(est_df, scheme, sub_div, location, total_amt)
    c1.download_button(
        label="🖨️ Direct Print Estimate (PDF)",
        data=bytes(pdf_out),
        file_name=f"MGVCL_Estimate_{location}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
    
    if c2.button("🗑️ Reset Everything", use_container_width=True):
        st.session_state.basket = []
        st.rerun()
