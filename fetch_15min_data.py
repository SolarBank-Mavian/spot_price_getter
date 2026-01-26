#!/usr/bin/env python3
"""
Script to fetch 15-minute electricity price data from OTE-CR endpoint
and send it to PostgREST API as JSON.
"""

import json
import os
import sys
import traceback
import requests
import time
from datetime import datetime, timedelta


def print_flush(*args, **kwargs):
    """Print with immediate flush to stdout."""
    print(*args, **kwargs)
    sys.stdout.flush()


def fetch_chart_data():
    """Fetch chart data from OTE-CR endpoint."""
    url = "https://www.ote-cr.cz/cs/kratkodobe-trhy/elektrina/denni-trh/chart-data"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print_flush(f"Error fetching data: {e}")
        raise


def extract_15min_data(chart_data):
    """Extract 15-minute price data from chart data."""
    data_lines = chart_data.get("data", {}).get("dataLine", [])
    
    # Find the dataLine with title "15min cena (EUR/MWh)"
    for line in data_lines:
        if line.get("title") == "15min cena (EUR/MWh)":
            return line.get("point", [])
    
    raise ValueError("15-minute price data not found in response")


def extract_date_from_title(chart_data):
    """Extract date from graph title (format: 'Výsledky denního trhu - 02.11.2025')."""
    title = chart_data.get("graph", {}).get("title", "")
    # Parse date from title like "Výsledky denního trhu - 02.11.2025"
    if " - " in title:
        date_str = title.split(" - ")[-1]
        try:
            # Parse DD.MM.YYYY format and convert to YYYY-MM-DD
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError as e:
            print_flush(f"Error parsing date from title: {e}")
            raise
    
    raise ValueError(f"Could not extract date from title: {title}")


def convert_to_time_format(period):
    """Convert period (1-96) to time format (00:00, 00:15, ..., 23:45)."""
    period_num = int(period)
    if period_num < 1 or period_num > 96:
        raise ValueError(f"Period must be between 1 and 96, got {period_num}")
    
    # Period 1 = 00:00, Period 2 = 00:15, ..., Period 96 = 23:45
    # Each period is 15 minutes
    period_index = period_num - 1  # 0-based index
    hours = period_index // 4
    minutes = (period_index % 4) * 15
    
    return f"{hours:02d}:{minutes:02d}"


def fetch_eur_to_czk_rate():
    """Fetch EUR to CZK exchange rate from ČNB API."""
    url = "https://api.cnb.cz/cnbapi/exrates/daily"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Find EUR rate
        for rate in data.get("rates", []):
            if rate.get("currencyCode") == "EUR":
                # The rate is for the amount specified in the 'amount' field (usually 1)
                # To get CZK per 1 EUR, we need to divide by the amount
                amount = rate.get("amount", 1)
                rate_value = rate.get("rate", 0)
                return rate_value / amount
        
        raise ValueError("EUR exchange rate not found in ČNB response")
    except requests.exceptions.RequestException as e:
        print_flush(f"Error fetching EUR rate from ČNB: {e}")
        raise


def format_for_api(points_15min, date_str, country_id="0"):
    """Format data for PostgREST API endpoint."""
    # Fetch EUR to CZK exchange rate
    print_flush("Fetching EUR to CZK exchange rate from ČNB...")
    eur_to_czk = fetch_eur_to_czk_rate()
    print_flush(f"EUR to CZK rate: {eur_to_czk}")
    
    # Build dates structure
    dates = {}
    
    for point in points_15min:
        period = point['x']
        price_eur = point['y']
        price_czk = float(price_eur) * eur_to_czk
        time_str = convert_to_time_format(period)
        
        dates[time_str] = {
            "price_eur_mwh": float(price_eur),
            "price_czk_mwh": round(price_czk, 2)
        }
    
    # Build p_data_prices with exchange_rate and dates
    data_prices = {
        "exchange_rate": eur_to_czk,
        "dates": dates
    }
    
    return {
        "p_country_id": country_id,
        "p_data_prices": data_prices,
        "p_prices_for_date": date_str
    }


def send_to_postgrest(api_data, postgrest_url, api_key):
    """Send data to PostgREST API endpoint."""
    endpoint = f"{postgrest_url}/rpc/insert_spot_price"
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }
    
    response = requests.post(endpoint, json=api_data, headers=headers)
    response.raise_for_status()
    return response.json()


def calculate_seconds_until_midnight():
    """Calculate seconds until next midnight (00:00)."""
    now = datetime.now()
    # Calculate next midnight (always tomorrow at 00:00:00)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    seconds_until = (next_midnight - now).total_seconds()
    return int(seconds_until), next_midnight


