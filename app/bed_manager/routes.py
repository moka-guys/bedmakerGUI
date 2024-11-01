"""
routes.py - Defines the routes for the bed manager app.

Routes:
- index(): Displays the main page of the bed manager with a list of all bed files.
- submit_bed_file(): Handles the submission of a new BED file.
- review_bed_file(file_id): Manages the review process for a specific BED file.
- remove_bed_file(file_id): Removes a BED file if the user has permission.
- bed_file_details(file_id): Displays details of a specific BED file, including its entries and version history.
- authorise_bed_file(file_id): Authorizes a BED file, publishing it or creating a new version.
- reload_bed_results(file_id): Reloads the results of a BED file into the session for the bed generator.
- compare_bed_files(file_id): Compares a new BED file with its published version or another selected file.
- file_details(file_id): Retrieves and returns detailed information about a specific BED file.
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app.bed_manager import bed_manager_bp
from app.models import BedFile, BedEntry
from app import db
import re
import json

@bed_manager_bp.route('/')
@login_required
def index():
    bed_files = BedFile.query.all()
    return render_template('bed_manager/index.html', bed_files=bed_files)

@bed_manager_bp.route('/submit', methods=['POST'])
@login_required
def submit_bed_file():
    # Logic for submitting a new BED file
    pass

@bed_manager_bp.route('/review/<int:file_id>', methods=['GET', 'POST'])
@login_required
def review_bed_file(file_id):
    # Logic for reviewing a BED file
    pass

@bed_manager_bp.route('/remove/<int:file_id>', methods=['POST'])
@login_required
def remove_bed_file(file_id):
    bed_file = BedFile.query.get_or_404(file_id)
    
    # Check if the current user has permission to remove the file
    if current_user.is_authorizer or current_user.id == bed_file.submitter_id:
        try:
            db.session.delete(bed_file)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)})
    else:
        return jsonify({'success': False, 'error': 'You do not have permission to remove this file.'}), 403

@bed_manager_bp.route('/bed_file_details/<int:file_id>')
@login_required
def bed_file_details(file_id):
    bed_file = BedFile.query.options(db.joinedload(BedFile.entries)).get_or_404(file_id)
    published_files = BedFile.query.filter_by(status='published').all()
    
    # Parse the warnings for each entry
    for entry in bed_file.entries:
        if entry.warning:
            entry.warning = json.loads(entry.warning)
    
    # Find the previous version of the file
    previous_version = None
    if bed_file.status == 'pending':
        match = re.search(r'_v(\d+)$', bed_file.filename)
        if match:
            current_version = int(match.group(1))
            previous_version_name = re.sub(r'_v\d+$', f'_v{current_version - 1}', bed_file.filename)
            previous_version = BedFile.query.filter_by(filename=previous_version_name, status='published').first()
    
    return render_template('bed_manager/bed_file_details.html', 
                           bed_file=bed_file, 
                           published_files=published_files, 
                           previous_version=previous_version)

@bed_manager_bp.route('/authorise/<int:file_id>', methods=['POST'])
@login_required
def authorise_bed_file(file_id):
    if not current_user.is_authorizer:
        return jsonify({'success': False, 'error': 'You do not have permission to authorise files.'}), 403

    bed_file = BedFile.query.get_or_404(file_id)
    
    if bed_file.status == 'published':
        return jsonify({'success': False, 'error': 'This file is already published.'}), 400

    # Add warning acknowledgment check
    if bed_file.warning and not request.json.get('warningsAcknowledged'):
        return jsonify({
            'success': False, 
            'error': 'You must acknowledge the warnings before authorising this file.'
        }), 400

    try:
        data = request.json
        file_action = data.get('fileAction', 'new')

        if file_action == 'new':
            # Check if the filename already has a version
            if not re.search(r'_v\d+$', bed_file.filename):
                # If not, append _v1 to the filename
                bed_file.filename = f"{bed_file.filename}_v1"
            
            bed_file.status = 'published'
            bed_file.authorizer_id = current_user.id
            message = f'The new BED file "{bed_file.filename}" was successfully published and is now available for analysis.'
        else:
            # Increment version of an existing file
            existing_file = BedFile.query.get(int(file_action))
            if not existing_file:
                return jsonify({'success': False, 'error': 'Selected file for increment not found.'}), 404

            match = re.search(r'_v(\d+)$', existing_file.filename)
            if match:
                current_version = int(match.group(1))
                new_filename = re.sub(r'_v\d+$', f'_v{current_version + 1}', existing_file.filename)
            else:
                new_filename = f"{existing_file.filename}_v2"

            new_file = BedFile(
                filename=new_filename,
                status='published',
                submitter_id=bed_file.submitter_id,
                authorizer_id=current_user.id,
                initial_query=bed_file.initial_query,
                assembly=bed_file.assembly
            )
            db.session.add(new_file)
            db.session.flush()  # This will assign an ID to new_file

            # Copy entries from the pending file to the new file
            for entry in bed_file.entries:
                new_entry = BedEntry(
                    bed_file_id=new_file.id,
                    chromosome=entry.chromosome,
                    start=entry.start,
                    end=entry.end,
                    entrez_id=entry.entrez_id,
                    gene=entry.gene,
                    accession=entry.accession,
                    exon_id=entry.exon_id,
                    exon_number=entry.exon_number,
                    transcript_biotype=entry.transcript_biotype,
                    mane_transcript=entry.mane_transcript,
                    mane_transcript_type=entry.mane_transcript_type,
                    warning=entry.warning
                )
                db.session.add(new_entry)

            # Set the original pending file to 'draft' status
            bed_file.status = 'draft'

            message = f'A new version of the BED file ({new_filename}) was created and published.'

        db.session.commit()
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bed_manager_bp.route('/reload_bed_results/<int:file_id>')
@login_required
def reload_bed_results(file_id):
    bed_file = BedFile.query.get_or_404(file_id)
    
    # Store the results in the session
    session['results'] = [
        {
            'loc_region': entry.chromosome,
            'loc_start': entry.start,
            'loc_end': entry.end,
            'entrez_id': entry.entrez_id,
            'gene': entry.gene,
            'accession': entry.accession,
            'exon_id': entry.exon_id,
            'exon_number': entry.exon_number,
            'transcript_biotype': entry.transcript_biotype,
            'mane_transcript': entry.mane_transcript,
            'mane_transcript_type': entry.mane_transcript_type,
        }
        for entry in bed_file.entries
    ]
    session['assembly'] = bed_file.assembly
    
    # Add warnings to session if they exist
    if bed_file.warning:
        session['warnings'] = json.loads(bed_file.warning)
    else:
        session.pop('warnings', None)  # Remove warnings if they don't exist
    
    return jsonify({
        'success': True,
        'redirect_url': url_for('bed_generator.results')
    })

@bed_manager_bp.route('/compare_bed_files/<int:file_id>')
@login_required
def compare_bed_files(file_id):
    new_file = BedFile.query.get_or_404(file_id)
    
    selected_file_id = request.args.get('selected_file_id', 'new')
    
    if selected_file_id != 'new':
        published_file = BedFile.query.get_or_404(int(selected_file_id))
    else:
        # Find the corresponding published file (assuming filenames are versioned)
        base_filename = new_file.filename.rsplit('_v', 1)[0]
        published_file = BedFile.query.filter(
            BedFile.filename.startswith(base_filename),
            BedFile.status == 'published'
        ).order_by(BedFile.created_at.desc()).first()

    new_entries = [
        {
            'chromosome': entry.chromosome,
            'start': entry.start,
            'end': entry.end,
            'gene': entry.gene
        } for entry in new_file.entries
    ]

    if published_file:
        published_entries = [
            {
                'chromosome': entry.chromosome,
                'start': entry.start,
                'end': entry.end,
                'gene': entry.gene
            } for entry in published_file.entries
        ]
        message = None
        published_file_name = published_file.filename
    else:
        published_entries = []
        message = "No published version found for comparison. This may be a new BED file."
        published_file_name = None

    return jsonify({
        'new_file': new_entries,
        'published_file': published_entries,
        'message': message,
        'new_file_name': new_file.filename,
        'published_file_name': published_file_name
    })

@bed_manager_bp.route('/file_details/<int:file_id>')
def file_details(file_id):
    bed_file = BedFile.query.get_or_404(file_id)
    
    # Parse the initial_query JSON string
    try:
        initial_query = json.loads(bed_file.initial_query)
    except json.JSONDecodeError:
        initial_query = {"error": "Invalid JSON"}

    return jsonify({
        'created_at': bed_file.created_at.isoformat(),
        'updated_at': bed_file.updated_at.isoformat(),
        'initial_query': initial_query,
        'warning': json.loads(bed_file.warning) if bed_file.warning else None
    })
