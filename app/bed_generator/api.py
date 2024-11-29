"""
api.py - Fetches and processes variant information from Ensembl, TARK, and PanelApp APIs.

Functions:
- fetch_variant_info: Retrieves variant information from the Ensembl API using a given rsID and assembly.
- fetch_data_from_tark: Fetches transcript data from the TARK API based on an identifier and assembly.
- fetch_data_from_tark_with_hg38: Retrieves GRCh37 transcript data using a GRCh38 identifier.
- fetch_coordinate_info: Obtains gene overlap information for a given genomic coordinate.
- fetch_panels_from_panelapp: Retrieves signed-off gene panels from the PanelApp API.
- fetch_genes_for_panel: Fetches genes associated with a specific panel from PanelApp, filtered by confidence level.
- validate_coordinates: Validates the format of genomic coordinates from frontend.
"""

import requests
import re
from typing import Dict, List, Optional
import time
import logging
from dataclasses import dataclass
import concurrent.futures

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
ENSEMBL_GRCh38_URL = "https://rest.ensembl.org"
ENSEMBL_GRCh37_URL = "https://grch37.rest.ensembl.org"
TARK_API_URL = "https://tark.ensembl.org/api/"
PANELAPP_API_URL = "https://panelapp.genomicsengland.co.uk/api/v1/"

# Helper functions
def get_ensembl_url(assembly: str) -> str:
    """Returns the appropriate Ensembl API URL based on the given assembly version."""
    return ENSEMBL_GRCh38_URL if assembly == 'GRCh38' else ENSEMBL_GRCh37_URL

class ApiError(Exception):
    pass

class ApiClient:
    @staticmethod
    def make_api_request(url: str, params: Optional[Dict] = None, retries: int = 3) -> Optional[Dict]:
        """
        Makes a GET request to the specified URL with optional parameters and returns the JSON response.
        Implements a retry mechanism with exponential backoff for handling rate limits and server errors.

        Args:
            url (str): The URL to send the GET request to.
            params (Optional[Dict]): A dictionary of query parameters to include in the request.
            retries (int): The number of retry attempts for handling errors.

        Returns:
            Optional[Dict]: The JSON response from the API if the request is successful, otherwise None.
        """
        attempt = 0
        while attempt < retries:  # Changed from <= to < to match actual retry count
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if response.status_code in [429, 500, 502, 503, 504]:
                    attempt += 1
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"API request failed with status {response.status_code}. "
                                 f"Attempt {attempt}/{retries}. "
                                 f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    if attempt == retries:
                        logger.error(f"Max retries exceeded for URL: {url}")
                        return None
                else:
                    logger.error(f"API request failed with status {response.status_code}: {e}")
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return None
        
        return None

    @classmethod
    def get_ensembl_data(cls, url: str) -> Optional[Dict]:
        return cls.make_api_request(url)

    @classmethod
    def get_tark_data(cls, url: str, params: Dict) -> Optional[Dict]:
        return cls.make_api_request(url, params)

    @classmethod
    def get_panelapp_data(cls, url: str) -> Optional[Dict]:
        return cls.make_api_request(url)

# Main functions
@dataclass
class VariantInfo:
    rsid: str
    accession: str
    gene: str
    entrez_id: str
    loc_region: str
    loc_start: int
    loc_end: int
    allele_string: str
    most_severe_consequence: str
    transcript_biotype: str

