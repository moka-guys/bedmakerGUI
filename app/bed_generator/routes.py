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
from typing import List, Dict, Optional
from flask_login import current_user, login_required
from app.bed_generator import bed_generator_bp
from app.bed_generator.utils import (
    store_panels_in_json, get_panels_from_json, load_settings, collect_warnings, increment_version_number, process_tark_data, fetch_genes_for_panel
)
from app.bed_generator.logic import process_form_data, store_results_in_session, process_bulk_data, get_mane_plus_clinical_identifiers, generate_bed_file
from app.forms import SettingsForm, BedGeneratorForm
from app.bed_generator.bed_generator import generate_bed_files, BedGenerator
from app.models import BedFile, Settings, BedEntry
from app.bed_generator.database import store_bed_file
import traceback
import json
from datetime import datetime 
from app import db
import re
import requests
import os
import concurrent.futures
from typing import List, Dict, Tuple

def fetch_panels_from_panelapp():
    """
    Fetches panel data from PanelApp API, handling pagination.
    Returns a list of panels with their details, ordered by the 'R' code.
    """
    try:
        # PanelApp API base URL for signed-off panels
        base_url = "https://panelapp.genomicsengland.co.uk/api/v1/panels/signedoff/"
        panels = []
        next_url = base_url
        
        while next_url:
            print(f"\nFetching from URL: {next_url}")
            response = requests.get(next_url)
            response.raise_for_status()
            
            data = response.json()
            panels.extend(data.get('results', []))
            next_url = data.get('next')
        
        # Extract relevant panel information
        panel_list = []
        for panel in panels:
            # Extract the 'R' code from relevant_disorders
            relevant_disorders = panel.get('relevant_disorders', [])
            r_code = next((code for code in relevant_disorders if code.startswith('R')), '')
            
            panel_name = panel.get('name', '')
            formatted_name = f"{r_code} - {panel_name}" if r_code else panel_name
            
            print(f"\nOriginal name: {panel_name}")
            print(f"Relevant disorders: {relevant_disorders}")
            print(f"R-code found: {r_code}")
            print(f"Formatted name: {formatted_name}")
            
            panel_list.append({
                'id': panel.get('id'),
                'name': formatted_name,
                'full_name': panel_name,
                'disease_group': panel.get('disease_group', ''),
                'disease_sub_group': panel.get('disease_sub_group', '')
            })
        
        # Sort panels by the 'R' code
        def get_r_number(panel):
            r_match = re.search(r'R(\d+)', panel['name'])
            return int(r_match.group(1)) if r_match else float('inf')
        
        panel_list.sort(key=get_r_number)
        
        print(f"\nFirst 3 sorted panels: {[p['name'] for p in panel_list[:3] if panel_list]}")
        
        return panel_list
        
    except requests.RequestException as e:
        current_app.logger.error(f"Error fetching panels from PanelApp: {str(e)}")
        raise Exception(f"Failed to fetch panels: {str(e)}")
    except Exception as e:
        current_app.logger.error(f"Error processing panels: {str(e)}")
        raise Exception(f"Failed to process panels: {str(e)}")

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
        # Store the panels in the JSON file
        store_panels_in_json(panels)
        
        # Read back the stored data to ensure consistency
        stored_panels, last_updated = get_panels_from_json()
        
        return jsonify({
            'panels': stored_panels,
            'last_updated': last_updated
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
    """
    try:
        # Fetch genes directly from PanelApp API
        genes = fetch_genes_for_panel(int(panel_id), include_amber=True, include_red=True)
        if genes:
            return jsonify({'gene_list': genes})
        else:
            return jsonify({'gene_list': [], 'error': 'No genes found for this panel'})
    except Exception as e:
        print(f"Error fetching genes for panel {panel_id}: {str(e)}")
        return jsonify({'gene_list': [], 'error': f'Error fetching genes: {str(e)}'})


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
@login_required
def submit_for_review():
    """
    Submit BED files for review, generating both base and type-specific versions.
    """
    try:
        data = request.get_json()
        file_name = data.get('fileName')
        results = data.get('results', [])
        initial_query = json.loads(data.get('initialQuery'))
        assembly = data.get('assembly')
        settings = Settings.get_settings()

        # Process base BED file if requested
        if data.get('baseOnly', False):
            base_settings = {
                'include_5utr': data.get('include5UTR', False),
                'include_3utr': data.get('include3UTR', False)
            }
            
            # Process entries for base BED file
            processed_results = process_bed_entries(
                results,
                settings=base_settings
            )
            
            # Create base BED file record
            base_query = initial_query.copy()
            base_query['settings'] = base_settings
            
            base_bed_file = BedFile(
                filename=file_name,
                status='draft',
                submitter_id=current_user.id,
                initial_query=json.dumps(base_query),
                assembly=assembly,
                include_5utr=base_settings['include_5utr'],
                include_3utr=base_settings['include_3utr']
            )
            db.session.add(base_bed_file)
            db.session.flush()
            
            # Create entries and generate file
            BedEntry.create_entries(base_bed_file.id, processed_results)
            from app.bed_generator.bed_generator import generate_bed_files as bed_generator_generate_files
            bed_generator_generate_files(file_name, processed_results, settings.to_dict())
            
        else:
            # Process each BED type
            bed_types = ['data', 'sambamba', 'exomeDepth', 'cnv']
            
            for bed_type in bed_types:
                # Get settings for this bed type
                type_settings = {
                    'include_5utr': getattr(settings, f'{bed_type}_include_5utr', False),
                    'include_3utr': getattr(settings, f'{bed_type}_include_3utr', False)
                }
                
                # Process entries for this type
                processed_results = process_bed_entries(
                    results,
                    settings=type_settings,
                    padding=getattr(settings, f'{bed_type}_padding', 0),
                    snp_padding=getattr(settings, f'{bed_type}_snp_padding', 0)
                )
                
                # Create type-specific query
                type_query = initial_query.copy()
                type_query['settings'] = {
                    **type_settings,
                    'padding': {
                        'standard': getattr(settings, f'{bed_type}_padding', 0),
                        'snp': getattr(settings, f'{bed_type}_snp_padding', 0)
                    },
                    'bed_type': bed_type
                }
                
                # Create BED file record
                type_filename = f"{file_name}_{bed_type}"
                bed_file = BedFile(
                    filename=type_filename,
                    status='draft',
                    submitter_id=current_user.id,
                    initial_query=json.dumps(type_query),
                    assembly=assembly,
                    include_5utr=type_settings['include_5utr'],
                    include_3utr=type_settings['include_3utr']
                )
                db.session.add(bed_file)
                db.session.flush()
                
                # Create entries and generate file
                BedEntry.create_entries(bed_file.id, processed_results)
                from app.bed_generator.bed_generator import generate_bed_files as bed_generator_generate_files
                bed_generator_generate_files(type_filename, processed_results, settings.to_dict())
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        current_app.logger.error(f"Error in submit_for_review: {str(e)}")
        current_app.logger.error("Full traceback:", exc_info=True)
        db.session.rollback()
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
        settings = Settings.get_settings()
        
        # Get settings for this bed type

        bed_settings = {
            'include_5utr': getattr(settings, f'{bed_type}_include_5utr', False),
            'include_3utr': getattr(settings, f'{bed_type}_include_3utr', False)
        }
        
        # Process entries
        processed_results = process_bed_entries(
            results,
            bed_settings,
            padding=getattr(settings, f'{bed_type}_padding', 0),
            snp_padding=getattr(settings, f'{bed_type}_snp_padding', 0)
        )
        
        # Generate BED file content
        bed_content = BedGenerator.create_formatted_bed(
            results=processed_results,
            format_type=bed_type,
            add_chr_prefix=data.get('addChrPrefix', False)
        )
        
        return jsonify({
            'content': bed_content,
            'filename': f"{data.get('filename', 'custom')}_{bed_type}.bed"
        })
    except Exception as e:
        current_app.logger.error(f"Error in download_custom_bed: {str(e)}")
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

def process_bed_entry(
    entry: Dict,
    settings: Dict[str, bool],
    padding: Optional[int] = None,
    snp_padding: Optional[int] = None
) -> Optional[Dict]:
    """
    Process a single BED entry according to UTR settings and padding requirements.
    Returns None if the entry should be excluded.
    
    Args:
        entry: Dictionary containing the entry data
        settings: Dictionary with 'include_5utr' and 'include_3utr' boolean flags
        padding: Optional padding value for regular entries
        snp_padding: Optional padding value for SNP entries
    """
    # Return genomic coordinates unchanged
    if entry.get('is_genomic_coordinate', False):
        return entry.copy()
    
    result = entry.copy()
    
    # Handle SNPs
    if entry.get('is_snp', False) or entry.get('rsid'):
        if snp_padding:
            center = int(entry['loc_start'])
            result['loc_start'] = center - snp_padding
            result['loc_end'] = center + snp_padding
        return result
    
    strand = entry.get('strand', 1)
    start = int(entry.get('full_loc_start', entry['loc_start']))
    end = int(entry.get('full_loc_end', entry['loc_end']))
    
    # Check if exon is entirely within UTR
    if strand == 1:  # Forward strand
        if not settings['include_5utr'] and entry.get('five_prime_utr_end'):
            utr_end = int(entry['five_prime_utr_end'])
            if end <= utr_end:
                return None
            start = max(start, utr_end)
            
        if not settings['include_3utr'] and entry.get('three_prime_utr_start'):
            utr_start = int(entry['three_prime_utr_start'])
            if start >= utr_start:
                return None
            end = min(end, utr_start)
    else:  # Reverse strand
        if not settings['include_5utr'] and entry.get('five_prime_utr_end'):
            utr_end = int(entry['five_prime_utr_end'])
            if start >= utr_end:
                return None
            end = min(end, utr_end)
            
        if not settings['include_3utr'] and entry.get('three_prime_utr_start'):
            utr_start = int(entry['three_prime_utr_start'])
            if end <= utr_start:
                return None
            start = max(start, utr_start)
    
    # Apply padding if specified
    if padding:
        start = max(0, start - padding)
        end = end + padding
        
    result['loc_start'] = start
    result['loc_end'] = end
    
    return result

def process_bed_entries(
    entries: List[Dict],
    settings: Dict[str, bool],
    padding: Optional[int] = None,
    snp_padding: Optional[int] = None
) -> List[Dict]:
    """
    Process multiple BED entries according to UTR settings and padding requirements.
    
    Args:
        entries: List of dictionaries containing entry data
        settings: Dictionary with 'include_5utr' and 'include_3utr' boolean flags
        padding: Optional padding value for regular entries
        snp_padding: Optional padding value for SNP entries
    """
    processed_entries = []
    
    for entry in entries:
        processed = process_bed_entry(entry, settings, padding, snp_padding)
        if processed:
            processed_entries.append(processed)
            
    return processed_entries