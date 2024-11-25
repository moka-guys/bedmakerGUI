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
    Fetches transcript data from the TARK API based on an identifier and assembly.

    Args:
        identifier (str): The identifier for the transcript (can include version, e.g., NM_004329.3).
        assembly (str): The genome assembly version ('GRCh38' or 'GRCh37').

    Returns:
        Optional[List[Dict]]: A list of dictionaries containing transcript data if successful, otherwise None.
    """
    base_accession = identifier.split('.')[0]
    version = identifier.split('.')[1] if '.' in identifier else None
    user_specified_version = '.' in identifier  # Add this flag

    search_url = f"{TARK_API_URL}transcript/search/"
    params = {
        'identifier_field': base_accession,
        'expand': 'exons,genes',
        'assembly_name': 'GRCh38' if assembly == 'GRCh38' else 'GRCh37'
    }

    # If version specified, first try to get exact version match
    if version:
        version_params = {**params, 'stable_id_version': version}
        data = ApiClient.get_tark_data(search_url, version_params)
        if data:
            exact_matches = [t for t in data if 
                           t['stable_id'] == base_accession and 
                           str(t['stable_id_version']) == version and
                           t['assembly'] == params['assembly_name']]
            if exact_matches:
                # Only add warning if user specified the version
                if user_specified_version:
                    for match in exact_matches:
                        match['warning'] = {
                            'type': 'version_specified',
                            'message': 'Version specified by user',
                            'identifier': identifier
                        }
                return process_transcripts(exact_matches, identifier)

    # If no exact match found or no version specified, proceed with base accession search
    data = ApiClient.get_tark_data(search_url, params)
    if not data:
        return None

    transcripts = select_transcripts(data, assembly, version)
    if not transcripts and assembly == 'GRCh37':
        # First try to get GRCh38 data to find MANE SELECT
        grch38_params = {**params, 'assembly_name': 'GRCh38'}
        grch38_data = ApiClient.get_tark_data(search_url, grch38_params)
        if grch38_data:
            grch38_transcripts = select_transcripts(grch38_data, 'GRCh38', version)
            mane_select = next((t for t in grch38_transcripts if t.get('mane_transcript_type') == 'MANE SELECT'), None)
            if mane_select:
                warning = {
                    'message': f"No direct GRCh37 transcript found. Using GRCh38 MANE SELECT transcript {mane_select['stable_id']} to find matching GRCh37 version",
                    'identifier': identifier,
                    'type': 'assembly_mapping'
                }
                return fetch_data_from_tark_with_hg38(mane_select['stable_id'], warning)
        
        # If no MANE SELECT found, try with base accession with a warning
        warning = {
            'message': "No MANE SELECT transcript found. Using base accession for GRCh37 lookup - clinical review recommended",
            'identifier': identifier,
            'type': 'assembly_mapping'
        }
        return fetch_data_from_tark_with_hg38(base_accession, warning)

    return process_transcripts(transcripts, base_accession)

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
                    'message': "Transcript selected based on best available GRCh38 MANE transcript match",
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

        # Determine the status message
        status = None
        if transcript.get('mane_transcript_type'):
            # Standardize MANE status format
            if 'PLUS CLINICAL' in transcript['mane_transcript_type'].upper():
                status = 'MANE Plus Clinical'
            elif 'SELECT' in transcript['mane_transcript_type'].upper():
                status = 'MANE Select'
        elif transcript.get('warning'):
            # Use warning message as status if no MANE type
            status = transcript['warning'].get('message')

        # Build the result dictionary
        for index, exon in enumerate(transcript.get('exons', []), start=1):
            results.append({
                'loc_region': exon['loc_region'],
                'loc_start': exon['loc_start'],
                'loc_end': exon['loc_end'],
                'loc_strand': exon['loc_strand'],
                'accession': f"{transcript['stable_id']}.{transcript['stable_id_version']}",
                'ensembl_id': transcript.get('ensembl_stable_id'),
                'gene': next((gene['name'] for gene in transcript.get('genes', []) if gene['name']), identifier),
                'entrez_id': None,
                'exon_id': exon['stable_id'],
                'exon_number': index,
                'transcript_biotype': transcript.get('biotype', ''),
                'mane_transcript': transcript.get('mane_transcript', ''),
                'status': status,
                'identifier': identifier,
                'five_prime_utr': {
                    'start': transcript.get('five_prime_utr_start'),
                    'end': transcript.get('five_prime_utr_end')
                },
                'three_prime_utr': {
                    'start': transcript.get('three_prime_utr_start'),
                    'end': transcript.get('three_prime_utr_end')
                }
            })

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

def fetch_panels_from_panelapp() -> List[Dict]:
    """
    Retrieves signed-off gene panels from the PanelApp API.

    Returns:
        List[Dict]: A list of dictionaries containing panel information.
    """
    url = f"{PANELAPP_API_URL}panels/signedoff/"
    panels_list = []
    logger.info(f"Fetching panels from {url}")

    while url:
        logger.info(f"Fetching from {url}")
        data = ApiClient.get_panelapp_data(url)
        if not data:
            logger.info("No data received from API")
            break

        logger.info(f"Received {len(data['results'])} panels")
        for panel in data['results']:
            panel_data = {
                'id': panel['id'],
                'name': panel['name'],
                'disease_group': panel.get('disease_group', ''),
                'disease_sub_group': panel.get('disease_sub_group', ''),
                'relevant_disorders': panel.get('relevant_disorders', []),
                'version': panel['version'],
                'version_created': panel['version_created'],
                'genes': fetch_genes_for_panel(panel['id'], include_amber=True, include_red=True)
            }
            panels_list.append(panel_data)
        
        url = data.get('next')

    logger.info(f"Total panels fetched: {len(panels_list)}")
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
            # The versioned endpoint returns a single transcript, but we'll keep the list format
            # for consistency with the rest of the code
            return [data] if data else []
    
    # For non-versioned identifiers, use the existing endpoint
    url = f"{TARK_API_BASE}/transcript/stable_id/{identifier}/"
    response = requests.get(url)
    if response.ok:
        return response.json()
    return []