def fetch_variant_info(rsid: str, assembly: str) -> Optional[VariantInfo]:
    """
    Fetches variant information from the Ensembl API using a given rsID and assembly.

    Args:
        rsid (str): The reference SNP ID (rsID) of the variant.
        assembly (str): The genome assembly version ('GRCh38' or 'GRCh37').

    Returns:
        Optional[VariantInfo]: A dataclass containing variant information if successful, otherwise None.
    """
    logger.info(f"Fetching variant info for {rsid} using assembly {assembly}")
    ensembl_url = f"{get_ensembl_url(assembly)}/vep/human/id/{rsid}?merged=true&content-type=application/json"
    
    # Makes the API request and checks if data is returned.
    data = ApiClient.get_ensembl_data(ensembl_url)
    if not data:
        return None

    # Extracts the first variant from the response and looks for RefSeq transcript consequences.
    variant = data[0]
    transcript_consequences = variant.get('transcript_consequences', [])
    refseq_consequence = next((c for c in transcript_consequences if c.get('source') == 'RefSeq'), None)

    # Returns a dataclass with variant details, using 'unknown' as a default for missing data.
    return VariantInfo(
        rsid=rsid,
        accession=refseq_consequence.get('transcript_id', 'unknown') if refseq_consequence else 'unknown',
        gene=refseq_consequence.get('gene_symbol', 'unknown') if refseq_consequence else 'unknown',
        entrez_id=refseq_consequence.get('hgnc_id', 'unknown') if refseq_consequence else 'unknown',
        loc_region=variant.get('seq_region_name', 'unknown'),
        loc_start=variant.get('start', 0),
        loc_end=variant.get('end', 0),
        allele_string=variant.get('allele_string', 'unknown'),
        most_severe_consequence=variant.get('most_severe_consequence', 'unknown'),
        transcript_biotype=refseq_consequence.get('consequence_terms', ['unknown'])[0] if refseq_consequence else 'unknown'
    )

def fetch_data_from_tark(identifier: str, assembly: str) -> Optional[List[Dict]]:
    """
    Fetches transcript data from TARK API with optimized request handling and parallel processing.
    """
    print(f"\n=== Fetching data for identifier: {identifier} ===")
    base_accession = identifier.split('.')[0]
    version = identifier.split('.')[1] if '.' in identifier else None
    
    search_url = f"{TARK_API_URL}transcript/search/"
    params = {
        'identifier_field': base_accession,
        'expand': 'exons,genes',
        'assembly_name': 'GRCh38' if assembly == 'GRCh38' else 'GRCh37'
    }
    
    # Make a single API call to get all transcript data
    data = ApiClient.get_tark_data(search_url, params)
    print(f"Initial TARK search result: {bool(data)}")
    
    # If we're looking for GRCh37 and either no data found or no GRCh37 transcripts
    if assembly == 'GRCh37' and (not data or not any(t for t in data if t['assembly'] == 'GRCh37')):
        # Try Ensembl gene symbol lookup as fallback
        ensembl_url = f"https://rest.ensembl.org/xrefs/symbol/homo_sapiens/{identifier}?content-type=application/json"
        print(f"Trying Ensembl lookup URL: {ensembl_url}")
        ensembl_data = ApiClient.get_ensembl_data(ensembl_url)
        print(f"Ensembl lookup response: {ensembl_data}")
        
        if ensembl_data and len(ensembl_data) > 0:
            ensembl_id = ensembl_data[0].get('id')
            print(f"Found Ensembl ID: {ensembl_id}")
            if ensembl_id:
                # Try TARK search with Ensembl ID
                params['identifier_field'] = ensembl_id
                print(f"Trying TARK search with Ensembl ID. URL: {search_url}, Params: {params}")
                new_data = ApiClient.get_tark_data(search_url, params)
                print(f"TARK search with Ensembl ID result: {bool(new_data)}")
                if new_data:
                    logger.info(f"Found transcript data using Ensembl ID lookup for {identifier}")
                    # Add warning about using Ensembl ID lookup
                    for transcript in new_data:
                        transcript['warning'] = {
                            'message': f"Transcript found via Ensembl gene symbol lookup - clinical review recommended",
                            'identifier': identifier,
                            'type': 'ensembl_lookup'
                        }
                    data = new_data

    if not data or (assembly == 'GRCh37' and not any(t for t in data if t['assembly'] == 'GRCh37')):
        print("No data found after all attempts")
        return None
        
    # Filter and process transcripts based on assembly and version
    transcripts = select_transcripts(data, assembly, version)
    
    # If no transcripts found for GRCh37, try parallel processing of alternatives
    if not transcripts and assembly == 'GRCh37':
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            
            # Try finding matching GRCh38 MANE SELECT
            futures.append(executor.submit(
                process_grch38_mane_select,
                data, base_accession, identifier
            ))
            
            # Try with base accession in parallel
            futures.append(executor.submit(
                process_base_accession,
                data, base_accession, identifier
            ))
            
            # Use the first successful result
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        return result
                except Exception as e:
                    logger.error(f"Error in parallel processing: {e}")
                    continue
    
    return process_transcripts(transcripts, base_accession)

