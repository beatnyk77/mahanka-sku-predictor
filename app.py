import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.processing import load_data, process_inventory, convert_df_to_csv
from fpdf import FPDF
import base64

# --- Page Config ---
st.set_page_config(
    page_title="Mahanka Dead Stock Oracle",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Styling ---
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6;
    }
    .main-header {
        font-size: 2.5rem;
        color: #FF4B4B;
    }
    .metric-card {
        padding: 20px;
        background-color: white;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.title("🔮 Mahanka Oracle")
    st.markdown("### Predict & Eliminate Dead Inventory")
    st.info("💡 **Freemium Mode**: Free analysis for up to 50 SKUs. Upgrade for unlimited processing!")
    
    st.markdown("---")
    st.write("Upload your Excel file with `Sales` and `Inventory` sheets.")
    st.caption("v1.0.0 | Made for Indian D2C")

# --- Utils for PDF ---
def create_pdf_report(df, total_risk_value, risk_count, sell_through):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    
    pdf.cell(200, 10, txt="Mahanka Dead Stock Report", ln=1, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Automated Analysis", ln=2, align='C')
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Executive Summary", ln=1)
    
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Total Dead Stock Risk Value: ${total_risk_value:,.2f}", ln=1)
    pdf.cell(0, 10, txt=f"High Risk SKUs Count: {risk_count}", ln=1)
    pdf.cell(0, 10, txt=f"Avg Sell-Through Rate: {sell_through:.1f}%", ln=1)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Top 5 High Risk SKUs", ln=1)
    pdf.set_font("Arial", size=10)
    
    top_risk = df.sort_values('Death_Risk_Score', ascending=False).head(5)
    for index, row in top_risk.iterrows():
        line = f"SKU: {row['SKU']} | Risk: {row['Death_Risk_Score']:.1f}% | Value: ${row['Stock_Value']:,.2f}"
        pdf.cell(0, 10, txt=line, ln=1)
        
    return pdf.output(dest='S').encode('latin-1')

# --- Main App ---
st.title("Mahanka Dead Stock Oracle 🔮")
st.markdown("### Upload your data to reveal hidden inventory risks")

uploaded_file = st.file_uploader("Upload Excel File (.xlsx)", type=['xlsx'])

use_sample = st.button("👉 Load Sample Data")

if uploaded_file or use_sample:
    with st.spinner('Processing your inventory data...'):
        if use_sample and not uploaded_file:
            # Load sample data path
            # Assuming the file is at specific path or we mock it
            # For this context, we'll try to read the file from the disk if it helps 
            # Or simplified: pass the path to load_data if it supports paths (it does since read_excel supports paths)
            import os
            sample_path = "samples/mahanka.xlsx"
            if os.path.exists(sample_path):
                sales_df, inventory_df, error = load_data(sample_path)
            else:
                sales_df, inventory_df, error = None, None, "Sample file not found."
                
        else:
            sales_df, inventory_df, error = load_data(uploaded_file)
        
        if error:
            st.error(f"Error reading file: {error}")
        else:
            # Validate columns
            req_sales = {'SKU', 'Date', 'Units_Sold', 'Revenue'}
            req_inv = {'SKU', 'Current_Stock', 'Cost_Price', 'Margin'}
            
            missing_sales = req_sales - set(sales_df.columns)
            missing_inv = req_inv - set(inventory_df.columns)
            
            if missing_sales or missing_inv:
                if missing_sales: st.error(f"Missing columns in 'Sales' sheet: {missing_sales}")
                if missing_inv: st.error(f"Missing columns in 'Inventory' sheet: {missing_inv}")
            else:
                # Process
                result_df = process_inventory(sales_df, inventory_df)
                
                # --- Metrics ---
                high_risk_df = result_df[result_df['Death_Risk_Score'] > 70]
                total_risk_value = high_risk_df['Stock_Value'].sum()
                risk_count = len(high_risk_df)
                avg_sell_through = result_df['Sell_Through_Rate'].mean() * 100
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Dead Stock Risk Value", f"${total_risk_value:,.2f}", delta_color="inverse")
                col2.metric("High Risk SKUs", f"{risk_count}", f"{risk_count/len(result_df)*100:.1f}% of total", delta_color="inverse")
                col3.metric("Avg Sell-Through", f"{avg_sell_through:.1f}%")
                
                st.divider()
                
                # --- Interactive Table ---
                st.subheader("Inventory Health Monitor")
                
                # Color coding for dataframe
                def color_risk(val):
                    color = 'green'
                    if val > 70: color = 'red'
                    elif val > 50: color = 'orange'
                    return f'background-color: {color}; color: white'
                
                display_cols = ['SKU', 'Current_Stock', 'Avg_Daily_Velocity', 'Days_of_Cover', 'Sell_Through_Rate', 'Stock_Value', 'Death_Risk_Score']
                display_df = result_df[display_cols].copy()
                display_df = display_df.sort_values('Death_Risk_Score', ascending=False)
                
                # Format for display
                st.dataframe(
                    display_df.style.map(color_risk, subset=['Death_Risk_Score'])
                    .format({
                        'Avg_Daily_Velocity': "{:.2f}",
                        'Days_of_Cover': "{:.1f}",
                        'Sell_Through_Rate': "{:.1%}",
                        'Stock_Value': "${:,.2f}",
                        'Death_Risk_Score': "{:.1f}"
                    }),
                    use_container_width=True
                )
                
                st.divider()
                
                # --- Visualizations ---
                c1, c2 = st.columns(2)
                
                with c1:
                    st.subheader("Margin vs Velocity Matrix")
                    fig_scatter = px.scatter(
                        result_df,
                        x="Avg_Daily_Velocity",
                        y="Margin",
                        size="Stock_Value",
                        color="Death_Risk_Score",
                        hover_name="SKU",
                        color_continuous_scale="RdYlGn_r",
                        title="Bubble Size = Stock Value"
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)
                    
                with c2:
                    st.subheader("Top 10 Risk SKUs Sell-Through")
                    # Top 10 risky items
                    top_risk_chart = result_df.sort_values('Death_Risk_Score', ascending=False).head(10)
                    fig_bar = px.bar(
                        top_risk_chart,
                        x="SKU",
                        y="Sell_Through_Rate",
                        color="Death_Risk_Score",
                        color_continuous_scale="RdYlGn_r",
                        title="Sell-Through Rate for Highest Risk Items"
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                # --- Downloads ---
                st.subheader("Export Analysis")
                d1, d2 = st.columns(2)
                
                csv = convert_df_to_csv(result_df)
                d1.download_button(
                    label="📥 Download Enriched CSV",
                    data=csv,
                    file_name='mahanka_dead_stock_analysis.csv',
                    mime='text/csv',
                )
                
                try:
                    pdf_bytes = create_pdf_report(result_df, total_risk_value, risk_count, avg_sell_through)
                    d2.download_button(
                        label="📄 Download PDF Report",
                        data=pdf_bytes,
                        file_name='mahanka_report.pdf',
                        mime='application/pdf'
                    )
                except Exception as e:
                    d2.error(f"PDF Generation failed: {e}")

else:
    st.info("👆 Upload a file to get started.")
    # Show sample format hint
    with st.expander("See expected file format"):
        st.write("Sheet1: **Sales** (SKU, Date, Units_Sold, Revenue)")
        st.write("Sheet2: **Inventory** (SKU, Current_Stock, Cost_Price, Margin)")
