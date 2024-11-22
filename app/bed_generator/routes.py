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
    Adjusts the padding for results, with separate handling for SNPs.
    Skips padding for genomic coordinates.
    """
    data = request.get_json()
    padding_5 = int(data.get('padding_5', 0))
    padding_3 = int(data.get('padding_3', 0))
    use_separate_snp_padding = data.get('use_separate_snp_padding', False)
    snp_padding_5 = int(data.get('snp_padding_5', padding_5))
    snp_padding_3 = int(data.get('snp_padding_3', padding_3))
    results = data.get('results', [])

    for result in results:
        # Check for genomic coordinates in multiple ways
        is_genomic = (
            result.get('is_genomic_coordinate', False) or  # Explicit flag
            result.get('gene', '') == 'none' or  # Default value from coordinate processing
            result.get('alert', '').startswith('No genes found overlapping coordinate')  # Alert message
        )
        
        if is_genomic:
            # Ensure original coordinates are preserved
            if 'original_loc_start' not in result:
                result['original_loc_start'] = result['loc_start']
            if 'original_loc_end' not in result:
                result['original_loc_end'] = result['loc_end']
            # Skip padding for genomic coordinates
            result['loc_start'] = result['original_loc_start']
            result['loc_end'] = result['original_loc_end']
            continue
            
        # Rest of the padding logic for non-genomic coordinates
        if 'original_loc_start' not in result:
            result['original_loc_start'] = result['loc_start']
        if 'original_loc_end' not in result:
            result['original_loc_end'] = result['loc_end']

        strand = result.get('loc_strand', 1)
        is_variant = (
            int(result['original_loc_start']) == int(result['original_loc_end']) or
            bool(re.match(r'^RS\d+$', result.get('rsid', ''), re.IGNORECASE))
        )
        
        p5 = snp_padding_5 if (is_variant and use_separate_snp_padding) else padding_5
        p3 = snp_padding_3 if (is_variant and use_separate_snp_padding) else padding_3

        if strand > 0:  # Forward strand
            result['loc_start'] = int(result['original_loc_start']) - p5
            result['loc_end'] = int(result['original_loc_end']) + p3
        else:  # Reverse strand
            result['loc_start'] = int(result['original_loc_start']) - p3
            result['loc_end'] = int(result['original_loc_end']) + p5

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

@bed_generator_bp.route('/download_bed/<bed_type>', methods=['POST'])
def download_bed(bed_type):
    try:
        data = request.json
        results = data['results']
        filename_prefix = data.get('filename_prefix', '')
        add_chr_prefix = data.get('add_chr_prefix', False)
        
        # Get settings from database
        settings = Settings.get_settings()
        settings_dict = settings.to_dict()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{filename_prefix}_{timestamp}_{bed_type}.bed" if filename_prefix else f"{timestamp}_{bed_type}.bed"
        
        if bed_type == 'raw':
            # For raw BED files, use the padding and UTR settings from the results page
            include_5utr = data.get('include_5utr', False)
            include_3utr = data.get('include_3utr', False)
            
            # Process UTR settings
            adjusted_results = []
            for result in results:
                if not result.get('is_genomic_coordinate', False):
                    processed = process_tark_data(result, include_5utr, include_3utr)
                    if processed:
                        adjusted_results.append(processed)
                else:
                    adjusted_results.append(result)
            
            bed_content = generate_bed_file(bed_type, adjusted_results, filename_prefix, settings_dict, add_chr_prefix)
        else:
            # For custom BED files, use the settings from the database only
            bed_content = generate_bed_file(bed_type, results, filename_prefix, settings_dict, add_chr_prefix)
        
        return jsonify({'content': bed_content[0], 'filename': filename})
    except Exception as e:
        current_app.logger.error(f"Error generating {bed_type} BED file: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