def process_grch38_mane_select(data: List[Dict], base_accession: str, identifier: str) -> Optional[List[Dict]]:
    """Helper function to process GRCh38 MANE SELECT transcripts."""
    grch38_transcripts = [t for t in data if t['assembly'] == 'GRCh38']
    mane_select = next((t for t in grch38_transcripts 
                      if t.get('mane_transcript_type') == 'MANE SELECT'), None)
    
    if mane_select:
        warning = {
            'message': f"No direct GRCh37 transcript found. Using GRCh38 MANE SELECT transcript {mane_select['stable_id']} to find matching GRCh37 version",
            'identifier': identifier,
            'type': 'assembly_mapping'
        }
        matching_grch37 = [t for t in data 
                         if t['assembly'] == 'GRCh37' 
                         and t['stable_id'] == mane_select['stable_id']]
        
        if matching_grch37:
            selected = max(matching_grch37, 
                         key=lambda x: int(x.get('stable_id_version', 0)))
            selected['warning'] = warning
            return process_transcripts([selected], base_accession)
    return None

def process_base_accession(data: List[Dict], base_accession: str, identifier: str) -> Optional[List[Dict]]:
    """Helper function to process base accession transcripts."""
    warning = {
        'message': "No MANE SELECT transcript found. Using base accession for GRCh37 lookup - clinical review recommended",
        'identifier': identifier,
        'type': 'assembly_mapping'
    }
    grch37_transcripts = [t for t in data if t['assembly'] == 'GRCh37']
    if grch37_transcripts:
        selected = max(grch37_transcripts, 
                     key=lambda x: int(x.get('stable_id_version', 0)))
        selected['warning'] = warning
        return process_transcripts([selected], base_accession)
    return None

def select_transcripts(data: List[Dict], assembly: str, version: Optional[str] = None) -> List[Dict]:
    """
    Selects the most relevant transcripts from the provided data based on the assembly and version.
    """
    # Filters transcripts based on assembly and stable ID prefix (NM or NR).
    assembly_transcripts = [item for item in data if item['assembly'] == assembly and (item['stable_id'].startswith('NM') or item['stable_id'].startswith('NR'))]
    
    # If version is specified, filter for exact version match
    if version:
        versioned_transcripts = [t for t in assembly_transcripts if str(t['stable_id_version']) == version]
        if versioned_transcripts:
            selected = versioned_transcripts[0]
            identifier = f"{selected['stable_id']}.{selected['stable_id_version']}"
            # Only add warning if this is a user-specified version
            if '.' in identifier:  # This indicates user specified a version
                selected['warning'] = {
                    'message': "Version specified by user",
                    'identifier': identifier,
                    'type': 'version_specified'
                }
            selected.pop('mane_transcript_type', None)
            return [selected]

    if assembly == 'GRCh38':
        # Prioritises MANE transcripts if available for GRCh38.
        mane_transcripts = [t for t in assembly_transcripts if t.get('mane_transcript_type') in ['MANE PLUS CLINICAL', 'MANE SELECT']]
        if mane_transcripts:
            return mane_transcripts
    elif assembly == 'GRCh37':
        # For GRCh37, find the corresponding MANE transcript in GRCh38 to ensure consistency
        grch38_mane = next((t for t in data if t['assembly'] == 'GRCh38' and 
                            t.get('mane_transcript_type') in ['MANE PLUS CLINICAL', 'MANE SELECT'] and 
                            t['stable_id'].startswith('NM')), None)
        if grch38_mane:
            matching_grch37 = [t for t in assembly_transcripts if t['stable_id'] == grch38_mane['stable_id']]
            if matching_grch37:
                selected = max(matching_grch37, key=lambda x: int(x['stable_id_version']))
                identifier = f"{selected['stable_id']}.{selected['stable_id_version']}"
                selected['warning'] = {
                    'message': f"Transcript selected based on GRCh38 MANE transcript {grch38_mane['stable_id']}.{grch38_mane['stable_id_version']}",
                    'identifier': identifier,
                    'type': 'transcript_selection'
                }
                return [selected]

    # If no MANE transcripts or matching GRCh37 transcript
    if assembly_transcripts:
        # Add null check and default to 0 if version is missing or invalid
        def get_version(transcript):
            try:
                return int(transcript.get('stable_id_version', 0))
            except (TypeError, ValueError):
                return 0
                
        selected = max(assembly_transcripts, key=get_version)
        identifier = f"{selected['stable_id']}.{selected['stable_id_version']}"
        selected['warning'] = {
            'message': "No MANE transcript available. Selected highest version number - clinical review recommended",
            'identifier': identifier,
            'type': 'transcript_selection'
        }
        return [selected]
    
    return []

