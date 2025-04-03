#!/usr/bin/env python3
import os
import sys
import json
import gzip
import shutil
import requests
import re
from datetime import datetime

# Default configuration file
DEFAULT_CONFIG_FILE = "epg_sources.json"
# Default output directory
DEFAULT_OUTPUT_DIR = "epg_data"

def load_config(config_file):
    """Load EPG source URLs from a JSON configuration file"""
    try:
        if not os.path.exists(config_file):
            print(f"Error: Configuration file '{config_file}' not found.")
            return None
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Check if the config has the expected structure
        if "epg_sources" not in config:
            print(f"Error: Configuration file '{config_file}' does not contain 'epg_sources' key.")
            return None
        
        if not config["epg_sources"] or not isinstance(config["epg_sources"], list):
            print(f"Error: No EPG sources found in '{config_file}'.")
            return None
        
        print(f"Loaded {len(config['epg_sources'])} EPG sources from '{config_file}'")
        return config
    except json.JSONDecodeError:
        print(f"Error: '{config_file}' is not a valid JSON file.")
        return None
    except Exception as e:
        print(f"Error loading configuration file: {e}")
        return None

def download_epg_file(url, output_dir):
    """Download an EPG file from a URL and save it to the output directory"""
    try:
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract filename from URL
        filename = os.path.basename(url)
        if '?' in filename:  # Handle URLs with query parameters
            filename = filename.split('?')[0]
        
        # If no filename could be extracted, create one based on the URL
        if not filename:
            filename = f"epg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml.gz"
        
        output_path = os.path.join(output_dir, filename)
        
        print(f"Downloading {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Save the downloaded file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Downloaded to {output_path}")
        return output_path
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

def decompress_gz_file(gz_file_path, output_dir):
    """Decompress a GZ file and save it to the output directory"""
    try:
        # Extract the base filename without the .gz extension
        base_filename = os.path.basename(gz_file_path)
        if base_filename.endswith('.gz'):
            base_filename = base_filename[:-3]
        
        output_path = os.path.join(output_dir, base_filename)
        
        print(f"Decompressing {gz_file_path}...")
        with gzip.open(gz_file_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        print(f"Decompressed to {output_path}")
        
        # Remove the compressed file after successful decompression
        os.remove(gz_file_path)
        print(f"Removed compressed file: {gz_file_path}")
        
        return output_path
    except Exception as e:
        print(f"Error decompressing {gz_file_path}: {e}")
        return None

def extract_country_code(filename):
    """Extract country code from filename"""
    # Look for patterns like _UK_, _IN_, etc.
    match = re.search(r'_([A-Z]{2})(?:_|[0-9])', filename)
    if match:
        return match.group(1)
    
    # Try to extract from patterns like uk/, in/, us/ in the URL path
    match = re.search(r'\/([a-z]{2})\/[^\/]+$', filename)
    if match:
        return match.group(1).upper()
    
    return None

def download_epgs(config_file=DEFAULT_CONFIG_FILE, output_dir=DEFAULT_OUTPUT_DIR):
    """Download EPG files from configured sources"""
    # Load configuration
    config = load_config(config_file)
    if not config:
        print(f"Creating a default configuration file: {config_file}")
        config = {
            "epg_sources": [
            ]
        }
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Default configuration saved to {config_file}")
            print("You can edit this file to add your own EPG sources.")
        except Exception as e:
            print(f"Error creating default configuration file: {e}")
            return []
    
    # Download and decompress EPG files
    epg_files = []
    country_files = {}
    
    for url in config.get("epg_sources", []):
        downloaded_file = download_epg_file(url, output_dir)
        if not downloaded_file:
            continue
            
        if downloaded_file.endswith('.gz'):
            decompressed_file = decompress_gz_file(downloaded_file, output_dir)
            if decompressed_file:
                epg_files.append(decompressed_file)
                
                # Extract country code and organize files by country
                country_code = extract_country_code(url) or extract_country_code(os.path.basename(decompressed_file))
                if country_code:
                    if country_code not in country_files:
                        country_files[country_code] = []
                    country_files[country_code].append(decompressed_file)
        else:
            epg_files.append(downloaded_file)
            
            # Extract country code and organize files by country
            country_code = extract_country_code(url) or extract_country_code(os.path.basename(downloaded_file))
            if country_code:
                if country_code not in country_files:
                    country_files[country_code] = []
                country_files[country_code].append(downloaded_file)
    
    # Print summary
    if epg_files:
        print("\nDownloaded EPG files:")
        for file in epg_files:
            print(f"  - {file}")
        
        print("\nFiles by country:")
        for country, files in country_files.items():
            print(f"  {country}: {len(files)} file(s)")
            for file in files:
                print(f"    - {os.path.basename(file)}")
    else:
        print("No EPG files were successfully downloaded.")
        print("Please check your internet connection and the URLs in your configuration file.")
    
    return epg_files

def main():
    # Parse command line arguments
    config_file = DEFAULT_CONFIG_FILE
    output_dir = DEFAULT_OUTPUT_DIR
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--config" and i + 1 < len(sys.argv):
            config_file = sys.argv[i + 1]
            i += 2
        elif arg == "--output-dir" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    
    # Download EPG files
    download_epgs(config_file, output_dir)

if __name__ == "__main__":
    main() 