import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF

st.set_page_config(page_title="MGVCL Estimate System", layout="wide")

MASTER_DATA_FILE = "master_rates_db.csv"

# --- REFINED PDF DESIGN (A4) ---
class MGVCL_Official_PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, 'MADHYA GUJARAT VIJ COMPANY LIMITED', 0, 1, 'C')
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, 'Detailed Work Expenditure Estimate (2024-25)', 0, 1, 'C')
        self.ln(5)
        self.line(10, 28, 200, 28)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

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
    st.header("Admin Settings")
    new_pdfs = st.file_uploader("Upload Cost Data PDFs", type="pdf", accept_multiple_files=True)
    if st.button("Sync Data"):
        if new_pdfs:
            master_df = process_pdfs(new_pdfs)
            master_df.to_csv(MASTER_DATA_FILE, index=False)
            st.success("Synced!")
            st.rerun()

# --- MAIN INTERFACE ---
st.title("⚡ MGVCL Smart Estimator")

with st.expander("📝 Project Identification", expanded=True):
    c1, c2, c3 = st.columns(3)
    scheme = c1.text_input("Name of Scheme")
    sub_div = c2.text_input("Sub Division", value="Karachiya/Savli")
    location = c3.text_input("Location / Village")

if 'basket' not in st.session_state:
    st.session_state.basket = []

# --- SEARCH & ADD SECTION ---
st.subheader("🔍 Search and Add Materials")
search_input = st.text_input("Type to search (e.g. '11KV AAAC' or '3PH CONNECTION')")

if search_input:
    keywords = search_input.lower().split()
    mask = master_df['Particulars'].apply(lambda x: all(k in str(x).lower() for k in keywords))
    results = master_df[mask]
    
    if not results.empty:
        # Show all matches in a select box
        selection = st.selectbox(f"Select from {len(results)} matches:", results['Particulars'].unique())
        item = master_df[master_df['Particulars'] == selection].iloc[0]
        
        with st.form("add_item_form", clear_on_submit=True):
            st.info(f"**Item Code:** {item['Group_Code']} | **Rate:** {item['Rate']:,.2f}")
            col_qty, col_btn = st.columns([2,1])
            qty = col_qty.number_input(f"Quantity ({item['Unit']})", min_value=0.0, step=0.01)
            if col_btn.form_submit_button("Add to Estimate"):
                st.session_state.basket.append({
                    "id": len(st.session_state.basket), # Unique ID for removal
                    "Code": str(item['Group_Code']),
                    "Description": item['Particulars'],
                    "Unit": item['Unit'],
                    "Rate": item['Rate'],
                    "Qty": qty,
                    "Total": qty * item['Rate']
                })
                st.rerun()
    else:
        st.error("No items match your search.")

# --- ESTIMATE DISPLAY & REMOVAL ---
if st.session_state.basket:
    st.divider()
    st.subheader("📋 Estimate Preview")
    
    # Display table with Remove button for each row
    for idx, row in enumerate(st.session_state.basket):
        c_desc, c_qty, c_total, c_del = st.columns([4, 1, 1, 1])
        c_desc.write(f"**{row['Description']}** (Code: {row['Code']})")
        c_qty.write(f"{row['Qty']} {row['Unit']}")
        c_total.write(f"₹{row['Total']:,.2f}")
        if c_del.button("❌ Remove", key=f"del_{idx}"):
            st.session_state.basket.pop(idx)
            st.rerun()

    total_amt = sum(item['Total'] for item in st.session_state.basket)
    st.subheader(f"Grand Total: ₹ {total_amt:,.2f}")

    # --- PDF GENERATOR (FIXED OVERLAP) ---
    def create_pdf(df_list, sch, sdiv, loc, g_total):
        pdf = MGVCL_Official_PDF()
        pdf.add_page()
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f" SCHEME: {sch.upper()}", 1, 1)
        pdf.cell(95, 8, f" SUB DIVISION: {sdiv.upper()}", 1, 0)
        pdf.cell(95, 8, f" LOCATION: {loc.upper()}", 1, 1)
        pdf.ln(5)

        # Header with specific widths
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(30, 10, "Group Code", 1, 0, 'C', True)
        pdf.cell(90, 10, "Description", 1, 0, 'C', True)
        pdf.cell(15, 10, "Unit", 1, 0, 'C', True)
        pdf.cell(20, 10, "Qty", 1, 0, 'C', True)
        pdf.cell(35, 10, "Total (Rs.)", 1, 1, 'C', True)
        
        pdf.set_font('Arial', '', 9)
        for row in df_list:
            # Step 1: Calculate height for the multi-cell description
            desc = str(row['Description'])
            # 50 characters is a safe width for a 90mm cell
            h = (len(desc) // 50 + 1) * 6
            if h < 10: h = 10
            
            # Step 2: Use multi_cell for description but keep track of position
            curr_y = pdf.get_y()
            pdf.multi_cell(90, 6 if h > 10 else 10, desc, 1)
            end_y = pdf.get_y()
            row_h = end_y - curr_y
            
            # Step 3: Draw the other columns at the same Y level with row_h height
            pdf.set_y(curr_y)
            pdf.cell(30, row_h, str(row['Code']), 1, 0, 'C')
            pdf.set_x(130) # Skip description width (30+90+10 padding)
            pdf.cell(15, row_h, str(row['Unit']), 1, 0, 'C')
            pdf.cell(20, row_h, str(row['Qty']), 1, 0, 'C')
            pdf.cell(35, row_h, f"{row['Total']:,.2f}", 1, 1, 'R')

        # Total Row
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(155, 12, "TOTAL MATERIAL COST ", 1, 0, 'R')
        pdf.cell(35, 12, f"{g_total:,.2f}", 1, 1, 'R')
        
        # Authorities
        pdf.ln(20)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(95, 10, "Prepared by: Junior Engineer", 0, 0, 'L')
        pdf.cell(95, 10, "Approved by: Deputy Engineer", 0, 1, 'R')
        
        return pdf.output()

    pdf_bytes = create_pdf(st.session_state.basket, scheme, sub_div, location, total_amt)
    st.download_button(
        label="🖨️ Direct Print Estimate (PDF)",
        data=bytes(pdf_bytes),
        file_name=f"Estimate_{location}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
    
    if st.button("🗑️ Clear All Items"):
        st.session_state.basket = []
        st.rerun()