def process_transcripts(transcripts: List[Dict], identifier: str) -> List[Dict]:
    results = []
    for transcript in transcripts:
        if not transcript:
            continue

        print(f"\nProcessing transcript: {transcript.get('stable_id')}")
        print(f"Assembly: {transcript.get('assembly')}")
        
        # Get Ensembl ID and Entrez ID from genes data
        ensembl_id = None
        entrez_id = None
        if transcript.get('genes'):
            for gene in transcript['genes']:
                if gene.get('ensembl_id'):
                    ensembl_id = gene['ensembl_id']
                    entrez_id = gene['ensembl_id']
                    break
                elif gene.get('stable_id'):
                    ensembl_id = gene['stable_id']
                    entrez_id = gene['stable_id']
                    break

        # Handle MANE transcript and type based on assembly
        assembly = transcript.get('assembly')
        mane_transcript = ''
        mane_transcript_type = None
        if assembly == 'GRCh38':
            mane_transcript = transcript.get('mane_transcript', '')
            mane_transcript_type = transcript.get('mane_transcript_type', '')
        
        print(f"Found Ensembl ID from genes: {ensembl_id}")
        print(f"Found Entrez ID from genes: {entrez_id}")
        print(f"MANE transcript (only for GRCh38): {mane_transcript}")
        print(f"MANE transcript type (only for GRCh38): {mane_transcript_type}")

        # Build the result dictionary
        for index, exon in enumerate(transcript.get('exons', []), start=1):
            result = {
                'loc_region': exon['loc_region'],
                'loc_start': exon['loc_start'],
                'loc_end': exon['loc_end'],
                'loc_strand': exon['loc_strand'],
                'accession': f"{transcript['stable_id']}.{transcript['stable_id_version']}",
                'ensembl_id': ensembl_id,
                'gene': next((gene['name'] for gene in transcript.get('genes', []) if gene['name']), identifier),
                'entrez_id': entrez_id,
                'exon_id': exon['stable_id'],
                'exon_number': index,
                'transcript_biotype': transcript.get('biotype', ''),
                'mane_transcript': mane_transcript,
                'mane_transcript_type': mane_transcript_type,
                'status': None,  # Initialize status as None
                'identifier': identifier,
                'five_prime_utr': {
                    'start': transcript.get('five_prime_utr_start'),
                    'end': transcript.get('five_prime_utr_end')
                },
                'three_prime_utr': {
                    'start': transcript.get('three_prime_utr_start'),
                    'end': transcript.get('three_prime_utr_end')
                }
            }
            
            # Set status based on MANE type if present, handling case-insensitively
            if mane_transcript_type:
                mane_type_upper = mane_transcript_type.upper()
                if mane_type_upper == 'MANE SELECT':
                    result['status'] = 'MANE Select transcript'
                elif mane_type_upper == 'MANE PLUS CLINICAL':
                    result['status'] = 'MANE Plus Clinical transcript'
            elif transcript.get('warning'):
                result['status'] = transcript['warning'].get('message') if isinstance(transcript['warning'], dict) else transcript['warning']
            
            results.append(result)

        print(f"Final result for transcript: {results[-1]}")

    return results

