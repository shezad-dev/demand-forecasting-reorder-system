#!/usr/bin/env python3
"""
Demand Forecasting & Reorder Alert System
Predicts stockouts and recommends purchase orders
Sends 1 CSV report via email then stops
"""

import urllib.request
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import os
import csv
import io
from collections import defaultdict

# ============ CONFIGURATION ============

# Your Google Sheet ID
SHEET_ID = "18brv69VGPALzF7aTSsMBvIludjOlz-fk0mVmco_w6rU"

# Load credentials from config.py
try:
    from config import GMAIL_USER, GMAIL_PASSWORD, ALERT_EMAIL
except ImportError:
    # Fallback to environment variables
    GMAIL_USER = os.environ.get('GMAIL_USER')
    GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD')
    ALERT_EMAIL = os.environ.get('ALERT_EMAIL')

if not all([GMAIL_USER, GMAIL_PASSWORD, ALERT_EMAIL]):
    print("❌ ERROR: Missing credentials!")
    print("\nCreate config.py with:")
    print("GMAIL_USER = 'your_email@gmail.com'")
    print("GMAIL_PASSWORD = 'your_app_password'")
    print("ALERT_EMAIL = 'recipient@email.com'")
    print("\nOr set environment variables:")
    print("GMAIL_USER, GMAIL_PASSWORD, ALERT_EMAIL")
    exit(1)

# ============ READ GOOGLE SHEET ============

def read_sheet(sheet_name):
    """Read a public Google Sheet tab as CSV"""
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req)
        data = response.read().decode('utf-8')
        
        lines = data.strip().split('\n')
        result = []
        for line in lines:
            parts = []
            current = ''
            in_quotes = False
            for char in line:
                if char == '"' and not in_quotes:
                    in_quotes = True
                elif char == '"' and in_quotes:
                    in_quotes = False
                elif char == ',' and not in_quotes:
                    parts.append(current.strip())
                    current = ''
                else:
                    current += char
            parts.append(current.strip())
            result.append(parts)
        return result
    except Exception as e:
        print(f"❌ Error reading {sheet_name}: {e}")
        return None

# ============ FORECASTING LOGIC ============

def calculate_daily_demand(sales_data):
    """Calculate average daily demand per SKU"""
    demand = defaultdict(list)
    
    for row in sales_data:
        if len(row) >= 4:
            sku = row[1]
            try:
                qty = float(row[3]) if row[3] else 0
                demand[sku].append(qty)
            except:
                pass
    
    avg_demand = {}
    for sku, values in demand.items():
        if values:
            avg_demand[sku] = sum(values) / len(values)
        else:
            avg_demand[sku] = 0
    
    return avg_demand

def forecast_demand(avg_demand, days=7):
    """Forecast demand for next N days"""
    forecast = {}
    for sku, avg in avg_demand.items():
        forecast[sku] = avg * days
    return forecast

def calculate_reorder(forecast, inventory_data, avg_demand):
    """Calculate reorder recommendations"""
    recommendations = []
    
    for sku, forecast_qty in forecast.items():
        # Find inventory data
        current_qty = 0
        reorder_point = 0
        lead_time = 5
        for row in inventory_data:
            if len(row) >= 3 and row[0] == sku:
                try:
                    current_qty = float(row[2]) if row[2] else 0
                    reorder_point = float(row[3]) if len(row) > 3 and row[3] else 0
                    lead_time = float(row[4]) if len(row) > 4 and row[4] else 5
                except:
                    pass
                break
        
        # Calculate days until stockout
        daily_avg = avg_demand.get(sku, 0)
        if daily_avg > 0:
            days_until_stockout = current_qty / daily_avg
        else:
            days_until_stockout = 999
        
        # Safety stock factor (1.5x forecast)
        safety_stock = 1.5
        
        # Reorder decision
        if current_qty <= reorder_point or days_until_stockout <= lead_time:
            order_qty = int(forecast_qty * safety_stock - current_qty)
            if order_qty < 0:
                order_qty = 0
            status = "🔴 ORDER NOW"
        else:
            order_qty = 0
            status = "✅ OK"
        
        recommendations.append({
            'sku': sku,
            'current_qty': current_qty,
            'reorder_point': reorder_point,
            'lead_time': lead_time,
            'avg_demand': round(daily_avg, 1),
            'forecast_7_days': round(forecast_qty, 0),
            'days_until_stockout': round(days_until_stockout, 1),
            'order_qty': order_qty,
            'status': status
        })
    
    return recommendations

