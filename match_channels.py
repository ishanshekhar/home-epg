#!/usr/bin/env python3
import re
import os
import sys
import csv
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import time
try:
    from fuzzywuzzy import fuzz
except ImportError:
    print("Warning: fuzzywuzzy package not found. Install with: pip install fuzzywuzzy python-Levenshtein")
    # Define a simple fallback for fuzz functions
    class FuzzFallback:
        @staticmethod
        def ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
        
        @staticmethod
        def partial_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
        
        @staticmethod
        def token_sort_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
        
        @staticmethod
        def token_set_ratio(s1, s2):
            return SequenceMatcher(None, s1, s2).ratio() * 100
    
    fuzz = FuzzFallback()

def load_playlist_from_xml(xml_content):
    """Load channels from XML content that contains channel information"""
    try:
        # Parse the XML content
        root = ET.fromstring(xml_content)
        
        channels = []
        
        # Extract channel information from XML
        for channel in root.findall(".//channel"):
            channel_id = channel.get('id', '')
            
            # Get display names
            display_names = []
            for display_name in channel.findall(".//display-name"):
                if display_name.text:
                    display_names.append(display_name.text.strip())
            
            if display_names:
                channel_name = display_names[0]
                
                # Create a channel entry
                channels.append({
                    'name': channel_name,
                    'clean_name': channel_name,  # Will be cleaned later if needed
                    'tvg_id': channel_id,
                    'info': f'#EXTINF:-1 tvg-id="{channel_id}",{channel_name}',
                    'url': f'#EXTURL:{channel_id}'  # Placeholder URL
                })
        
        print(f"Found {len(channels)} channels in XML playlist")
        return channels
    except Exception as e:
        print(f"Error parsing XML playlist: {e}")
        return []

def load_playlist_channels(file_path, country_prefix=None):
    """Load channels from M3U playlist file with optional country filtering"""
    if not os.path.exists(file_path):
        print(f"Playlist file not found: {file_path}")
        return []
    
    print(f"Loading playlist from {file_path}...")
    try:
        # Check if the file is XML
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # If it starts with XML declaration or contains <tv> tag, treat as XML
        if content.strip().startswith('<?xml') or '<tv>' in content:
            print("Detected XML format in playlist file")
            channels = load_playlist_from_xml(content)
            
            # Apply country filter if specified
            if country_prefix and channels:
                filtered_channels = []
                
                print(f"Filtering channels by country prefix: {country_prefix}")
                for channel in channels:
                    # Only include channels that start with the prefix
                    if channel['name'].startswith(country_prefix):
                        filtered_channels.append(channel)
                
                print(f"Found {len(filtered_channels)} channels with prefix: {country_prefix}")
                return filtered_channels
            
            return channels
        
        # Otherwise, process as M3U
        channels = []
        lines = content.splitlines()
        
        # Get TV channels only
        for i in range(len(lines)):
            if lines[i].startswith("#EXTINF"):
                # Get the channel info from current line
                channel_info = lines[i]
                # Extract channel name
                channel_name_match = re.search(r',(.+)$', channel_info)
                if channel_name_match:
                    channel_name = channel_name_match.group(1).strip()
                    
                    # Apply country filter if specified
                    include_channel = True
                    if country_prefix:
                        # Only include channels that start with the prefix
                        include_channel = channel_name.startswith(country_prefix)
                    
                    if include_channel:
                        # Get the URL from the next line
                        if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                            url = lines[i + 1].strip()
                            # Extract tvg-id if available
                            tvg_id_match = re.search(r'tvg-id="([^"]*)"', channel_info)
                            tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
                            
                            # Clean name (remove country prefix)
                            clean_name = channel_name
                            if country_prefix and channel_name.startswith(country_prefix):
                                clean_name = channel_name[len(country_prefix):].strip()
                            
                            channels.append({
                                'name': channel_name,
                                'clean_name': clean_name,
                                'tvg_id': tvg_id,
                                'info': channel_info,
                                'url': url
                            })
        
        if country_prefix:
            print(f"Found {len(channels)} channels with prefix: {country_prefix}")
        else:
            print(f"Found {len(channels)} channels in playlist")
        return channels
    except Exception as e:
        print(f"Error loading playlist: {e}")
        return []

