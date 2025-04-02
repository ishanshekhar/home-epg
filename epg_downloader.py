#!/usr/bin/env python3
import os
import sys
import json
import gzip
import shutil
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from match_channels import (
    load_playlist_channels, 
    match_channels, 
    generate_filtered_epg_xml,
    generate_consolidated_epg_xml
)

# Default configuration file
DEFAULT_CONFIG_FILE = "epg_sources.json"
# Default output directory
DEFAULT_OUTPUT_DIR = "epg_data"

def load_config(config_file):
    """Load EPG source URLs from a JSON configuration file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
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
        return output_path
    except Exception as e:
        print(f"Error decompressing {gz_file_path}: {e}")
        return None

def process_epg_files(epg_files, playlist_file, output_dir, threshold=70, only_perfect=False):
    """Process multiple EPG files and generate a consolidated filtered EPG"""
    # Load playlist channels
    playlist_channels = load_playlist_channels(playlist_file)
    if not playlist_channels:
        print("No playlist channels loaded. Exiting.")
        return False
    
    all_matches = []
    
    # Process each EPG file
    for epg_file in epg_files:
        if not os.path.exists(epg_file):
            print(f"EPG file not found: {epg_file}")
            continue
        
        print(f"\nProcessing EPG file: {epg_file}")
        # Match channels for this EPG file
        matches = match_channels(playlist_channels, epg_file, threshold)
        
        # Add source information to matches
        for match in matches:
            if match.get('epg_match'):
                match['source_file'] = os.path.basename(epg_file)
        
        # Add to all matches
        all_matches.extend(matches)
    
    # Create a consolidated list of unique playlist channels with their best matches
    consolidated_matches = {}
    for match in all_matches:
        playlist_channel_name = match['playlist_channel']['name']
        
        # If this channel already exists in consolidated_matches, check if the new match is better
        if playlist_channel_name in consolidated_matches:
            existing_match = consolidated_matches[playlist_channel_name]
            
            # If the existing match has no EPG match, or the new match has a better score
            if (not existing_match.get('epg_match') and match.get('epg_match')) or \
               (existing_match.get('epg_match') and match.get('epg_match') and 
                match['epg_match']['score'] > existing_match['epg_match']['score']):
                consolidated_matches[playlist_channel_name] = match
        else:
            consolidated_matches[playlist_channel_name] = match
    
    # Convert back to list
    final_matches = list(consolidated_matches.values())
    
    # Generate timestamp for the output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"consolidated_epg_{timestamp}.xml")
    
    # Generate the consolidated filtered EPG XML
    success = generate_consolidated_epg_xml(final_matches, epg_files, output_file, only_perfect)
    
    if success:
        print(f"\nConsolidated EPG file generated: {output_file}")
    else:
        print("\nFailed to generate consolidated EPG file.")
    
    return success

def main():
    # Parse command line arguments
    config_file = DEFAULT_CONFIG_FILE
    output_dir = DEFAULT_OUTPUT_DIR
    playlist_file = None
    threshold = 70
    only_perfect = False
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--config" and i + 1 < len(sys.argv):
            config_file = sys.argv[i + 1]
            i += 2
        elif arg == "--output-dir" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        elif arg == "--playlist" and i + 1 < len(sys.argv):
            playlist_file = sys.argv[i + 1]
            i += 2
        elif arg == "--threshold" and i + 1 < len(sys.argv):
            try:
                threshold = int(sys.argv[i + 1])
            except ValueError:
                print(f"Invalid threshold value: {sys.argv[i + 1]}")
            i += 2
        elif arg == "--only-perfect":
            only_perfect = True
            i += 1
        else:
            i += 1
    
    # Check if playlist file is provided
    if not playlist_file:
        print("Error: Playlist file is required. Use --playlist to specify the file.")
        print("Usage: python epg_downloader.py --playlist playlist.m3u [options]")
        print("Options:")
        print("  --config CONFIG_FILE    Specify the configuration file (default: epg_sources.json)")
        print("  --output-dir DIR        Specify the output directory (default: epg_data)")
        print("  --threshold N           Set the matching threshold (default: 70)")
        print("  --only-perfect          Include only perfect matches (100% score)")
        return
    
    # Load configuration
    config = load_config(config_file)
    if not config:
        print(f"Creating a default configuration file: {config_file}")
        config = {
            "epg_sources": []
        }
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Default configuration saved to {config_file}")
        except Exception as e:
            print(f"Error creating default configuration file: {e}")
            return
    
    # Download and decompress EPG files
    epg_files = []
    for url in config.get("epg_sources", []):
        downloaded_file = download_epg_file(url, output_dir)
        if downloaded_file and downloaded_file.endswith('.gz'):
            decompressed_file = decompress_gz_file(downloaded_file, output_dir)
            if decompressed_file:
                epg_files.append(decompressed_file)
    
    if not epg_files:
        print("No EPG files were successfully downloaded and decompressed.")
        return
    
    # Process the EPG files
    process_epg_files(epg_files, playlist_file, output_dir, threshold, only_perfect)

if __name__ == "__main__":
    main() 