def fetch_data_from_tark_with_hg38(hg38_identifier: str, warning: Optional[Dict] = None) -> Optional[List[Dict]]:
    """
    Retrieves GRCh37 transcript data using a GRCh38 identifier.

    Args:
        hg38_identifier (str): The GRCh38 identifier for the transcript.
        warning (Optional[Dict]): Warning to propagate to the results.

    Returns:
        Optional[List[Dict]]: A list of dictionaries containing GRCh37 transcript data if successful, otherwise None.
    """
    search_url = f"{TARK_API_URL}transcript/search/"
    params = {
        'identifier_field': hg38_identifier,
        'expand': 'exons,genes'
    }

    data = ApiClient.get_tark_data(search_url, params)
    if not data:
        return None

    hg37_transcripts = [max((item for item in data if item['assembly'] == 'GRCh37'), key=lambda x: int(x['stable_id_version']), default=None)]
    gene_name = next((gene['name'] for item in data for gene in item.get('genes', []) if gene['name']), None)

    if warning:
        for transcript in hg37_transcripts:
            if transcript:
                transcript['warning'] = warning

    return process_transcripts(hg37_transcripts, gene_name or hg38_identifier)

def fetch_coordinate_info(coord: str, assembly: str) -> List[Dict]:
    """
    Obtains gene overlap information for a given genomic coordinate.

    Args:
        coord (str): The genomic coordinate in the format 'chromosome:start-end'.
        assembly (str): The genome assembly version ('GRCh38' or 'GRCh37').

    Returns:
        List[Dict]: A list of dictionaries containing gene overlap information.
    """
    # Validates the coordinate format and raises an error if invalid.
    error = validate_coordinates(coord)
    if error:
        raise ValueError(error)

    # Parses the coordinate string into chromosome, start, and end positions.
    chrom, pos = coord.split(':')
    chrom = chrom.lstrip('chr')
    start, end = map(int, pos.split('-'))

    logger.info(get_ensembl_url(assembly))
    logger.info(f"{chrom} {start} {end}")
    
    # Constructs the URL for the Ensembl API request to get gene overlap information.
    ensembl_url = f"{get_ensembl_url(assembly)}/overlap/region/human/{chrom}:{start}-{end}?feature=gene;content-type=application/json"
    
    # Makes the API request and processes the response.
    data = ApiClient.get_ensembl_data(ensembl_url)
    if not data:
        return [{
            'loc_region': chrom,
            'loc_start': start,
            'loc_end': end,
            'accession': 'N/A',
            'gene': 'N/A',
            'entrez_id': 'N/A',
            'biotype': 'N/A',
            'strand': 'N/A',
        }]

    return process_coordinate_data(data, chrom, start, end, coord)

def process_coordinate_data(data: List[Dict], chrom: str, start: int, end: int, coord: str) -> List[Dict]:
    """
    Processes coordinate data to extract relevant gene overlap information.

    Args:
        data (List[Dict]): A list of feature data dictionaries.
        chrom (str): The chromosome name.
        start (int): The start position of the coordinate.
        end (int): The end position of the coordinate.
        coord (str): The original coordinate string.

    Returns:
        List[Dict]: A list of dictionaries containing processed gene overlap information.
    """
    valid_features = []
    unknown_features = []

    for feature in data:
        feature_entry = {
            'loc_region': chrom,
            'loc_start': start,
            'loc_end': end,
            'accession': feature.get('id', 'unknown_id'),
            'gene': feature.get('external_name', 'unknown_gene'),
            'entrez_id': feature.get('id', 'unknown_id'),
            'biotype': feature.get('biotype', 'unknown_biotype'),
            'strand': feature.get('strand', 1),
            'alert': '',
            'is_genomic_coordinate': True
        }
        
        # Separates known and unknown gene features.
        if feature_entry['gene'] != 'unknown_gene':
            valid_features.append(feature_entry)
        else:
            unknown_features.append(feature_entry)

    # Adds alerts if multiple genes or unknown genes overlap the coordinate.
    if valid_features:
        if len(valid_features) > 1:
            for feature in valid_features:
                feature['alert'] = f"Coordinate {coord} overlaps multiple genes."
        return valid_features
    elif unknown_features:
        if len(unknown_features) > 1:
            for feature in unknown_features:
                feature['alert'] = f"Coordinate {coord} overlaps multiple uncharacterised genomic regions with the VEP API."
        return unknown_features
    else:
        return [{
            'loc_region': chrom,
            'loc_start': start,
            'loc_end': end,
            'accession': 'none',
            'gene': 'none',
            'entrez_id': 'none',
            'biotype': 'none',
            'strand': 'none',
            'alert': f"No genes found overlapping coordinate {coord}."
        }]

