import requests
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
ENSEMBL_GRCh38_URL = "https://rest.ensembl.org"
ENSEMBL_GRCh37_URL = "https://grch37.rest.ensembl.org"

def get_ensembl_url(assembly: str) -> str:
    """Returns the appropriate Ensembl API URL based on the given assembly version."""
    return ENSEMBL_GRCh38_URL if assembly == 'GRCh38' else ENSEMBL_GRCh37_URL

class ApiError(Exception):
    pass

class ApiClient:
    @staticmethod
    def make_api_request(url: str, params: Optional[Dict] = None, retries: int = 3) -> Optional[Dict]:
        """Makes a GET request with retry logic."""
        headers = {"Content-Type": "application/json"}
        attempt = 0
        while attempt < retries:
            try:
                response = requests.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if response.status_code in [429, 500, 502, 503, 504]:
                    attempt += 1
                    wait_time = 2 ** attempt
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
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return None
        return None

def fetch_transcript_info(identifier: str, assembly: str = 'GRCh38') -> Optional[List[Dict]]:
    """
    Fetches transcript information using Ensembl REST API.
    
    Args:
        identifier (str): RefSeq transcript ID (e.g., 'NM_000546')
        assembly (str): Genome assembly ('GRCh38' or 'GRCh37')
    
    Returns:
        Optional[List[Dict]]: List of transcript information dictionaries
    """
    logger.info(f"Fetching transcript info for {identifier} using {assembly}")
    
    base_accession = identifier.split('.')[0]
    version = identifier.split('.')[1] if '.' in identifier else None
    
    # First try to get transcript info directly
    ensembl_base = get_ensembl_url(assembly)
    xref_url = f"{ensembl_base}/xrefs/symbol/homo_sapiens/{base_accession}?external_db=RefSeq_mRNA"
    
    xref_data = ApiClient.make_api_request(xref_url)
    if not xref_data:
        logger.warning(f"No xref data found for {identifier}")
        return None

    results = []
    for xref in xref_data:
        ensembl_id = xref.get('id')
        if not ensembl_id:
            continue

        # Get detailed transcript information
        lookup_url = f"{ensembl_base}/lookup/id/{ensembl_id}?expand=1"
        transcript_data = ApiClient.make_api_request(lookup_url)
        
        if not transcript_data:
            continue

        # Additional request for UTR information
        utr_url = f"{ensembl_base}/lookup/id/{ensembl_id}?expand=1&utr=1"
        utr_data = ApiClient.make_api_request(utr_url)

        # Build result dictionary
        result = {
            'stable_id': base_accession,
            'stable_id_version': version or transcript_data.get('version', '1'),
            'assembly': assembly,
            'biotype': transcript_data.get('biotype'),
            'genes': [{
                'name': transcript_data.get('display_name'),
                'ensembl_id': transcript_data.get('id'),
                'stable_id': transcript_data.get('id')
            }],
            'exons': [],
            'utrs': {
                '5_prime_utr': [],
                '3_prime_utr': []
            }
        }

        # Process exons
        if 'Exon' in transcript_data:
            for idx, exon in enumerate(transcript_data['Exon'], 1):
                result['exons'].append({
                    'stable_id': exon.get('id'),
                    'loc_region': exon.get('seq_region_name'),
                    'loc_start': exon.get('start'),
                    'loc_end': exon.get('end'),
                    'loc_strand': exon.get('strand'),
                    'rank': idx
                })

        # Process UTRs if available
        if utr_data:
            if 'UTR' in utr_data:
                for utr in utr_data['UTR']:
                    utr_info = {
                        'loc_region': utr.get('seq_region_name'),
                        'loc_start': utr.get('start'),
                        'loc_end': utr.get('end'),
                        'loc_strand': utr.get('strand')
                    }
                    
                    # Determine UTR type based on object_type
                    if utr.get('object_type') == 'five_prime_UTR':
                        result['utrs']['5_prime_utr'].append(utr_info)
                    elif utr.get('object_type') == 'three_prime_UTR':
                        result['utrs']['3_prime_utr'].append(utr_info)

        # Add MANE information for GRCh38
        if assembly == 'GRCh38':
            mane_status = None
            if transcript_data.get('MANE'):
                mane_status = 'MANE SELECT' if transcript_data['MANE'].get('status') == 'MANE_Select' else 'MANE PLUS CLINICAL'
            result['mane_transcript_type'] = mane_status

        results.append(result)

    return results

def main():
    """
    Process transcript information based on command-line input.
    Usage: python test.py NM_000546
    """
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python test.py <transcript_id>")
        print("Example: python test.py NM_000546")
        sys.exit(1)
        
    identifier = sys.argv[1]
    assembly = 'GRCh37'  # Default to GRCh37/hg19
    
    print(f"\nProcessing {identifier} in {assembly}")
    results = fetch_transcript_info(identifier, assembly)
    
    if results:
        print(f"Found {len(results)} transcript(s)")
        for result in results:
            print("\nTranscript details:")
            print(f"Stable ID: {result['stable_id']}.{result['stable_id_version']}")
            print(f"Biotype: {result['biotype']}")
            print(f"Gene name: {result['genes'][0]['name']}")
            print(f"Number of exons: {len(result['exons'])}")
            
            # Print exon coordinates
            print("\nExon coordinates:")
            for exon in result['exons']:
                print(f"Exon {exon['rank']}: "
                      f"chr{exon['loc_region']}:"
                      f"{exon['loc_start']}-{exon['loc_end']} "
                      f"(strand: {exon['loc_strand']})")
            
            # Print UTR coordinates
            print("\nUTR coordinates:")
            if result['utrs']['5_prime_utr']:
                print("5' UTR regions:")
                for utr in result['utrs']['5_prime_utr']:
                    print(f"chr{utr['loc_region']}:"
                          f"{utr['loc_start']}-{utr['loc_end']} "
                          f"(strand: {utr['loc_strand']})")
            
            if result['utrs']['3_prime_utr']:
                print("3' UTR regions:")
                for utr in result['utrs']['3_prime_utr']:
                    print(f"chr{utr['loc_region']}:"
                          f"{utr['loc_start']}-{utr['loc_end']} "
                          f"(strand: {utr['loc_strand']})")
    else:
        print(f"No results found for {identifier}")

if __name__ == "__main__":
    main()