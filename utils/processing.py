import pandas as pd
import numpy as np
from scipy.special import expit
import io

def load_data(file):
    """
    Reads the uploaded Excel file and returns the Sales and Inventory dataframes.
    Attempts to auto-detect header row.
    """
    try:
        # Helper to find header
        def read_sheet(f, sheet):
            # Try header=0
            df = pd.read_excel(f, sheet_name=sheet, header=0)
            required_cols = {'SKU'} # SKU is common to both
            if required_cols.issubset(df.columns):
                return df
            
            # Try header=1
            df = pd.read_excel(f, sheet_name=sheet, header=1)
            if required_cols.issubset(df.columns):
                return df
                
            # If neither works, return original (will fail validation later)
            return pd.read_excel(f, sheet_name=sheet, header=0)

        sales_df = read_sheet(file, "Sales")
        inventory_df = read_sheet(file, "Inventory")
        
        return sales_df, inventory_df, None
    except Exception as e:
        return None, None, str(e)

def process_inventory(sales_df, inventory_df):
    """
    Core logic to calculate metrics and death risk.
    """
    # 1. Date Parsing
    if 'Date' in sales_df.columns:
        sales_df['Date'] = pd.to_datetime(sales_df['Date'], errors='coerce')
    
    # 2. Velocity Calculation
    # Group via SKU
    sales_grouped = sales_df.groupby('SKU', as_index=False).agg({
        'Units_Sold': 'sum',
        'Revenue': 'sum',
        'Date': ['min', 'max']
    })
    
    # Flatten multi-index columns
    sales_grouped.columns = ['SKU', 'Total_Units_Sold', 'Total_Revenue', 'Min_Date', 'Max_Date']
    
    # Calculate period days
    sales_grouped['Period_Days'] = (sales_grouped['Max_Date'] - sales_grouped['Min_Date']).dt.days + 1
    # Avoid division by zero or negative days (fallback to 1 if weird data)
    sales_grouped['Period_Days'] = sales_grouped['Period_Days'].apply(lambda x: x if x > 0 else 1)
    
    # Avg Daily Velocity
    sales_grouped['Avg_Daily_Velocity'] = sales_grouped['Total_Units_Sold'] / sales_grouped['Period_Days']
    
    # 3. Merge with Inventory
    # Ensure SKUs are strings for merging
    sales_grouped['SKU'] = sales_grouped['SKU'].astype(str)
    inventory_df['SKU'] = inventory_df['SKU'].astype(str)
    
    merged_df = pd.merge(inventory_df, sales_grouped, on='SKU', how='left')
    
    # Fill NaN for sales data (items with no sales)
    merged_df['Total_Units_Sold'] = merged_df['Total_Units_Sold'].fillna(0)
    merged_df['Total_Revenue'] = merged_df['Total_Revenue'].fillna(0)
    merged_df['Avg_Daily_Velocity'] = merged_df['Avg_Daily_Velocity'].fillna(0)
    
    # 4. Derived Metrics
    # Days of Cover
    # Avoid div/0 by replacing 0 velocity with 0.001
    safe_velocity = merged_df['Avg_Daily_Velocity'].replace(0, 0.001)
    merged_df['Days_of_Cover'] = merged_df['Current_Stock'] / safe_velocity
    
    # Sell-Through Rate
    total_stock_flow = merged_df['Total_Units_Sold'] + merged_df['Current_Stock']
    # Avoid div/0
    merged_df['Sell_Through_Rate'] = merged_df.apply(
        lambda row: row['Total_Units_Sold'] / (row['Total_Units_Sold'] + row['Current_Stock']) 
        if (row['Total_Units_Sold'] + row['Current_Stock']) > 0 else 0, 
        axis=1
    )
    
    # Financials
    # Selling Price = Cost / (1 - Margin) where margin is 0-1 (e.g. 0.30)
    # Handle cases where Margin might be 1 (infinite price) -> clip or handle? 
    # Assuming valid margins < 1.
    merged_df['Selling_Price'] = merged_df['Cost_Price'] / (1 - merged_df['Margin'])
    merged_df['Stock_Value'] = merged_df['Current_Stock'] * merged_df['Selling_Price']
    
    # 5. Death Risk Algorithm
    # Base = sigmoid((Days_Cover - 60)/30) * 100
    merged_df['Death_Risk_Base'] = expit((merged_df['Days_of_Cover'] - 60) / 30) * 100
    
    # Penalty: +30 if Avg_daily_velocity < 0.5
    merged_df['Risk_Penalty'] = np.where(merged_df['Avg_Daily_Velocity'] < 0.5, 30, 0)
    
    merged_df['Death_Risk_Score'] = merged_df['Death_Risk_Base'] + merged_df['Risk_Penalty']
    
    # Clip to 0-100
    merged_df['Death_Risk_Score'] = merged_df['Death_Risk_Score'].clip(0, 100)
    
    return merged_df

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')