def fetch_panels_from_panelapp():
    """
    Fetches panel data from PanelApp API, handling pagination.
    """
    panels_list = []
    next_url = "https://panelapp.genomicsengland.co.uk/api/v1/panels/signedoff/"
    
    while next_url:
        try:
            response = requests.get(next_url)
            response.raise_for_status()
            data = response.json()
            
            panels_list.extend(data['results'])
            next_url = data.get('next')
            
        except requests.RequestException as e:
            current_app.logger.error(f"Error fetching panels from PanelApp: {str(e)}")
            break
    
    return panels_list

def fetch_genes_for_panel(panel_id: int, include_amber: bool, include_red: bool) -> List[Dict]:
    """
    Fetches genes associated with a specific panel from PanelApp, filtered by confidence level.

    Args:
        panel_id (int): The ID of the panel.
        include_amber (bool): Whether to include genes with amber confidence level.
        include_red (bool): Whether to include genes with red confidence level.

    Returns:
        List[Dict]: A list of dictionaries containing gene information.
    """
    url = f"{PANELAPP_API_URL}panels/{panel_id}/"
    data = ApiClient.get_panelapp_data(url)
    if not data:
        return []

    confidence_levels = ['3'] + (['2'] if include_amber else []) + (['1'] if include_red else [])
    return [{'symbol': gene['gene_data']['gene_symbol'], 'confidence': gene['confidence_level']} 
            for gene in data['genes'] if gene['confidence_level'] in confidence_levels]

def validate_coordinates(coordinates: str) -> Optional[str]:
    """
    Validates the format of genomic coordinates from frontend.

    Args:
        coordinates (str): The genomic coordinates in the format 'chromosome:start-end'.

    Returns:
        Optional[str]: An error message if the format is invalid, otherwise None.
    """
    # Validates the coordinate format using a regular expression.
    regex = r'^(chr)?([1-9][0-9]?|[XYM]):(\d+)-(\d+)$'
    match = re.match(regex, coordinates, re.IGNORECASE)

    if not match:
        return "Invalid format. Use 'chromosome:start-end' (e.g., 1:200-300 or chr1:200-300)."

    start, end = int(match.group(3)), int(match.group(4))

    # Ensures the end position is not less than the start position
    if start > end:
        return "End position cannot be less than start position."

    return None

def get_transcript_data(identifier: str) -> List[Dict]:
    """Gets transcript data from Tark API."""
    # Check if identifier includes a version
    if '.' in identifier and any(identifier.startswith(prefix) for prefix in ['NM_', 'NR_']):
        # Use the direct versioned transcript endpoint
        url = f"{TARK_API_BASE}/transcript/stable_id_with_version/?stable_id_with_version={identifier}"
        response = requests.get(url)
        if response.ok:
            data = response.json()
            # Versioned endpoint returns a single transcript, but keep the list format
            # for consistency with the rest of the code
            return [data] if data else []
    
    # For non-versioned identifiers, use the existing endpoint
    url = f"{TARK_API_BASE}/transcript/stable_id/{identifier}/"
    response = requests.get(url)
    if response.ok:
        return response.json()
    return []