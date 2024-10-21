"""
logic.py Core logic for processing genetic data in the bed generator application for processing data.

Functions:
- process_form_data(form): Processes form data to extract and process genetic identifiers and coordinates.
- store_results_in_session(results, no_data_identifiers, assembly, initial_query): Stores processed results in the session.
- process_bulk_data(data): Processes bulk genetic data from a dictionary input.
- get_mane_plus_clinical_identifiers(results): Retrieves identifiers marked as 'MANE PLUS CLINICAL' from results.
- update_settings(form, json_file_path): Updates application settings based on form input and saves to a JSON file.
- populate_form_with_settings(form, json_file_path): Populates a form with settings loaded from a JSON file.
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

def process_bulk_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Processes bulk genetic data from a dictionary input.

    Args:
        data: A dictionary containing identifiers and coordinates to process.

    Returns:
        A list of processed genetic data entries.

    Raises:
        ValueError: If any coordinate is invalid.
    """
    results = []
    if data.get('identifiers'):
        processed_results = process_identifiers(
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
    
    return results

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
        if result is not None and result.get('mane_transcript_type') == 'MANE PLUS CLINICAL'
    )

def update_settings(form):
    settings = Settings.get_settings()
    for field in ['data_padding', 'sambamba_padding', 'exomeDepth_padding', 'cnv_padding']:
        setattr(settings, field, getattr(form, field).data)
    db.session.commit()

def populate_form_with_settings(form):
    settings = Settings.get_settings()
    for field in ['data_padding', 'sambamba_padding', 'exomeDepth_padding', 'cnv_padding']:
        getattr(form, field).data = getattr(settings, field)

def generate_bed_file(bed_type: str, results: List[Dict[str, Any]], filename_prefix: str, settings: Dict[str, int], add_chr_prefix: bool) -> Tuple[str, str]:
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
    elif bed_type == 'data':
        bed_content = BedGenerator.create_data_bed(results, settings['data_padding'], add_chr_prefix)
        filename = f'{filename_prefix}_data.bed' if filename_prefix else 'data.bed'
    elif bed_type == 'sambamba':
        bed_content = BedGenerator.create_sambamba_bed(results, settings['sambamba_padding'], add_chr_prefix)
        filename = f'{filename_prefix}_sambamba.bed' if filename_prefix else 'sambamba.bed'
    elif bed_type == 'exomeDepth':
        bed_content = BedGenerator.create_exome_depth_bed(results, settings['exomeDepth_padding'], add_chr_prefix)
        filename = f'{filename_prefix}_exomeDepth.bed' if filename_prefix else 'exomeDepth.bed'
    elif bed_type == 'cnv':
        bed_content = BedGenerator.create_cnv_bed(results, settings['cnv_padding'], add_chr_prefix)
        filename = f'{filename_prefix}_CNV.bed' if filename_prefix else 'CNV.bed'
    else:
        raise ValueError('Invalid BED type')
    
    return bed_content, filename