def load_epg_channels(epg_file_path):
    """Load channel information from EPG XML file"""
    if not os.path.exists(epg_file_path):
        print(f"EPG file not found: {epg_file_path}")
        return []
    
    print(f"Loading EPG data from {epg_file_path}...")
    try:
        # Parse the XML file
        tree = ET.parse(epg_file_path)
        root = tree.getroot()
        
        epg_channels = []
        
        # Extract channel information
        for channel in root.findall(".//channel"):
            channel_id = channel.get('id')
            
            # Get display names
            display_names = []
            for display_name in channel.findall(".//display-name"):
                if display_name.text:
                    display_names.append(display_name.text.strip())
            
            # Get icons
            icons = []
            for icon in channel.findall(".//icon"):
                src = icon.get('src')
                if src:
                    icons.append(src)
            
            if channel_id and display_names:
                epg_channels.append({
                    'id': channel_id,
                    'display_names': display_names,
                    'primary_name': display_names[0] if display_names else "",
                    'icons': icons
                })
        
        print(f"Loaded {len(epg_channels)} channels from EPG data")
        return epg_channels
    except Exception as e:
        print(f"Error loading EPG file: {e}")
        return []

def clean_channel_name(name):
    """Clean channel name for better matching"""
    # Remove common prefixes
    for prefix in ["UK:", "US:", "IN:", "CA:"]:
        if name.upper().startswith(prefix):
            name = name[len(prefix):].strip()
    
    # Standardize spacing
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Remove HD/SD/FHD/UHD quality indicators
    name = re.sub(r'\b(HD|SD|FHD|UHD|4K|HEVC|H265|H\.265)\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(HD|SD|FHD|UHD|4K)$', '', name, flags=re.IGNORECASE)
    
    # Remove other common suffixes
    name = re.sub(r'\s+(CHANNEL|TV|NETWORK|INDIA)\s*$', '', name, flags=re.IGNORECASE)
    
    # Remove common punctuation that might affect matching
    name = re.sub(r'[&+]', ' AND ', name)
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # Standardize spacing again after all replacements
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name.strip().upper()

def find_best_match(channel, epg_channels, threshold=70, quiet=True):
    """Find the best matching EPG channel for a given playlist channel"""
    clean_name = clean_channel_name(channel['clean_name'])
    best_match = None
    best_score = 0
    best_method = None
    
    # For debugging
    if not quiet:
        print(f"Finding match for: {channel['name']} → Cleaned to: {clean_name}")
    
    # Try exact match first (case insensitive)
    for epg_channel in epg_channels:
        for display_name in epg_channel['display_names']:
            clean_epg_name = clean_channel_name(display_name)
            if clean_name == clean_epg_name:
                if not quiet:
                    print(f"  Exact match found: {display_name} ({epg_channel['id']})")
                return {
                    'epg_channel': epg_channel,
                    'score': 100,
                    'method': 'Exact match'
                }
    
    # Try fuzzy matching
    for epg_channel in epg_channels:
        for display_name in epg_channel['display_names']:
            clean_epg_name = clean_channel_name(display_name)
            
            # Try different fuzzy matching methods
            ratio = fuzz.ratio(clean_name, clean_epg_name)
            partial_ratio = fuzz.partial_ratio(clean_name, clean_epg_name)
            token_sort_ratio = fuzz.token_sort_ratio(clean_name, clean_epg_name)
            token_set_ratio = fuzz.token_set_ratio(clean_name, clean_epg_name)
            
            # Use the best score from any method
            current_best = best_score
            
            if ratio > best_score:
                best_score = ratio
                best_match = epg_channel
                best_method = 'String similarity'
            
            if partial_ratio > best_score:
                best_score = partial_ratio
                best_match = epg_channel
                best_method = 'Partial match'
            
            if token_sort_ratio > best_score:
                best_score = token_sort_ratio
                best_match = epg_channel
                best_method = 'Token sort'
                
            if token_set_ratio > best_score:
                best_score = token_set_ratio
                best_match = epg_channel
                best_method = 'Token set'
                
            # Print high-scoring matches for debugging
            if not quiet and best_score > current_best and best_score >= 80:
                print(f"  Good match: {display_name} - Score: {best_score}% ({best_method})")
    
    if best_score >= threshold:
        return {
            'epg_channel': best_match,
            'score': best_score,
            'method': best_method
        }
    else:
        if not quiet:
            print(f"  No good match found. Best score: {best_score}%")
        return None

