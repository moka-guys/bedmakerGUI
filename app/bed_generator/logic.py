"""
logic.py Core logic for processing genetic data in the bed generator application for processing data.

Functions:
- process_form_data(form): Processes form data to extract and process genetic identifiers and coordinates.
- store_results_in_session(results, no_data_identifiers, assembly, initial_query): Stores processed results in the session.
- process_bulk_data(data): Processes bulk genetic data from a dictionary input.
- get_mane_plus_clinical_identifiers(results): Retrieves identifiers marked as 'MANE PLUS CLINICAL' from results.
- generate_bed_file(bed_type, results, filename_prefix, settings, add_chr_prefix=False): Generates a BED file of a specified type using processed results and settings.
"""

from app import db
from app.models import Settings
from .utils import process_identifiers, process_coordinates
from .bed_generator import BedGenerator
import re
from flask import session
from .api import validate_coordinates
from typing import List, Tuple, Dict, Any, Set
from flask_wtf import FlaskForm
from app.bed_generator.utils import process_tark_data

def process_form_data(form: FlaskForm) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """
    Processes form data to extract and process genetic identifiers and coordinates.

    Args:
        form: The form object containing user input data.

    Returns:
        A tuple containing:
        - results: A list of processed genetic data entries.
        - no_data_identifiers: A list of identifiers for which no data was found.
        - initial_query: The initial query made from the frontend.
    """
    results = []
    no_data_identifiers = []
    
    initial_query = {
        'identifiers': form.identifiers.data.split() if form.identifiers.data else [],
        'coordinates': form.coordinates.data.split('\n') if form.coordinates.data else [],
        'assembly': form.assembly.data,
        'include5UTR': form.include5UTR.data,
        'include3UTR': form.include3UTR.data
    }
    
    if form.identifiers.data:
        processed_results, no_data = process_identifiers(
            form.identifiers.data.split(),
            form.assembly.data,
            form.include5UTR.data,
            form.include3UTR.data
        )
        results.extend([r for r in processed_results if isinstance(r, dict)])
        no_data_identifiers.extend(no_data)
    
    if form.coordinates.data:
        processed_coordinates = process_coordinates(form.coordinates.data.split('\n'), form.assembly.data)
        results.extend([r for r in processed_coordinates if isinstance(r, dict)])
    
    return results, no_data_identifiers, initial_query

def store_results_in_session(results: List[Dict[str, Any]], no_data_identifiers: List[str], assembly: str, initial_query: Dict[str, Any]) -> None:
    """
    Stores processed results in the session.

    Args:
        results: A list of processed genetic data entries.
        no_data_identifiers: A list of identifiers for which no data was found.
        assembly: The genome assembly version used for processing.
        initial_query: The initial query made from the frontend.
    """
    session['results'] = results
    session['no_data_identifiers'] = no_data_identifiers
    session['assembly'] = assembly
    session['initial_query'] = initial_query

