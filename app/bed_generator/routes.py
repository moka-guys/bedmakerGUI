"""
routes.py - Defines the routes for the bed generator app.

Routes:
- index(): Handles the main page for the bed generator, processing form submissions.
- bulk_process(): Processes bulk genetic data submitted via a POST request.
- results(): Displays the results of processed genetic data.
- adjust_padding(): Adjusts padding for results based on user input.
- panels(): Returns the list of panels as a JSON response.
- refresh_panels(): Fetches and updates the panel data from an external source.
- get_genes_by_panel(panel_id): Retrieves genes associated with a specific panel.
- settings(): Displays and updates application settings.
- submit_for_review(): Submits a BED file for review.
- download_bed(bed_type): Generates and returns a specific type of BED file.
- get_published_bed_files(): Retrieves a list of published BED files.
- get_bed_files(): Retrieves a list of all BED files with their details.

Helper Functions:
- generate_bed_files(filename, results, settings): Generates different BED file formats based on stored settings.
- create_bed_entries(bed_file_id, results, padding_5, padding_3): Creates BED entries for a given file ID.
- collect_warnings(results): Collects and formats warnings from results.
- increment_version_number(filename): Creates a new version number for an existing BED file.
"""

from flask import render_template, request, jsonify, session, current_app, redirect, url_for, flash
from flask_login import current_user, login_required
from typing import List, Dict, Optional
from app.bed_generator import bed_generator_bp
from app.bed_generator.utils import (
    fetch_panels_from_panelapp,
    store_panels_in_json, get_panels_from_json, load_settings
)
from app.bed_generator.logic import process_form_data, store_results_in_session, process_bulk_data, get_mane_plus_clinical_identifiers, update_settings, populate_form_with_settings, generate_bed_file
from app.bed_generator.bed_generator import BedGenerator
from app.forms import SettingsForm, BedGeneratorForm
from app.models import BedFile, BedEntry
import os
import traceback
import json
from datetime import datetime 
from app import db
import re

@bed_generator_bp.route('/', methods=['GET', 'POST'])
def index():
    """
    Renders the main page for the bed generator. Handles form submissions to process genetic data.
    
    GET: Displays the form for data input.
    POST: Processes the submitted form data and redirects to the results page.
    """
    form = BedGeneratorForm()
    panels = get_panels_from_json()
    
    if form.validate_on_submit():
        results, no_data_identifiers, initial_query = process_form_data(form)
        store_results_in_session(results, no_data_identifiers, form.assembly.data, initial_query)
        
        return redirect(url_for('bed_generator.results'))

    return render_template('bed_generator.html', form=form, panels=panels)

@bed_generator_bp.route('/bulk_process', methods=['POST'])
def bulk_process():
    """
    Processes bulk genetic data submitted via a POST request.
    
    Expects JSON data with identifiers and coordinates. Stores results in the session.
    Returns a JSON response indicating success or failure.
    """
    data = request.get_json()
    try:
        results = process_bulk_data(data)
        # Add 'original_loc_start' and 'original_loc_end' to each result
        for result in results:
            result['original_loc_start'] = result['loc_start']
            result['original_loc_end'] = result['loc_end']
        session['results'] = results
        session['assembly'] = data.get('assembly', 'GRCh38')
        session['initial_query'] = data.get('initial_query', {})
        return jsonify({'success': True, 'message': 'Data processed successfully'})
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error in bulk_process: {str(e)}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred.'}), 500

@bed_generator_bp.route('/results')
def results():
    """
    Displays the results of processed genetic data.
    
    Retrieves results from the session and renders them on the results page.
    """
    results = session.get('results', [])
    assembly = session.get('assembly', 'GRCh38')
    initial_query = session.get('initial_query', {})
    
    print("Results:", results)
    print("assembly:", assembly)
    print("initial_query:", initial_query)  # Debug print
    
    session['results'] = []
    session['initial_query'] = {}
    
    mane_plus_clinical_identifiers = get_mane_plus_clinical_identifiers(results)
    has_mane_plus_clinical = bool(mane_plus_clinical_identifiers)
    return render_template(
        'results.html',
        results=results,
        assembly=assembly,
        has_mane_plus_clinical=has_mane_plus_clinical,
        mane_plus_clinical_identifiers=list(mane_plus_clinical_identifiers),
        initial_query=json.dumps(initial_query)  # JSON encode the initial_query
    )