def match_channels(playlist_channels, epg_file, threshold=70, quiet=True):
    """Match playlist channels with EPG data"""
    epg_channels = load_epg_channels(epg_file)
    if not epg_channels:
        return []
    
    matches = []
    for channel in playlist_channels:
        epg_match = find_best_match(channel, epg_channels, threshold, quiet)
        matches.append({
            'playlist_channel': channel,
            'epg_match': epg_match
        })
    
    # Count matches
    matched_count = sum(1 for m in matches if m['epg_match'])
    perfect_matches = sum(1 for m in matches if m['epg_match'] and m['epg_match']['score'] == 100)
    
    print(f"Found matches for {matched_count} out of {len(playlist_channels)} channels ({matched_count/len(playlist_channels)*100:.1f}%)")
    print(f"Perfect matches (100% score): {perfect_matches}")
    
    return matches

def display_matches(matches, show_all=False, only_perfect=False):
    """Display channel matches in console"""
    # Sort by match score (descending)
    sorted_matches = sorted(matches, key=lambda x: x['epg_match']['score'] if x['epg_match'] else 0, reverse=True)
    
    # Filter based on options
    if only_perfect:
        sorted_matches = [m for m in sorted_matches if m['epg_match'] and m['epg_match']['score'] == 100]
        print(f"\nShowing {len(sorted_matches)} perfect matches (100% score):")
    elif not show_all:
        sorted_matches = [m for m in sorted_matches if m['epg_match']]
        print(f"\nShowing {len(sorted_matches)} channel matches:")
    else:
        print(f"\nShowing all {len(sorted_matches)} channels:")
    
    print("-" * 80)
    
    for i, match in enumerate(sorted_matches, 1):
        print(f"{i}. Playlist Channel: {match['playlist_channel']['name']}")
        
        if match['epg_match']:
            print(f"   EPG Channel: {match['epg_match']['epg_channel']['primary_name']}")
            print(f"   EPG ID: {match['epg_match']['epg_channel']['id']}")
            print(f"   Match Score: {match['epg_match']['score']}% ({match['epg_match']['method']})")
            if match['epg_match']['epg_channel']['icons']:
                print(f"   Icon: {match['epg_match']['epg_channel']['icons'][0]}")
        else:
            print("   No EPG match found")
        
        print("-" * 80)

def export_matches_to_csv(matches, filename, only_perfect=False):
    """Export channel matches to CSV file"""
    # Filter for perfect matches if requested
    if only_perfect:
        matches_to_export = [m for m in matches if m['epg_match'] and m['epg_match']['score'] == 100]
    else:
        matches_to_export = matches
    
    fieldnames = [
        'Playlist Channel', 
        'EPG Channel ID', 
        'EPG Display Name', 
        'Match Score', 
        'Match Method',
        'Icon URL'
    ]
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for match in matches_to_export:
                row = {
                    'Playlist Channel': match['playlist_channel']['name'],
                    'EPG Channel ID': match['epg_match']['epg_channel']['id'] if match['epg_match'] else 'No match',
                    'EPG Display Name': match['epg_match']['epg_channel']['primary_name'] if match['epg_match'] else 'No match',
                    'Match Score': match['epg_match']['score'] if match['epg_match'] else 0,
                    'Match Method': match['epg_match']['method'] if match['epg_match'] else 'None',
                    'Icon URL': match['epg_match']['epg_channel']['icons'][0] if match['epg_match'] and match['epg_match']['epg_channel']['icons'] else ''
                }
                writer.writerow(row)
        
        print(f"Exported {len(matches_to_export)} channel matches to {filename}")
    except Exception as e:
        print(f"Error exporting to CSV: {e}")

