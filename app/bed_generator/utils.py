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
from flask import current_app
from app.models import Settings
from typing import List, Dict, Tuple, Any, Optional
from .api import fetch_variant_info, fetch_data_from_tark, fetch_coordinate_info, fetch_genes_for_panel
import datetime

# Constants
PANELS_JSON_PATH = os.path.join(os.path.dirname(__file__), 'panels.json')
GENES_JSON_PATH = os.path.join(os.path.dirname(__file__), 'genes.json')

def load_settings():
    settings = Settings.get_settings()
    return settings.to_dict()

def process_identifiers(identifiers: List[str], assembly: str, include_5utr: bool, include_3utr: bool) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Processes a list of genetic identifiers in parallel, fetching data and applying UTR and padding adjustments.
    """
    results = []
    no_data_identifiers = []
    
    print(f"\n=== Starting batch processing of {len(identifiers)} identifiers ===")
    
    # Group identifiers by type for batch processing
    rsids = []
    other_identifiers = []
    for identifier in identifiers:
        if re.match(r'^RS\d+$', identifier, re.IGNORECASE):
            rsids.append(identifier)
        else:
            other_identifiers.append(identifier)
    
    print(f"Found {len(rsids)} rsIDs and {len(other_identifiers)} other identifiers")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        future_to_id = {}
        
        # Submit rsIDs for processing
        for rsid in rsids:
            print(f"Submitting rsID: {rsid}")
            future_to_id[executor.submit(fetch_variant_info, rsid, assembly)] = rsid
        
        # Submit other identifiers for processing
        for identifier in other_identifiers:
            print(f"Submitting identifier: {identifier}")
            future_to_id[executor.submit(fetch_data_from_tark, identifier, assembly)] = identifier
        
        # Process completed futures
        for future in concurrent.futures.as_completed(future_to_id):
            identifier = future_to_id[future]
            try:
                print(f"\n=== Processing results for {identifier} ===")
                data = future.result()
                
                if data:
                    if isinstance(data, list):
                        # Handle MANE SELECT for GRCh37
                        if assembly == 'GRCh37' and not any(d.get('assembly_name') == 'GRCh37' for d in data):
                            mane_select = next((d for d in data if d.get('mane_transcript_type') == 'MANE SELECT'), None)
                            if mane_select and mane_select.get('stable_id'):
                                print(f"Attempting secondary lookup using MANE SELECT stable_id: {mane_select['stable_id']}")
                                secondary_data = fetch_data_from_tark(mane_select['stable_id'], assembly)
                                if secondary_data:
                                    if isinstance(secondary_data, list):
                                        for sd in secondary_data:
                                            sd['mane_transcript_type'] = mane_select.get('mane_transcript_type')
                                            sd['warning'] = {
                                                'type': 'version_specified',
                                                'message': f"Using GRCh37 version of MANE Select transcript"
                                            }
                                    data = secondary_data
                        
                        # Process TARK data
                        for r in data:
                            if r is None:
                                continue
                            processed_r = process_tark_data(r, include_5utr, include_3utr)
                            if processed_r:
                                print(f"Processed: Gene={processed_r.get('gene')}, EntrezID={processed_r.get('entrez_id')}")
                                results.append(processed_r)
                    else:
                        # Handle VariantInfo dataclass
                        variant_dict = {
                            'loc_region': data.loc_region,
                            'loc_start': data.loc_start,
                            'loc_end': data.loc_end,
                            'gene': data.gene,
                            'accession': data.accession,
                            'entrez_id': data.entrez_id,
                            'transcript_biotype': data.rsid,
                            'most_severe_consequence': data.most_severe_consequence,
                            'allele_string': data.allele_string,
                            'original_loc_start': data.loc_start,
                            'original_loc_end': data.loc_end,
                            'rsid': data.rsid,
                            'is_snp': True,
                            'mane_transcript_type': None
                        }
                        print(f"Processed SNP: {variant_dict['rsid']}")
                        results.append(variant_dict)
                else:
                    print(f"No data found for {identifier}")
                    no_data_identifiers.append(identifier)
            except Exception as e:
                print(f"Error processing identifier {identifier}: {e}")
                no_data_identifiers.append(identifier)
    
    print(f"\n=== Batch processing complete ===")
    print(f"Successfully processed: {len(results)} results")
    print(f"Failed to process: {len(no_data_identifiers)} identifiers")
    
    return results, no_data_identifiers

def process_tark_data(r: Dict[str, Any], include_5utr: bool, include_3utr: bool) -> Optional[Dict[str, Any]]:
    if r is None or 'loc_start' not in r or 'loc_end' not in r:
        return None

    strand = r.get('loc_strand', 1)
    
    # Store the full coordinates and UTR positions
    r['full_loc_start'] = r['loc_start']
    r['full_loc_end'] = r['loc_end']
    r['five_prime_utr_end'] = r.get('five_prime_utr', {}).get('end')
    r['three_prime_utr_start'] = r.get('three_prime_utr', {}).get('start')
    r['strand'] = strand

    # Apply initial UTR adjustments
    if strand == 1:  # Positive strand
        if not include_5utr and r['five_prime_utr_end']:
            r['loc_start'] = max(r['loc_start'], r['five_prime_utr_end'])
        if not include_3utr and r['three_prime_utr_start']:
            r['loc_end'] = min(r['loc_end'], r['three_prime_utr_start'])
    else:  # Negative strand
        if not include_5utr and r['five_prime_utr_end']:
            r['loc_end'] = min(r['loc_end'], r['five_prime_utr_end'])
        if not include_3utr and r['three_prime_utr_start']:
            r['loc_start'] = max(r['loc_start'], r['three_prime_utr_start'])
    
    return r

def process_coordinates(coordinates: List[str], assembly: str = 'GRCh38') -> List[Dict[str, Any]]:
    """
    Processes a list of genomic coordinates in parallel, fetching overlapping gene information.
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
                    # Ensure each result has the is_genomic_coordinate flag set
                    for item in data:
                        item['is_genomic_coordinate'] = True
                    results.extend(data)
            except Exception as e:
                print(f"Error processing coordinate {coord}: {e}")
    
    return results

