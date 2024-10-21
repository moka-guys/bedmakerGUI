"""
utils.py - Provides utility functions for processing data.

Functions:
- load_settings: Loads settings from a JSON file.
- process_identifiers: Processes a list of genetic identifiers, fetching data and applying UTR and padding adjustments.
- process_single_identifier: Processes a single genetic identifier, fetching data based on its type.
- process_tark_data: Processes a single TARK data entry, adjusting for UTRs and padding.
- process_coordinates: Processes a list of genomic coordinates, fetching overlapping gene information.
- store_panels_in_json: Stores panel data in a JSON file, formatting the panel names.
- get_panels_from_json: Retrieves panel data from a JSON file.
- store_genes_in_json: Stores gene data for a specific panel in a JSON file.
- get_genes_from_json: Retrieves gene data from a JSON file.
- fetch_and_store_genes_for_panel: Fetches genes for a specific panel and stores them in a JSON file.
"""

import re
import os
import concurrent.futures
import json
from app.models import Settings
from typing import List, Dict, Tuple, Any
from .api import fetch_variant_info, fetch_data_from_tark, fetch_coordinate_info, fetch_panels_from_panelapp, fetch_genes_for_panel
import datetime

# Constants
PANELS_JSON_PATH = os.path.join(os.path.dirname(__file__), 'panels.json')
GENES_JSON_PATH = os.path.join(os.path.dirname(__file__), 'genes.json')

def load_settings():
    settings = Settings.get_settings()
    return settings.to_dict()

def process_identifiers(identifiers: List[str], assembly: str, include_5utr: bool, include_3utr: bool) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Processes a list of genetic identifiers, fetching data and applying UTR and padding adjustments.

    Args:
        identifiers: A list of genetic identifiers (e.g., rsIDs or TARK IDs).
        assembly: The genome assembly version (e.g., 'GRCh38').
        include_5utr: Whether to include the 5' UTR in the results.
        include_3utr: Whether to include the 3' UTR in the results.

    Returns:
        A tuple containing a list of processed results and a list of identifiers with no data.
    """
    results = []
    no_data_identifiers = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_id = {}
        for identifier in identifiers:
            # Determine the type of identifier and submit the appropriate fetch task
            if re.match(r'^RS\d+$', identifier, re.IGNORECASE):
                print(f"Processing rsID: {identifier}")  # Debug print
                future_to_id[executor.submit(fetch_variant_info, identifier, assembly)] = identifier
            else:
                future_to_id[executor.submit(fetch_data_from_tark, identifier, assembly)] = identifier
        
        for future in concurrent.futures.as_completed(future_to_id):
            identifier = future_to_id[future]
            try:
                data = future.result()
                if data:
                    if isinstance(data, list):
                        # Handle TARK data
                        for r in data:
                            if r is None:
                                continue
                            processed_r = process_tark_data(r, include_5utr, include_3utr)
                            if processed_r:
                                results.append(processed_r)
                    else:
                        # Handle variant data
                        print(f"Variant data for {identifier}: {data}")  # Debug print
                        results.append(data)
                else:
                    no_data_identifiers.append(identifier)
                    print(f"No data found for {identifier}")
            except Exception as e:
                print(f"Error processing identifier {identifier}: {e}")
    
    return results, no_data_identifiers

def process_tark_data(r: Dict[str, Any], include_5utr: bool, include_3utr: bool) -> Dict[str, Any]:
    """
    Processes a single TARK data entry, adjusting for UTRs and padding.
    """
    strand = r.get('loc_strand')
    
    if strand == 1:  # Positive strand
        if not include_5utr and r.get('five_prime_utr'):
            r['loc_start'] = max(r['loc_start'], r['five_prime_utr']['end'])
        if not include_3utr and r.get('three_prime_utr'):
            r['loc_end'] = min(r['loc_end'], r['three_prime_utr']['start'])
    else:  # Negative strand
        if not include_5utr and r.get('five_prime_utr'):
            r['loc_end'] = min(r['loc_end'], r['five_prime_utr']['end'])
        if not include_3utr and r.get('three_prime_utr'):
            r['loc_start'] = max(r['loc_start'], r['three_prime_utr']['start'])
    
    return r if r['loc_start'] < r['loc_end'] else None

def process_coordinates(coordinates: List[str], assembly: str = 'GRCh38') -> List[Dict[str, Any]]:
    """
    Processes a list of genomic coordinates, fetching overlapping gene information.

    Args:
        coordinates: A list of genomic coordinates in the format 'chromosome:start-end'.
        assembly: The genome assembly version (default is 'GRCh38').

    Returns:
        A list of dictionaries containing gene information for each coordinate.
    """
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_coord = {
            executor.submit(fetch_coordinate_info, coord, assembly): coord for coord in coordinates
        }
        for future in concurrent.futures.as_completed(future_to_coord):
            coord = future_to_coord[future]
            try:
                data = future.result()
                if data:
                    results.extend(data)
            except Exception as e:
                print(f"Error processing coordinate {coord}: {e}")
    
    return results

def store_panels_in_json(panels_data: List[Dict[str, Any]]) -> None:
    """
    Stores panel data in a JSON file, formatting the panel names and adding a last updated timestamp.
    """
    for panel in panels_data:
        panel['id'] = int(panel['id'])
        relevant_disorders = panel.get('relevant_disorders', [])
        r_code = relevant_disorders[-1] if relevant_disorders else ''
        panel['full_name'] = f"{r_code} - {panel['name']}" if r_code else panel['name']
    
    data_to_store = {
        'last_updated': datetime.datetime.now().isoformat(),
        'panels': panels_data
    }
    
    with open(PANELS_JSON_PATH, 'w') as json_file:
        json.dump(data_to_store, json_file, indent=2)

def get_panels_from_json() -> Tuple[List[Dict[str, Any]], str]:
    """
    Retrieves panel data and last updated timestamp from a JSON file.

    Returns:
        A tuple containing a list of dictionaries with panel information and the last updated timestamp.
    """
    if not os.path.exists(PANELS_JSON_PATH):
        return [], ''
    with open(PANELS_JSON_PATH, 'r') as json_file:
        data = json.load(json_file)
    
    if isinstance(data, list):
        # Old format: just a list of panels
        return data, ''
    elif isinstance(data, dict):
        # New format: dictionary with 'panels' and 'last_updated'
        return data.get('panels', []), data.get('last_updated', '')
    else:
        # Unexpected data format
        print(f"Unexpected data format in panels JSON: {type(data)}")
        return [], ''

def store_genes_in_json(panel_id: int, genes_data: List[Dict[str, Any]]) -> None:
    """
    Stores gene data for a specific panel in a JSON file.

    Args:
        panel_id: The ID of the panel.
        genes_data: A list of dictionaries containing gene information.
    """
    all_genes = get_genes_from_json()
    all_genes[str(panel_id)] = genes_data
    with open(GENES_JSON_PATH, 'w') as json_file:
        json.dump(all_genes, json_file, indent=2)

def get_genes_from_json() -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieves gene data from a JSON file.

    Returns:
        A dictionary mapping panel IDs to lists of gene information.
    """
    if not os.path.exists(GENES_JSON_PATH):
        return {}
    with open(GENES_JSON_PATH, 'r') as json_file:
        return json.load(json_file)

def fetch_and_store_genes_for_panel(panel_id: int) -> None:
    """
    Fetches genes for a specific panel and stores them in a JSON file.

    Args:
        panel_id: The ID of the panel.
    """
    genes = fetch_genes_for_panel(panel_id, include_amber=True, include_red=True)
    store_genes_in_json(panel_id, genes)