def generate_filtered_epg_xml(matches, input_epg_file, output_file, only_perfect=True):
    """Generate a filtered EPG XML file containing only matched channels and their programs"""
    if not os.path.exists(input_epg_file):
        print(f"EPG file not found: {input_epg_file}")
        return False
    
    # Filter for perfect matches if requested
    if only_perfect:
        matches_to_include = [m for m in matches if m['epg_match'] and m['epg_match']['score'] == 100]
    else:
        matches_to_include = [m for m in matches if m['epg_match']]
    
    if not matches_to_include:
        print("No matches to include in the filtered EPG file.")
        return False
    
    try:
        # Parse the original EPG file
        tree = ET.parse(input_epg_file)
        root = tree.getroot()
        
        # Create a new XML root with the same structure
        new_root = ET.Element('tv')
        for attr_name, attr_value in root.attrib.items():
            new_root.set(attr_name, attr_value)
        
        # Track channel IDs to include
        channel_ids_to_include = set()
        
        # Add matched channels to the new XML
        for match in matches_to_include:
            epg_channel_id = match['epg_match']['epg_channel']['id']
            channel_ids_to_include.add(epg_channel_id)
            
            # Find the original channel element
            for channel_elem in root.findall(".//channel[@id='{}']".format(epg_channel_id)):
                # Create a new channel element
                new_channel = ET.SubElement(new_root, 'channel', id=epg_channel_id)
                
                # Use the playlist channel name as the display name
                display_name = ET.SubElement(new_channel, 'display-name')
                display_name.text = match['playlist_channel']['name']
                
                # Copy icons if they exist
                for icon in channel_elem.findall('.//icon'):
                    new_icon = ET.SubElement(new_channel, 'icon', src=icon.get('src', ''))
                
                # Copy any other elements
                for child in channel_elem:
                    if child.tag != 'display-name' and child.tag != 'icon':
                        new_channel.append(child)
        
        # Add program entries for the included channels
        for program in root.findall(".//programme"):
            channel_id = program.get('channel')
            if channel_id in channel_ids_to_include:
                # Copy the program element and all its children
                new_program = ET.Element('programme')
                for attr_name, attr_value in program.attrib.items():
                    new_program.set(attr_name, attr_value)
                
                for child in program:
                    new_program.append(child)
                
                new_root.append(new_program)
        
        # Create a new XML tree and write to file
        new_tree = ET.ElementTree(new_root)
        
        # Count the number of programs included
        program_count = len(new_root.findall(".//programme"))
        channel_count = len(new_root.findall(".//channel"))
        
        # Write the new XML file with proper formatting
        with open(output_file, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            new_tree.write(f, encoding='utf-8')
        
        print(f"Generated filtered EPG file: {output_file}")
        print(f"Included {channel_count} channels and {program_count} program entries")
        return True
    
    except Exception as e:
        print(f"Error generating filtered EPG file: {e}")
        return False

def generate_consolidated_epg_xml(matches, epg_files, output_file, only_perfect=True):
    """Generate a consolidated EPG XML file from multiple source files"""
    # Filter for perfect matches if requested
    if only_perfect:
        matches_to_include = [m for m in matches if m.get('epg_match') and m['epg_match']['score'] == 100]
    else:
        matches_to_include = [m for m in matches if m.get('epg_match')]
    
    if not matches_to_include:
        print("No matches to include in the consolidated EPG file.")
        return False
    
    try:
        # Create a new XML root
        new_root = ET.Element('tv')
        new_root.set('generator-info-name', 'Consolidated EPG Generator')
        new_root.set('generator-info-url', 'https://github.com/yourusername/epg-tools')
        
        # Track channel IDs to avoid duplicates
        added_channel_ids = set()
        
        # Create a mapping of source files to their parsed XML trees
        epg_trees = {}
        for epg_file in epg_files:
            if os.path.exists(epg_file):
                try:
                    tree = ET.parse(epg_file)
                    epg_trees[epg_file] = tree
                except Exception as e:
                    print(f"Error parsing EPG file {epg_file}: {e}")
        
        # Add matched channels to the new XML
        for match in matches_to_include:
            if not match.get('epg_match') or not match.get('source_file'):
                continue
                
            epg_channel_id = match['epg_match']['epg_channel']['id']
            source_file = match.get('source_file')
            
            # Find the full path of the source file
            source_file_path = None
            for epg_file in epg_files:
                if os.path.basename(epg_file) == source_file:
                    source_file_path = epg_file
                    break
            
            if not source_file_path or source_file_path not in epg_trees:
                continue
            
            root = epg_trees[source_file_path].getroot()
            
            # Skip if we've already added this channel ID
            if epg_channel_id in added_channel_ids:
                continue
            
            # Find the original channel element
            channel_elem = root.find(f".//channel[@id='{epg_channel_id}']")
            if channel_elem is None:
                continue
                
            # Create a new channel element
            new_channel = ET.SubElement(new_root, 'channel', id=epg_channel_id)
            
            # Use the playlist channel name as the display name
            display_name = ET.SubElement(new_channel, 'display-name')
            display_name.text = match['playlist_channel']['name']
            
            # Copy icons if they exist
            for icon in channel_elem.findall('.//icon'):
                new_icon = ET.SubElement(new_channel, 'icon', src=icon.get('src', ''))
            
            # Copy any other elements
            for child in channel_elem:
                if child.tag != 'display-name' and child.tag != 'icon':
                    new_channel.append(ET.fromstring(ET.tostring(child)))
            
            # Mark this channel ID as added
            added_channel_ids.add(epg_channel_id)
        
        # Add program entries for the included channels
        for epg_file, tree in epg_trees.items():
            root = tree.getroot()
            for program in root.findall(".//programme"):
                channel_id = program.get('channel')
                if channel_id in added_channel_ids:
                    # Copy the program element and all its children
                    new_program = ET.Element('programme')
                    for attr_name, attr_value in program.attrib.items():
                        new_program.set(attr_name, attr_value)
                    
                    for child in program:
                        new_program.append(ET.fromstring(ET.tostring(child)))
                    
                    new_root.append(new_program)
        
        # Create a new XML tree and write to file
        new_tree = ET.ElementTree(new_root)
        
        # Count the number of programs included
        program_count = len(new_root.findall(".//programme"))
        channel_count = len(new_root.findall(".//channel"))
        
        # Write the new XML file with proper formatting
        with open(output_file, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            new_tree.write(f, encoding='utf-8')
        
        print(f"Generated consolidated EPG file: {output_file}")
        print(f"Included {channel_count} channels and {program_count} program entries")
        return True
    
    except Exception as e:
        print(f"Error generating consolidated EPG file: {e}")
        return False

def download_file(url, output_dir="downloads", file_type="generic"):
    """Download a file from a URL and save it to the output directory"""
    import requests
    import os
    import gzip
    import shutil
    
    try:
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract filename from URL or create a default one
        if '?' in url:  # URL has query parameters
            base_url = url.split('?')[0]
            filename = os.path.basename(base_url)
            if not filename:  # If URL ends with '/'
                filename = f"{file_type}_{int(time.time())}"
        else:
            filename = os.path.basename(url)
        
        # If no extension, add appropriate one
        if '.' not in filename:
            if file_type == "playlist":
                filename += ".m3u"
            elif file_type == "epg":
                filename += ".xml"
        
        output_path = os.path.join(output_dir, filename)
        
        print(f"Downloading {file_type} from {url}...")
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Get the content
        content = response.content
        
        # Save the downloaded file
        with open(output_path, 'wb') as f:
            f.write(content)
        
        print(f"Downloaded to {output_path}")
        
        # If it's a gzip file, decompress it
        if filename.endswith('.gz'):
            # Create proper output filename by removing .gz extension
            decompressed_filename = os.path.splitext(filename)[0]  # Remove .gz extension
            decompressed_path = os.path.join(output_dir, decompressed_filename)
            
            print(f"Decompressing {output_path}...")
            with gzip.open(output_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove the compressed file after decompression
            os.remove(output_path)
            print(f"Decompressed to {decompressed_path}")
            return decompressed_path
        
        return output_path
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

# Keep the existing download_epg_file function for backward compatibility
def download_epg_file(url, output_dir="epg_data"):
    """Download an EPG file from a URL and save it to the output directory"""
    return download_file(url, output_dir, "epg")

def download_playlist_from_url(url, output_dir="playlist_data", force_download=False):
    """Download M3U playlist from a specified URL, with date in filename and only if needed"""
    import requests
    import os
    import datetime
    
    try:
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get today's date for the filename
        today = datetime.datetime.now().strftime("%Y%m%d")
        
        # Use a filename with date
        filename = f"playlist_{today}.m3u"
        output_path = os.path.join(output_dir, filename)
        
        # Check if we already have today's file
        if os.path.exists(output_path) and not force_download:
            print(f"Using existing playlist file from today: {output_path}")
            return output_path, 'm3u'
        
        # Check for older files
        if not force_download:
            files = os.listdir(output_dir)
            playlist_files = [f for f in files if f.startswith("playlist_") and f.endswith(".m3u")]
            
            if playlist_files:
                # Sort by date (newest first)
                playlist_files.sort(reverse=True)
                newest_file = playlist_files[0]
                newest_path = os.path.join(output_dir, newest_file)
                
                # Extract date from filename
                try:
                    file_date_str = newest_file.replace("playlist_", "").replace(".m3u", "")
                    file_date = datetime.datetime.strptime(file_date_str, "%Y%m%d")
                    
                    # Check if file is less than one day old
                    age = datetime.datetime.now() - file_date
                    if age.days < 1:
                        print(f"Using recent playlist file (less than 1 day old): {newest_path}")
                        return newest_path, 'm3u'
                    else:
                        print(f"Existing playlist file is {age.days} days old. Downloading new one.")
                except ValueError:
                    # If we can't parse the date, download a new file
                    pass
        
        print(f"Downloading playlist from {url}...")
        
        # Use requests to download the file
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Save the content to a file
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        print(f"Downloaded to {output_path}")
        
        # Check if the content is XML by decoding a copy of the content
        content_text = response.content.decode('utf-8', errors='ignore')
        if content_text.strip().startswith('<?xml') or '<tv>' in content_text:
            print("Detected XML format in playlist file")
            # If it's XML, rename the file to reflect that
            xml_path = output_path.replace(".m3u", ".xml")
            os.rename(output_path, xml_path)
            return xml_path, 'xml'
        
        return output_path, 'm3u'
    except Exception as e:
        print(f"Error downloading playlist from {url}: {e}")
        return None, None

def use_local_livego_playlist(playlist_path="playlist_data/livego_playlist.xml"):
    """Use a local livego playlist XML file instead of downloading it"""
    if not os.path.exists(playlist_path):
        print(f"Error: Local livego playlist file not found at {playlist_path}")
        print("Please make sure the file exists or specify the correct path.")
        return None
    
    print(f"Using local livego playlist file: {playlist_path}")
    return playlist_path, 'xml'

def load_epg_sources(json_file="epg_sources.json"):
    """Load EPG sources from JSON file with explicit country mappings"""
    import json
    
    try:
        if not os.path.exists(json_file):
            print(f"EPG sources file not found: {json_file}")
            return {}
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Check if we have the new format with explicit country mappings
        if "country_mappings" in data:
            print("Using explicit country mappings from EPG sources file")
            return data["country_mappings"]
        
        # Fallback to the old format with list of URLs
        if "epg_sources" in data:
            print("Using legacy EPG sources format, extracting country codes from URLs")
            sources = {}
            
            # Extract country code from each URL
            for url in data.get("epg_sources", []):
                # Extract country code from filename (e.g., epg_ripper_UK1.xml.gz -> UK)
                filename = os.path.basename(url)
                match = re.search(r'epg_ripper_([A-Z]{2})(?:_[A-Z]+)?(?:\d*)\.xml', filename)
                if match:
                    country_code = match.group(1)
                    if country_code in sources:
                        if isinstance(sources[country_code], list):
                            sources[country_code].append(url)
                        else:
                            sources[country_code] = [sources[country_code], url]
                    else:
                        sources[country_code] = [url]
            
            return sources
        
        return {}
    except Exception as e:
        print(f"Error loading EPG sources: {e}")
        return {}

def get_epg_urls_for_country(country_prefix, sources_file="epg_sources.json"):
    """Get all EPG URLs for a specific country prefix"""
    # Load EPG sources
    sources = load_epg_sources(sources_file)
    
    if not sources:
        print("No EPG sources found.")
        return []
    
    # Extract country code from prefix (e.g., "UK:" -> "UK")
    country_code = country_prefix.rstrip(':').upper()
    
    # Find all matching EPG URLs
    if country_code in sources:
        urls = sources[country_code]
        # Ensure we always return a list
        if not isinstance(urls, list):
            urls = [urls]
        
        print(f"Found {len(urls)} EPG sources for country {country_code}")
        for url in urls:
            print(f"  - {url}")
        return urls
    
    print(f"No EPG sources found for country {country_code}")
    return []

def download_multiple_epg_files(urls, output_dir="epg_data"):
    """Download multiple EPG files and return their paths"""
    downloaded_files = []
    
    for url in urls:
        downloaded_file = download_epg_file(url, output_dir)
        if downloaded_file:
            downloaded_files.append(downloaded_file)
    
    return downloaded_files

def consolidate_epg_files(epg_files, output_file):
    """Consolidate multiple EPG files into a single file"""
    if not epg_files:
        print("No EPG files to consolidate")
        return None
    
    if len(epg_files) == 1:
        print(f"Only one EPG file provided, no consolidation needed: {epg_files[0]}")
        return epg_files[0]
    
    try:
        # Create a new XML root
        new_root = ET.Element('tv')
        new_root.set('generator-info-name', 'Consolidated EPG Generator')
        
        # Track channel IDs to avoid duplicates
        channel_ids = set()
        program_count = 0
        
        print(f"Consolidating {len(epg_files)} EPG files...")
        
        for file_path in epg_files:
            print(f"Processing {file_path}...")
            
            # Parse the EPG file
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Copy attributes from the first file
            if not new_root.attrib:
                for attr, value in root.attrib.items():
                    if attr != 'generator-info-name':
                        new_root.set(attr, value)
            
            # Add channels that aren't already included
            for channel in root.findall(".//channel"):
                channel_id = channel.get('id')
                if channel_id not in channel_ids:
                    channel_ids.add(channel_id)
                    new_root.append(channel)
            
            # Add all programs
            for program in root.findall(".//programme"):
                new_root.append(program)
                program_count += 1
        
        # Create a new XML tree
        new_tree = ET.ElementTree(new_root)
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Write the consolidated EPG file
        with open(output_file, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            new_tree.write(f, encoding='utf-8')
        
        print(f"Consolidated EPG file created: {output_file}")
        print(f"Included {len(channel_ids)} channels and {program_count} program entries")
        
        return output_file
    except Exception as e:
        print(f"Error consolidating EPG files: {e}")
        return None

if __name__ == "__main__":
    # This script can also be run standalone
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python match_channels.py [epg_file.xml] [options]")
        print("Options:")
        print("  --playlist-url URL        URL to download the playlist from")
        print("  --country-prefix PREFIX   Filter channels by country prefix (e.g., 'UK:', 'US:', 'IN:')")
        print("  --threshold N             Set the matching threshold (default: 70)")
        print("  --output-dir DIR          Directory to save filtered EPG files (default: export_epg)")
        print("  --only-perfect            Include only perfect matches (100% score)")
        print("  --verbose                 Show detailed matching information")
        print("  --export-csv FILENAME     Export matches to CSV file")
        print("  --show-all                Show all channels including those without matches")
        print("  --download-dir DIR        Directory to save downloaded files (default: downloads)")
        print("  --playlist-dir DIR        Directory to save downloaded playlists (default: playlist_data)")
        print("  --epg-dir DIR             Directory to save downloaded EPG files (default: epg_data)")
        print("  --epg-sources FILE        JSON file with EPG sources (default: epg_sources.json)")
        print("  --force-download          Force download of playlist even if recent file exists")
        sys.exit(1)
    
    # Parse options first to get parameters
    country_prefix = None
    threshold = 70
    output_dir = "export_epg"
    only_perfect = False
    verbose = False
    export_csv = None
    show_all = False
    download_dir = "downloads"
    playlist_dir = "playlist_data"
    epg_dir = "epg_data"
    epg_sources_file = "epg_sources.json"
    epg_file = None
    playlist_url = None
    force_download = False
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--country-prefix" and i + 1 < len(sys.argv):
            country_prefix = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--playlist-url" and i + 1 < len(sys.argv):
            playlist_url = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--force-download":
            force_download = True
            i += 1
        elif sys.argv[i] == "--threshold" and i + 1 < len(sys.argv):
            threshold = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--output-dir" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--export-csv" and i + 1 < len(sys.argv):
            export_csv = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--download-dir" and i + 1 < len(sys.argv):
            download_dir = sys.argv[i + 1]
            playlist_dir = download_dir
            epg_dir = download_dir
            i += 2
        elif sys.argv[i] == "--playlist-dir" and i + 1 < len(sys.argv):
            playlist_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--epg-dir" and i + 1 < len(sys.argv):
            epg_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--epg-sources" and i + 1 < len(sys.argv):
            epg_sources_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--only-perfect":
            only_perfect = True
            i += 1
        elif sys.argv[i] == "--verbose":
            verbose = True
            i += 1
        elif sys.argv[i] == "--show-all":
            show_all = True
            i += 1
        elif not epg_file and not sys.argv[i].startswith("--"):
            # First non-option argument is the EPG file
            epg_file = sys.argv[i]
            i += 1
        else:
            i += 1
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # If no EPG file specified but country_prefix is provided, try to get it from epg_sources.json
    if not epg_file and country_prefix:
        epg_urls = get_epg_urls_for_country(country_prefix, epg_sources_file)
        if epg_urls:
            if len(epg_urls) > 1:
                print(f"Found multiple EPG sources for {country_prefix}, will consolidate them.")
                # Download all EPG files
                downloaded_epgs = download_multiple_epg_files(epg_urls, epg_dir)
                if downloaded_epgs:
                    # Consolidate the EPG files
                    consolidated_file = os.path.join(epg_dir, f"consolidated_{country_prefix.rstrip(':')}.xml")
                    epg_file = consolidate_epg_files(downloaded_epgs, consolidated_file)
                    if not epg_file:
                        print("Failed to consolidate EPG files.")
                        sys.exit(1)
                else:
                    print("Failed to download EPG files.")
                    sys.exit(1)
            else:
                # Just one EPG file, use it directly
                epg_file = epg_urls[0]
                print(f"Using EPG file for {country_prefix}: {epg_file}")
                
                # Download the EPG file if it's a URL
                if epg_file.startswith(('http://', 'https://')):
                    downloaded_epg = download_epg_file(epg_file, epg_dir)
                    if downloaded_epg:
                        epg_file = downloaded_epg
                    else:
                        print(f"Failed to download EPG from {epg_file}")
                        sys.exit(1)
        else:
            print(f"Error: No EPG file specified and no matching EPG source found for country prefix {country_prefix}.")
            sys.exit(1)

    # If still no EPG file specified, show error
    if not epg_file:
        print("Error: No EPG file specified. Please provide an EPG file or use --country-prefix with a known country.")
        sys.exit(1)

    try:
        import requests
        
        # Download playlist from the specified URL
        downloaded_playlist, format_type = download_playlist_from_url(playlist_url, playlist_dir, force_download)
        if downloaded_playlist:
            playlist_file = downloaded_playlist
            print(f"Using playlist from {playlist_url}: {playlist_file}")
        else:
            print(f"Failed to download playlist from {playlist_url}")
            sys.exit(1)
        
        # Check if epg_file is a URL and download it if needed
        if epg_file.startswith(('http://', 'https://')):
            epg_urls = get_epg_urls_for_country(country_prefix, epg_sources_file)
            if epg_urls:
                epg_files = download_multiple_epg_files(epg_urls, epg_dir)
                if epg_files:
                    epg_file = consolidate_epg_files(epg_files, epg_dir)
                else:
                    print(f"Failed to download EPG files for {country_prefix}")
                    sys.exit(1)
            else:
                print(f"Error: No EPG files found for {country_prefix}")
                sys.exit(1)
    except ImportError:
        print("Error: The requests package is required for downloading files.")
        print("Please install it using: pip install requests")
        sys.exit(1)
    
    # Load playlist channels
    playlist_channels = load_playlist_channels(playlist_file, country_prefix)
    
    if not playlist_channels:
        print(f"No channels found in playlist: {playlist_file}")
        if country_prefix:
            print(f"Note: You specified a country prefix '{country_prefix}', which might be filtering out all channels.")
        sys.exit(1)
    
    # Match channels
    matches = match_channels(playlist_channels, epg_file, threshold, not verbose)
    
    # Display matches
    display_matches(matches, show_all, only_perfect)
    
    # Export to CSV if requested
    if export_csv:
        export_matches_to_csv(matches, export_csv, only_perfect)
    
    # Generate filtered EPG with country prefix in filename
    if country_prefix:
        country_code = country_prefix.rstrip(':').upper()
        output_file = os.path.join(output_dir, f"epg_{country_code}.xml")
    else:
        output_file = os.path.join(output_dir, "epg.xml")
    
    print(f"Generating filtered EPG file: {output_file}")
    generate_filtered_epg_xml(matches, epg_file, output_file, only_perfect)

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # If no EPG file specified but country_prefix is provided, try to get it from epg_sources.json
    if not epg_file and country_prefix:
        epg_urls = get_epg_urls_for_country(country_prefix, epg_sources_file)
        if epg_urls:
            epg_files = download_multiple_epg_files(epg_urls, epg_dir)
            if epg_files:
                epg_file = consolidate_epg_files(epg_files, epg_dir)
            else:
                print(f"Failed to download EPG files for {country_prefix}")
                sys.exit(1)
        else:
            print(f"Error: No EPG files found for {country_prefix}")
            sys.exit(1)

    # If still no EPG file specified, show error
    if not epg_file:
        print("Error: No EPG file specified. Please provide an EPG file or use --country-prefix with a known country.")
        sys.exit(1) 