def store_panels_in_json(panels_data: List[Dict[str, Any]]) -> None:
    """
    Stores panel data in a JSON file, formatting panel names with R-codes.
    """
    for panel in panels_data:
        panel['id'] = int(panel['id'])
        
        # Get R-code from relevant_disorders
        r_code = next((disorder for disorder in panel.get('relevant_disorders', []) 
                      if disorder.startswith('R')), '')
        
        # Format the full name
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

def collect_warnings(results: List[Dict]) -> Optional[str]:
    """
    Collects and formats warnings from results.
    """
    warnings = []
    for result in results:
        if warning := result.get('warning'):
            warnings.append({
                'identifier': result.get('identifier'),
                'message': warning.get('message'),
                'type': warning.get('type')
            })
    
    if warnings:
        return json.dumps({
            'summary': "Some transcripts require clinical review",
            'details': warnings
        })
    return None

def increment_version_number(filename: str) -> str:
    """
    Creates a new version number for an existing BED file.
    """
    match = re.search(r'_v(\d+)$', filename)
    if match:
        current_version = int(match.group(1))
        return re.sub(r'_v\d+$', f'_v{current_version + 1}', filename)
    return f"{filename}_v2"

def standardize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardizes result structure across all entry types.
    """
    standard_result = {
        # Required fields
        'loc_region': result.get('loc_region'),
        'loc_start': result.get('loc_start'),
        'loc_end': result.get('loc_end'),
        'gene': result.get('gene', 'none'),
        
        # Optional fields with defaults
        'entrez_id': result.get('entrez_id', ''),
        'accession': result.get('accession', ''),
        'exon_id': result.get('exon_id', ''),
        'exon_number': result.get('exon_number', ''),
        'transcript_biotype': result.get('transcript_biotype', ''),
        'mane_transcript': result.get('mane_transcript', ''),
        'mane_transcript_type': result.get('mane_transcript_type'),
        
        # Flags
        'is_snp': result.get('is_snp', False),
        'is_genomic_coordinate': result.get('is_genomic_coordinate', False),
        
        # Coordinate tracking
        'original_loc_start': result.get('original_loc_start', result.get('loc_start')),
        'original_loc_end': result.get('original_loc_end', result.get('loc_end')),
        
        # UTR information
        'strand': result.get('strand', 1),
        'five_prime_utr_end': result.get('five_prime_utr_end'),
        'three_prime_utr_start': result.get('three_prime_utr_start'),
        
        # Warning/status information
        'warning': result.get('warning'),
    }
    
    # Store full coordinates if available
    if 'full_loc_start' in result:
        standard_result['full_loc_start'] = result['full_loc_start']
        standard_result['full_loc_end'] = result['full_loc_end']
    
    return standard_result