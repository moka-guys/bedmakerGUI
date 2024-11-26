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
- adjust_utrs(): Adjusts UTRs for results based on user input.
- download_raw_bed(): Generates and returns a raw BED file.
- download_custom_bed(bed_type): Generates and returns a custom BED file.
"""

from flask import render_template, request, jsonify, session, current_app, redirect, url_for, flash
from flask_login import current_user, login_required
from app.bed_generator import bed_generator_bp
from app.bed_generator.utils import (
    store_panels_in_json, get_panels_from_json, load_settings, collect_warnings, increment_version_number, process_tark_data
)
from app.bed_generator.logic import process_form_data, store_results_in_session, process_bulk_data, get_mane_plus_clinical_identifiers, generate_bed_file
from app.forms import SettingsForm, BedGeneratorForm
from app.bed_generator.bed_generator import generate_bed_files
from app.models import BedFile, Settings, BedEntry
from app.bed_generator.database import store_bed_file
import traceback
import json
from datetime import datetime 
from app import db
import re
import requests

def fetch_panels_from_panelapp():
    """
    Fetches panel data from PanelApp API.
    Returns a list of panels with their details.
    """
    try:
        # PanelApp API base URL
        base_url = "https://panelapp.genomicsengland.co.uk/api/v1"
        
        # Get all panels
        response = requests.get(f"{base_url}/panels")
        response.raise_for_status()
        
        panels_data = response.json()
        
        # Extract relevant panel information
        panels = []
        for panel in panels_data.get('results', []):
            panels.append({
                'id': panel.get('id'),
                'name': panel.get('name'),
                'full_name': panel.get('name'),
                'disease_group': panel.get('disease_group', ''),
                'disease_sub_group': panel.get('disease_sub_group', '')
            })
        
        return panels
        
    except requests.RequestException as e:
        current_app.logger.error(f"Error fetching panels from PanelApp: {str(e)}")
        raise Exception(f"Failed to fetch panels: {str(e)}")

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
    """
    data = request.get_json()
    try:
        results, no_data_identifiers = process_bulk_data(data)
        # Only add original locations if they don't already exist
        for result in results:
            if isinstance(result, dict):
                if 'original_loc_start' not in result:
                    result['original_loc_start'] = result.get('loc_start')
                if 'original_loc_end' not in result:
                    result['original_loc_end'] = result.get('loc_end')
        
        session['results'] = results
        session['assembly'] = data.get('assembly', 'GRCh38')
        session['initial_query'] = data.get('initial_query', {})
        return jsonify({
            'success': True, 
            'message': 'Data processed successfully',
            'no_data_identifiers': no_data_identifiers
        })
    
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
    no_data_identifiers = session.get('no_data_identifiers', [])
    
    print("Results:", results)
    print("assembly:", assembly)
    print("No data identifiers:", no_data_identifiers)
    
    session['results'] = []
    session['initial_query'] = {}
    session['no_data_identifiers'] = []
    
    mane_plus_clinical_identifiers = get_mane_plus_clinical_identifiers(results)
    has_mane_plus_clinical = bool(mane_plus_clinical_identifiers)
    settings = Settings.get_settings()
    return render_template(
        'results.html',
        results=results,
        assembly=assembly,
        has_mane_plus_clinical=has_mane_plus_clinical,
        mane_plus_clinical_identifiers=list(mane_plus_clinical_identifiers),
        initial_query=json.dumps(initial_query),
        no_data_identifiers=no_data_identifiers,
        settings=settings.to_dict()
    )

@bed_generator_bp.route('/store_no_data', methods=['POST'])
def store_no_data():
    """Store no_data_identifiers in session."""
    data = request.get_json()
    session['no_data_identifiers'] = data.get('no_data_identifiers', [])
    return jsonify({'success': True})

