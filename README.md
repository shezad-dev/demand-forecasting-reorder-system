# Demand Forecasting & Reorder Alert System

Automated demand forecasting tool that analyzes sales history, predicts future demand, and flags items that need reordering.

## Features
- Reads sales history and inventory data from Google Sheets
- Calculates average daily demand per SKU
- Forecasts demand for the next 7 days
- Flags items below reorder point or at risk of stockout
- Generates CSV report with reorder recommendations
- Sends email alert with report attached

## How It Works
1. Google Sheet with 2 tabs: Sales_History and Inventory_Current
2. Python script reads both tabs
3. Calculates average daily demand from sales history
4. Forecasts next 7 days demand
5. Compares to current inventory and reorder point
6. Generates CSV report with recommendations
7. Emails report to configured address

## Configuration
```python
SHEET_ID = "your_sheet_id_here"
GMAIL_USER = "your_email@gmail.com"
GMAIL_PASSWORD = "your_app_password"
ALERT_EMAIL = "where_to_send@email.com"