@bed_generator_bp.route('/adjust_padding', methods=['POST'])
def adjust_padding():
    """
    Adjusts the padding for results.

    Expects JSON data with 'padding_5', 'padding_3', and 'results'.
    Recalculates 'loc_start' and 'loc_end' for each result based on the provided padding values.

    Returns:
        JSON response with the updated results and a success status.
    """
    data = request.get_json()
    padding_5 = int(data.get('padding_5', 0))
    padding_3 = int(data.get('padding_3', 0))
    results = data.get('results', [])

    # Recalculate loc_start and loc_end based on new padding
    for result in results:
        result['loc_start'] = int(result['original_loc_start']) - padding_5
        result['loc_end'] = int(result['original_loc_end']) + padding_3

    return jsonify({'success': True, 'results': results})


@bed_generator_bp.route('/panels')
def panels():
    """
    Returns the list of panels and last updated timestamp as a JSON response.
    """
    panel_data, last_updated = get_panels_from_json()
    return jsonify({'panels': panel_data, 'last_updated': last_updated})

@bed_generator_bp.route('/refresh_panels')
def refresh_panels():
    """
    Fetches and updates the panel data from an external source.
    
    Retrieves panel data from PanelApp, stores it in a JSON file, and returns the updated data.
    """
    try:
        print("Starting panel refresh")
        panel_data = fetch_panels_from_panelapp()
        print(f"Fetched {len(panel_data)} panels")
        store_panels_in_json(panel_data)
        print("Stored panels in JSON")
        panels, last_updated = get_panels_from_json()
        return jsonify({'panels': panels, 'last_updated': last_updated})
    except Exception as e:
        print(f"Error in refresh_panels: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bed_generator_bp.route('/get_genes_by_panel/<panel_id>')
def get_genes_by_panel(panel_id):
    """
    Retrieves genes associated with a specific panel.
    
    Args:
        panel_id: The ID of the panel to retrieve genes for.
    
    Returns a JSON response with the list of genes or an error message if the panel is not found.
    """
    panels, last_updated = get_panels_from_json()
    
    if not isinstance(panels, list):
        return jsonify({'gene_list': [], 'error': 'Invalid panel data format'})
    
    try:
        panel = next((p for p in panels if str(p.get('id')) == str(panel_id) or p.get('full_name') == panel_id), None)
        
        if panel:
            if 'genes' in panel:
                return jsonify({'gene_list': panel['genes']})
            else:
                return jsonify({'gene_list': [], 'error': 'Panel found but contains no genes'})
        else:
            return jsonify({'gene_list': [], 'error': 'Panel not found'})
    except Exception as e:
        print(f"Error processing panel data: {str(e)}")
        return jsonify({'gene_list': [], 'error': f'Error processing panel data: {str(e)}'})


@bed_generator_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """
    Displays and updates application settings.

    GET: Populates the settings form with current settings and renders the settings page.
    POST: Validates and updates the settings based on user input, then redirects to the settings page.

    Returns:
        Renders the settings page with the form.
    """
    form = SettingsForm()
    if form.validate_on_submit():
        update_settings(form)
        flash('Settings updated successfully', 'success')
        return redirect(url_for('bed_generator.settings'))
    
    populate_form_with_settings(form)
    return render_template('settings.html', form=form)

@bed_generator_bp.route('/submit_for_review', methods=['POST'])
def submit_for_review():
    """
    Submits a BED file for review in bed_manager.

    Expects JSON data with 'results', 'fileName', 'initialQuery', and optionally 'existing_file_id'.

    Returns:
        JSON response indicating success or failure, with a message and the new BED file ID if successful.
    """
    try:
        data = request.json
        results = data.get('results', [])
        fileName = data.get('fileName', '')
        initial_query = data.get('initialQuery', {})
        existing_file_id = data.get('existing_file_id')

        # Extract and standardize assembly information
        assembly = initial_query.get('assembly', 'GRCh38')
        assembly_mapping = {'hg19': 'GRCh37', 'hg38': 'GRCh38', 'GRCh37': 'GRCh37', 'GRCh38': 'GRCh38'}
        assembly = assembly_mapping.get(assembly, 'UNKNOWN')

        # Common parameters for BED file creation
        file_params = {
            'status': 'pending',
            'submitter_id': current_user.id,
            'initial_query': json.dumps(initial_query, ensure_ascii=False),
            'assembly': assembly,
            'include_3utr': initial_query.get('include3UTR', False),
            'include_5utr': initial_query.get('include5UTR', False),
            'warning': collect_warnings(results)
        }

        if existing_file_id:
            existing_file = BedFile.query.get(existing_file_id)
            if not existing_file:
                return jsonify({'success': False, 'error': 'Existing file not found'}), 404

            # Handle version update
            new_filename = increment_version_number(existing_file.filename)
            existing_file.status = 'draft'
            db.session.add(existing_file)

            new_file = BedFile(filename=new_filename, **file_params)
        elif fileName:
            new_file = BedFile(filename=fileName, **file_params)
        else:
            return jsonify({'success': False, 'error': 'No file name provided and no existing file selected'}), 400

        # Create and save the new file
        db.session.add(new_file)
        db.session.flush()

        # Create and save entries
        padding_5 = initial_query.get('padding_5', 0)
        padding_3 = initial_query.get('padding_3', 0)
        entries = create_bed_entries(new_file.id, results, padding_5, padding_3)
        db.session.bulk_save_objects(entries)
        db.session.commit()

        # Generate BED files
        if fileName:
            generate_bed_files(fileName, results, load_settings())

        return jsonify({
            'success': True,
            'message': 'BED file created and saved successfully',
            'bed_file_id': new_file.id
        })

    except Exception as e:
        current_app.logger.error(f"Error in submit_for_review: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_bed_files(filename: str, results: List[Dict], settings: Dict) -> None:
    """
    Generates different BED file formats based on stored settings in database.
    """
    bed_dir = current_app.config.get('DRAFT_BED_FILES_DIR')
    os.makedirs(bed_dir, exist_ok=True)

    bed_types = {
        'raw': BedGenerator.create_raw_bed,
        'data': BedGenerator.create_data_bed,
        'sambamba': BedGenerator.create_sambamba_bed,
        'exomeDepth': BedGenerator.create_exome_depth_bed,
        'CNV': BedGenerator.create_cnv_bed
    }

    for bed_type, create_function in bed_types.items():
        padding = settings.get('padding', {}).get(bed_type, 0)
        content = (create_function(results, add_chr_prefix=False) if bed_type == 'raw'
                  else create_function(results, padding, add_chr_prefix=False))
        
        file_path = os.path.join(bed_dir, f"{filename}_{bed_type}.bed")
        with open(file_path, 'w') as f:
            f.write(content)

def create_bed_entries(bed_file_id: int, results: List[Dict], padding_5: int, padding_3: int) -> List[BedEntry]:
    """
    Creates BED entries for a given file ID.
    """
    entries = []
    for result in results:
        entry = BedEntry(
            bed_file_id=bed_file_id,
            chromosome=result['loc_region'],
            start=int(result['loc_start']) - padding_5,
            end=int(result['loc_end']) + padding_3,
            entrez_id=result['entrez_id'],
            gene=result['gene'],
            accession=result['accession'],
            exon_id=result['exon_id'],
            exon_number=result['exon_number'],
            transcript_biotype=result['transcript_biotype'],
            mane_transcript=result['mane_transcript'],
            mane_transcript_type=result['mane_transcript_type'],
            warning=json.dumps(result.get('warning')) if result.get('warning') else None
        )
        entries.append(entry)
    return entries

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

@bed_generator_bp.route('/download_bed/<bed_type>', methods=['POST'])
def download_bed(bed_type):
    """
    Generates and returns a specific type of BED file.
    
    Args:
        bed_type: The type of BED file to generate (e.g., 'raw', 'data', 'sambamba').
    
    Expects JSON data with results and an optional filename prefix. Returns the BED file content and filename.
    """
    try:
        results = request.json['results']
        filename_prefix = request.json.get('filename_prefix', '')
        add_chr_prefix = request.json.get('add_chr_prefix', False)  # Get the add_chr_prefix flag
        settings = load_settings()
        
        bed_content, filename = generate_bed_file(bed_type, results, filename_prefix, settings, add_chr_prefix)
        
        return jsonify({'content': bed_content, 'filename': filename})
    except Exception as e:
        print(f"Error in download_bed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bed_generator_bp.route('/get_published_bed_files')
@login_required
def get_published_bed_files():
    try:
        published_files = BedFile.query.filter_by(status='published').all()
        files_data = [{'id': file.id, 'filename': file.filename} for file in published_files]
        return jsonify({'success': True, 'bed_files': files_data})
    except Exception as e:
        current_app.logger.error(f"Error in get_published_bed_files: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bed_generator_bp.route('/get_bed_files')
def get_bed_files():
    try:
        bed_files = BedFile.query.all()
        files_data = [{
            'id': file.id,
            'filename': file.filename,
            'status': file.status,
            'submitter': file.submitter.username if file.submitter else 'Unknown',
            'created_at': file.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'assembly': file.assembly,
            'include_3utr': file.include_3utr,
            'include_5utr': file.include_5utr
        } for file in bed_files]
        return jsonify({'success': True, 'bed_files': files_data})
    except Exception as e:
        current_app.logger.error(f"Error in get_bed_files: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