@bed_generator_bp.route('/adjust_padding', methods=['POST'])
def adjust_padding():
    """
    Adjusts the padding for results while preserving UTR settings.
    """
    data = request.get_json()
    padding_5 = int(data.get('padding_5', 0))
    padding_3 = int(data.get('padding_3', 0))
    use_separate_snp_padding = data.get('use_separate_snp_padding', False)
    snp_padding_5 = int(data.get('snp_padding_5', padding_5))
    snp_padding_3 = int(data.get('snp_padding_3', padding_3))
    results = data.get('results', [])
    is_padding_update = data.get('is_padding_update', False)

    adjusted_results = []
    for result in results:
        adjusted = result.copy()
        
        # Skip padding for genomic coordinates
        if result.get('is_genomic_coordinate', False):
            adjusted_results.append(adjusted)
            continue

        # Determine if this is a SNP entry
        is_snp = bool(result.get('rsid')) or result.get('is_snp', False)
        
        # Skip padding if this is a SNP and separate SNP padding is not enabled
        if is_snp and not use_separate_snp_padding:
            adjusted_results.append(adjusted)
            continue

        # Get strand information (default to forward/1 if not specified)
        strand = result.get('strand', 1)
        
        # If this is a padding update, we need to use the original coordinates
        if is_padding_update:
            # Get original coordinates (before any padding)
            original_start = result.get('original_start', result['loc_start'])
            original_end = result.get('original_end', result['loc_end'])
            
            # Store original coordinates if not already stored
            if 'original_start' not in adjusted:
                adjusted['original_start'] = original_start
                adjusted['original_end'] = original_end
            
            # Determine which padding values to use
            if is_snp and use_separate_snp_padding:
                pad_5 = snp_padding_5
                pad_3 = snp_padding_3
            else:
                pad_5 = padding_5
                pad_3 = padding_3

            # Apply padding based on strand direction
            if strand > 0:  # Forward strand
                adjusted['loc_start'] = original_start - pad_5
                adjusted['loc_end'] = original_end + pad_3
            else:  # Reverse strand
                adjusted['loc_start'] = original_start - pad_3
                adjusted['loc_end'] = original_end + pad_5
        
        adjusted_results.append(adjusted)

    return jsonify({
        'success': True,
        'results': adjusted_results
    })

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
    Endpoint to refresh panel data from PanelApp.
    """
    try:
        panels = fetch_panels_from_panelapp()
        return jsonify({
            'panels': panels,
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        current_app.logger.error(f"Error in refresh_panels: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500

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
        Settings.get_settings().update_from_form(form)
        flash('Settings updated successfully', 'success')
        return redirect(url_for('bed_generator.settings'))
    
    Settings.get_settings().populate_form(form)
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

        # Extract and standardise assembly information
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

        # Create and save entries without applying padding again
        BedEntry.create_entries(new_file.id, results)
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

@bed_generator_bp.route('/download_raw_bed', methods=['POST'])
def download_raw_bed():
    try:
        data = request.json
        results = data['results']
        filename_prefix = data.get('filename_prefix', '')
        add_chr_prefix = data.get('add_chr_prefix', False)
        include_5utr = data.get('include_5utr', False)
        include_3utr = data.get('include_3utr', False)
        
        # Process UTR settings from frontend
        adjusted_results = []
        for result in results:
            if not result.get('is_genomic_coordinate', False):
                processed = process_tark_data(result, include_5utr, include_3utr)
                if processed:
                    adjusted_results.append(processed)
            else:
                adjusted_results.append(result)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{filename_prefix}_{timestamp}_raw.bed" if filename_prefix else f"{timestamp}_raw.bed"
        
        bed_content = BedGenerator.create_formatted_bed(adjusted_results, 'raw', 0, add_chr_prefix)
        
        return jsonify({'content': bed_content, 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bed_generator_bp.route('/download_custom_bed/<bed_type>', methods=['POST'])
def download_custom_bed(bed_type):
    try:
        data = request.get_json()
        results = data.get('results', [])
        filename_prefix = data.get('filename', 'custom')
        add_chr_prefix = data.get('addChrPrefix', False)
        
        # Get settings from database
        settings = Settings.get_settings()
        
        # Debug log the settings
        current_app.logger.debug(f"Settings for {bed_type}:")
        current_app.logger.debug(f"Regular padding: {getattr(settings, f'{bed_type}_padding', 0)}")
        current_app.logger.debug(f"SNP padding: {getattr(settings, f'{bed_type}_snp_padding', 0)}")
        
        # Get the appropriate padding based on whether it's a SNP or not
        for result in results:
            # Debug log the result before processing
            current_app.logger.debug(f"Processing result: {result}")
            current_app.logger.debug(f"Is SNP: {result.get('is_snp', False)}")
            
            # Convert coordinates to integers
            result['loc_start'] = int(result['loc_start'])
            result['loc_end'] = int(result['loc_end'])
            if 'original_loc_start' in result:
                result['original_loc_start'] = int(result['original_loc_start'])
            if 'original_loc_end' in result:
                result['original_loc_end'] = int(result['original_loc_end'])
            
            # Apply appropriate padding based on whether it's a SNP
            if result.get('is_snp', False) or result.get('rsid'):  # Check both is_snp flag and rsid presence
                padding = int(getattr(settings, f'{bed_type}_snp_padding', 0))
                current_app.logger.debug(f"Applying SNP padding: {padding}")
            else:
                padding = int(getattr(settings, f'{bed_type}_padding', 0))
                current_app.logger.debug(f"Applying regular padding: {padding}")
            
            result['_padding'] = padding
            
            # Debug log the result after processing
            current_app.logger.debug(f"Result after padding applied: {result}")
        
        # Generate BED file using database settings
        from app.bed_generator.bed_generator import BedGenerator
        bed_content = BedGenerator.create_formatted_bed(
            results=results,
            format_type=bed_type,
            add_chr_prefix=add_chr_prefix
        )
        
        filename = f"{filename_prefix}_{bed_type}.bed"
        
        return jsonify({
            'content': bed_content,
            'filename': filename
        })
    except Exception as e:
        current_app.logger.error(f"Error in download_custom_bed: {str(e)}")
        current_app.logger.error(f"Full traceback:", exc_info=True)
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

@bed_generator_bp.route('/adjust_utrs', methods=['POST'])
def adjust_utrs():
    try:
        data = request.get_json()
        results = data['results']
        include_5utr = data['include_5utr']
        include_3utr = data['include_3utr']
        
        adjusted_results = []
        for result in results:
            # Skip UTR processing for genomic coordinates
            if (result.get('is_genomic_coordinate', False) or 
                result.get('gene') == 'none' or 
                result.get('alert', '').startswith('No genes found overlapping coordinate')):
                adjusted_results.append(result)
                continue
            
            # Process through process_tark_data for gene-based entries
            processed = process_tark_data(result, include_5utr, include_3utr)
            if processed:
                adjusted_results.append(processed)
        
        return jsonify({
            'success': True,
            'results': adjusted_results
        })
    except Exception as e:
        current_app.logger.error(f"Error in adjust_utrs: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def get_mane_plus_clinical_identifiers(results):
    """Helper function to identify MANE Plus Clinical transcripts."""
    mane_plus_clinical = set()
    for result in results:
        # Check both the mane_transcript_type field and any potential string variations
        mane_type = result.get('mane_transcript_type', '')
        if isinstance(mane_type, str) and ('PLUS CLINICAL' in mane_type.upper() or 
            'MANE Plus Clinical' in mane_type):
            mane_plus_clinical.add(result.get('gene', ''))
    return mane_plus_clinical