def wait_until_midnight():
    """Wait until next midnight (00:00)."""
    seconds_until, next_midnight = calculate_seconds_until_midnight()
    
    if seconds_until > 0:
        print_flush(f"Čekám do {next_midnight.strftime('%Y-%m-%d %H:%M:%S')}...")
        print_flush(f"Zbývá {seconds_until} sekund ({seconds_until // 3600:.1f} hodin)")
        time.sleep(seconds_until)
        print_flush(f"Dosáhnuto času {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - spouštím fetch...")
    else:
        print_flush(f"Aktuální čas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - spouštím fetch ihned...")


def perform_fetch():
    """Perform the fetch and send operation."""
    # ============================================================================
    # Load configuration from environment variables
    # ============================================================================
    postgrest_url = os.getenv("POSTGREST_URL", "http://postgrestapi:3000")
    api_key = os.getenv("POSTGREST_API_KEY")
    
    if not api_key:
        raise ValueError("POSTGREST_API_KEY environment variable is required")
    # ============================================================================
    
    print_flush("Fetching data from OTE-CR endpoint...")
    chart_data = fetch_chart_data()
    
    print_flush("Extracting 15-minute price data...")
    points_15min = extract_15min_data(chart_data)
    print_flush(f"Found {len(points_15min)} data points")
    
    print_flush("Extracting date from chart title...")
    date_str = extract_date_from_title(chart_data)
    print_flush(f"Date: {date_str}")
    
    print_flush("Formatting data for API...")
    api_data = format_for_api(points_15min, date_str)
    
    print_flush(f"Sending data to PostgREST at {postgrest_url}...")
    try:
        result = send_to_postgrest(api_data, postgrest_url, api_key)
        print_flush(f"✅ Úspěšně odesláno do PostgREST")
        print_flush(f"   Datum: {date_str}, Počet datových bodů: {len(points_15min)}")
        print_flush(f"   Response z API:")
        print_flush(f"   {json.dumps(result, indent=2, ensure_ascii=False)}")
        return True
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.text
                print_flush(f"❌ Neúspěšné odeslání do PostgREST")
                print_flush(f"   Chyba: {error_msg}")
                print_flush(f"   Detail odpovědi: {error_detail[:200]}")
            except:
                print_flush(f"❌ Neúspěšné odeslání do PostgREST: {error_msg}")
        else:
            print_flush(f"❌ Neúspěšné odeslání do PostgREST: {error_msg}")
        return False
    except Exception as e:
        print_flush(f"❌ Neúspěšné odeslání do PostgREST: {e}")
        return False


def main():
    """Main function to fetch and send 15-minute data at midnight (00:00)."""
    print_flush("=" * 60)
    print_flush("Spot Price Fetcher - První volání hned, pak vždy v 00:00")
    print_flush("=" * 60)
    print_flush(f"Script spuštěn v: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_flush(f"POSTGREST_URL: {os.getenv('POSTGREST_URL', 'http://localhost:9000')}")
    print_flush(f"POSTGREST_API_KEY: {'nastaveno' if os.getenv('POSTGREST_API_KEY') else 'CHYBÍ!'}")
    print_flush("")
    
    # Perform first fetch immediately after startup
    try:
        print_flush(f"\n🚀 Spouštím první fetch okamžitě po buildu...")
        print_flush(f"Aktuální čas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        success = perform_fetch()
        print_flush("\n" + "=" * 60)
        if success:
            print_flush(f"✅ První fetch úspěšně dokončen v {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print_flush(f"❌ První fetch selhal v {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_flush("=" * 60 + "\n")
    except Exception as e:
        print_flush(f"\n❌ Chyba při prvním fetch: {e}")
        print_flush(traceback.format_exc())
        print_flush(f"Pokračuji a čekám do půlnoci...\n")
    
    # Infinite loop to run daily at midnight
    while True:
        try:
            # Wait until midnight
            wait_until_midnight()
            
            # Perform the fetch operation
            success = perform_fetch()
            
            print_flush("\n" + "=" * 60)
            if success:
                print_flush(f"✅ Fetch úspěšně dokončen v {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print_flush(f"❌ Fetch selhal v {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print_flush("Čekám do příští půlnoci...")
            print_flush("=" * 60 + "\n")
            
        except KeyboardInterrupt:
            print_flush("\n\nUkončuji aplikaci...")
            break
        except Exception as e:
            print_flush(f"\n❌ Chyba při provádění fetch: {e}")
            print_flush(traceback.format_exc())
            print_flush(f"Čekám 1 minutu před dalším pokusem...")
            time.sleep(60)  # Wait 1 minute before retrying


if __name__ == "__main__":
    main()