# ============ GENERATE CSV ============

def generate_csv(recommendations):
    """Generate CSV report as string"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['DEMAND FORECAST & REORDER REPORT'])
    writer.writerow([f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
    writer.writerow([])
    
    writer.writerow(['RECOMMENDATIONS'])
    writer.writerow([
        'SKU', 'Current_Qty', 'Reorder_Point', 'Lead_Time_Days',
        'Avg_Daily_Demand', 'Forecast_7_Days', 'Days_Until_Stockout',
        'Order_Qty', 'Status'
    ])
    
    for r in recommendations:
        writer.writerow([
            r['sku'],
            f'{r["current_qty"]:.0f}',
            f'{r["reorder_point"]:.0f}',
            f'{r["lead_time"]:.0f}',
            f'{r["avg_demand"]:.1f}',
            f'{r["forecast_7_days"]:.0f}',
            f'{r["days_until_stockout"]:.1f}',
            f'{r["order_qty"]:.0f}',
            r['status']
        ])
    
    # Add summary at bottom
    order_now = [r for r in recommendations if "ORDER NOW" in r['status']]
    writer.writerow([])
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total SKUs', 'Order Now', 'OK'])
    writer.writerow([len(recommendations), len(order_now), len(recommendations) - len(order_now)])
    
    return output.getvalue()

# ============ SEND EMAIL WITH ATTACHMENT ============

def send_email_with_attachment(subject, body, filename, file_data):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = ALERT_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(file_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={filename}')
        msg.attach(part)
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

# ============ MAIN ============

def run_forecast():
    print("\n" + "="*70)
    print("  DEMAND FORECASTING & REORDER SYSTEM")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    print("📥 Reading from Google Sheets...")
    sales_data = read_sheet("Sales_History")
    inventory_data = read_sheet("Inventory_Current")
    
    if not sales_data or not inventory_data:
        print("❌ Missing data. Check tabs: Sales_History, Inventory_Current")
        return
    
    sales_rows = sales_data[1:]  # Skip header
    inventory_rows = inventory_data[1:]
    
    print(f"✅ Sales Records: {len(sales_rows)} rows")
    print(f"✅ Inventory Records: {len(inventory_rows)} SKUs\n")
    
    print("🔍 Calculating average daily demand...")
    avg_demand = calculate_daily_demand(sales_rows)
    
    print("🔍 Forecasting next 7 days...")
    forecast = forecast_demand(avg_demand, 7)
    
    print("🔍 Calculating reorder recommendations...")
    recommendations = calculate_reorder(forecast, inventory_rows, avg_demand)
    
    # Summary
    order_now = [r for r in recommendations if "ORDER NOW" in r['status']]
    
    print("\n" + "="*70)
    print("📊 SUMMARY")
    print("="*70)
    print(f"SKUs Analyzed:        {len(recommendations)}")
    print(f"Items to Order Now:   {len(order_now)}")
    print(f"Items at Safe Levels: {len(recommendations) - len(order_now)}")
    print("="*70 + "\n")
    
    if order_now:
        print("🔴 ITEMS TO ORDER NOW:")
        for r in order_now[:10]:
            print(f"  • {r['sku']} | Current: {r['current_qty']:.0f} | Avg Demand: {r['avg_demand']:.1f}/day | Order: {r['order_qty']:.0f} units")
        if len(order_now) > 10:
            print(f"  ... and {len(order_now)-10} more")
    else:
        print("✅ All SKUs are at safe levels.")
    
    # Generate CSV
    csv_data = generate_csv(recommendations)
    filename = f"reorder_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    # Email body
    body = f"""
DEMAND FORECAST & REORDER REPORT
================================

📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 Summary:
- SKUs Analyzed: {len(recommendations)}
- Items to Order Now: {len(order_now)}
- Items at Safe Levels: {len(recommendations) - len(order_now)}

📎 Attached: {filename}
"""
    
    print("\n📧 Sending email with CSV attachment...")
    success = send_email_with_attachment(
        f"Reorder Alert: {len(order_now)} items need ordering",
        body,
        filename,
        csv_data.encode('utf-8')
    )
    
    if success:
        print("✅ Email sent successfully!")
    else:
        print("❌ Email failed to send")
    
    print("\n✅ Forecasting complete. Script will now stop.")

# ============ RUN ONCE AND STOP ============

if __name__ == "__main__":
    run_forecast()