def process_bulk_data(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Processes bulk genetic data from a dictionary input.

    Args:
        data: A dictionary containing identifiers and coordinates to process.

    Returns:
        A tuple containing:
        - results: A list of processed genetic data entries.
        - no_data_identifiers: A list of identifiers for which no data was found.

    Raises:
        ValueError: If any coordinate is invalid.
    """
    results = []
    no_data_identifiers = []
    
    if data.get('identifiers'):
        processed_results, no_data = process_identifiers(
            data['identifiers'],
            data.get('assembly', 'GRCh38'),
            data.get('include5UTR', False),
            data.get('include3UTR', False)
        )
        # Flatten the processed results
        for result in processed_results:
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
        no_data_identifiers.extend(no_data)
    
    if data.get('coordinates'):
        coordinate_list = [coord.strip() for coord in re.split(r'[,\n]', data['coordinates']) if coord.strip()]
        for coord in coordinate_list:
            error = validate_coordinates(coord)
            if error:
                raise ValueError(error)
        processed_coordinates = process_coordinates(coordinate_list, data.get('assembly', 'GRCh38'))
        # Flatten the processed coordinates
        for coord in processed_coordinates:
            if isinstance(coord, list):
                results.extend(coord)
            else:
                results.append(coord)
    
    # Sort results before returning
    results = sort_results(results)
    return results, no_data_identifiers

def get_mane_plus_clinical_identifiers(results: List[Dict[str, Any]]) -> Set[str]:
    """
    Retrieves identifiers marked as 'MANE PLUS CLINICAL' from results.

    Args:
        results: A list of processed genetic data entries.

    Returns:
        A set of gene identifiers marked as 'MANE PLUS CLINICAL'.
    """
    return set(
        result.get('gene', 'Unknown')
        for result in results
        if isinstance(result, dict) and result.get('mane_transcript_type') == 'MANE PLUS CLINICAL'
    )

def generate_bed_file(bed_type: str, results: List[Dict[str, Any]], filename_prefix: str, settings: Dict[str, Any], add_chr_prefix: bool) -> Tuple[str, str]:
    """
    Generates a BED file of a specified type using processed results and settings.

    Args:
        bed_type: The type of BED file to generate ('raw', 'data', 'sambamba', 'exomeDepth', or 'cnv').
        results: A list of processed genetic data entries.
        filename_prefix: A prefix to use for the generated filename.
        settings: A dictionary containing padding settings for different BED types.
        add_chr_prefix: Whether to add 'chr' prefix to chromosome names.

    Returns:
        A tuple containing:
        - bed_content: The content of the generated BED file as a string.
        - filename: The filename for the generated BED file.

    Raises:
        ValueError: If an invalid BED type is specified.
    """
    if bed_type == 'raw':
        bed_content = BedGenerator.create_raw_bed(results, add_chr_prefix)
        filename = f'{filename_prefix}_raw.bed' if filename_prefix else 'raw.bed'
    else:
        # Map bed_type to settings
        padding_map = {
            'data': settings.get('data_padding', 0),
            'sambamba': settings.get('sambamba_padding', 0),
            'exome_depth': settings.get('exomeDepth_padding', 0),
            'cnv': settings.get('cnv_padding', 0)
        }
        
        # Map bed_type to UTR settings
        utr_settings = {
            'data': (settings.get('data_include_5utr', False), settings.get('data_include_3utr', False)),
            'sambamba': (settings.get('sambamba_include_5utr', False), settings.get('sambamba_include_3utr', False)),
            'exome_depth': (settings.get('exomeDepth_include_5utr', False), settings.get('exomeDepth_include_3utr', False)),
            'cnv': (settings.get('cnv_include_5utr', False), settings.get('cnv_include_3utr', False))
        }
        
        padding = padding_map.get(bed_type.lower(), 0)
        include_5utr, include_3utr = utr_settings.get(bed_type.lower(), (False, False))
        
        # Process results with UTR settings using existing UTR data
        processed_results = []
        for result in results:
            if result.get('is_genomic_coordinate', False):
                processed_results.append(result.copy())
                continue
                
            processed = result.copy()
            if 'full_loc_start' in result and 'full_loc_end' in result:
                # Start with full coordinates
                new_start = result['full_loc_start']
                new_end = result['full_loc_end']

                if result.get('strand', 1) == 1:  # Positive strand
                    if not include_5utr and result.get('five_prime_utr_end'):
                        new_start = max(new_start, int(result['five_prime_utr_end']))
                    if not include_3utr and result.get('three_prime_utr_start'):
                        new_end = min(new_end, int(result['three_prime_utr_start']))
                else:  # Negative strand
                    if not include_5utr and result.get('five_prime_utr_end'):
                        # For negative strand, 5' UTR is at the 3' end
                        new_end = min(new_end, int(result['five_prime_utr_end']))
                    if not include_3utr and result.get('three_prime_utr_start'):
                        # For negative strand, 3' UTR is at the 5' end
                        new_start = max(new_start, int(result['three_prime_utr_start']))
                
                processed['loc_start'] = new_start
                processed['loc_end'] = new_end
                processed['_padding'] = padding
                processed_results.append(processed)
            else:
                processed_results.append(processed)
        
        bed_content = BedGenerator.create_formatted_bed(processed_results, bed_type.lower(), padding, add_chr_prefix)
        filename = f'{filename_prefix}_{bed_type}.bed' if filename_prefix else f'{bed_type}.bed'
    
    return bed_content, filename

def sort_results(results):
    """
    Sorts results by chromosome (numerically and alphabetically) and start position.
    """
    def chromosome_key(chrom):
        # Remove 'chr' prefix if present
        chrom = str(chrom).replace('chr', '').upper()
        # Convert to integer if possible, otherwise keep as string
        try:
            return (0, int(chrom)) if chrom.isdigit() else (1, chrom)
        except ValueError:
            return (1, chrom)

    def sort_key(result):
        # Ensure start position is an integer
        try:
            start = int(result['loc_start'])
        except (ValueError, TypeError):
            start = 0
        return (chromosome_key(result['loc_region']), start)

    return sorted(results, key=sort_key)
