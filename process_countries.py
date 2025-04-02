#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import time
import argparse
import shutil

# Default playlist URL
DEFAULT_PLAYLIST_URL = ""
def load_country_mappings(json_file="epg_sources.json"):
    """Load country mappings from JSON file"""
    try:
        if not os.path.exists(json_file):
            print(f"EPG sources file not found: {json_file}")
            return {}
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        if "country_mappings" in data:
            return data["country_mappings"]
        
        return {}
    except Exception as e:
        print(f"Error loading country mappings: {e}")
        return {}

def clear_data_directories(clear_exports=False):
    """Clear data directories before processing
    
    Args:
        clear_exports: Whether to also clear export files
    """
    # Clear EPG data
    if os.path.exists('epg_data'):
        print("Clearing EPG data directory...")
        for file in os.listdir('epg_data'):
            file_path = os.path.join('epg_data', file)
            if os.path.isfile(file_path):
                os.unlink(file_path)
    
    # Clear playlist data
    if os.path.exists('playlist_data'):
        print("Clearing playlist data directory...")
        for file in os.listdir('playlist_data'):
            file_path = os.path.join('playlist_data', file)
            if os.path.isfile(file_path):
                os.unlink(file_path)
    
    # Only clear export files if specifically requested
    if clear_exports and os.path.exists('export_epg'):
        print("Clearing export EPG directory...")
        for file in os.listdir('export_epg'):
            file_path = os.path.join('export_epg', file)
            if os.path.isfile(file_path):
                os.unlink(file_path)

def run_match_channels(country_prefix, playlist_url, force_download=False):
    """Run match_channels.py for a specific country"""
    print(f"\n{'='*80}")
    print(f"Processing country: {country_prefix}")
    print(f"{'='*80}\n")
    
    cmd = [
        "python3", "match_channels.py",
        "--playlist-url", playlist_url,
        "--country-prefix", f"{country_prefix}:",
        "--only-perfect",
        "--output-dir", "export_epg"
    ]
    
    if force_download:
        cmd.append("--force-download")
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        # Run the command and capture output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Print the output
        print(result.stdout)
        
        if result.returncode != 0:
            print(f"Error processing {country_prefix}:")
            print(result.stderr)
            return False
        
        return True
    except Exception as e:
        print(f"Error running match_channels.py for {country_prefix}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Process EPG data for multiple countries.')
    parser.add_argument('--countries', nargs='+', help='List of country codes to process (default: all countries in epg_sources.json)')
    parser.add_argument('--playlist-url', default=DEFAULT_PLAYLIST_URL, help='URL to download the playlist from')
    parser.add_argument('--force-download', action='store_true', help='Force download of playlist even if recent file exists')
    parser.add_argument('--clear-data', action='store_true', help='Clear all EPG data, export files, and playlist data before running')
    
    args = parser.parse_args()
    
    # Clear data if requested
    if args.clear_data:
        print("Clearing all data directories before processing...")
        clear_data_directories(clear_exports=False)
    
    # Load country mappings
    country_mappings = load_country_mappings()
    if not country_mappings:
        print("No country mappings found in epg_sources.json")
        sys.exit(1)
    
    # Determine which countries to process
    countries_to_process = args.countries if args.countries else list(country_mappings.keys())
    
    print(f"Will process the following countries: {', '.join(countries_to_process)}")
    
    # Process each country
    successful_countries = []
    failed_countries = []
    
    for country in countries_to_process:
        if country in country_mappings:
            if run_match_channels(country, args.playlist_url, args.force_download):
                successful_countries.append(country)
            else:
                failed_countries.append(country)
        else:
            print(f"Warning: Country {country} not found in epg_sources.json")
            failed_countries.append(country)
    
    # Print summary
    print(f"\n{'='*80}")
    print("Processing Summary")
    print(f"{'='*80}")
    
    if successful_countries:
        print(f"\nSuccessfully processed {len(successful_countries)} countries:")
        for country in successful_countries:
            print(f"  - {country}: export_epg/epg_{country}.xml")
    
    if failed_countries:
        print(f"\nFailed to process {len(failed_countries)} countries:")
        for country in failed_countries:
            print(f"  - {country}")
    
    print(f"\nOutput files are in the export_epg directory.")
    print(f"You can use these files individually with your media player or IPTV client.")

if __name__ == "__main__":
    start_time = time.time()
    main()
    elapsed_time = time.time() - start_time
    print(f"\nTotal processing time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)") 