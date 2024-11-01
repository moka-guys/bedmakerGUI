"""
database.py - Provides functions to store BED files and their entries in the database.

Functions:
- store_bed_file: Stores a BED file and its entries in the database.
- create_bed_file: Creates a new BED file record in the database.
"""

from app import db
from app.models import BedFile, BedEntry
from typing import List, Dict
import json

def store_bed_file(file_name: str, results: List[Dict], user_id: int, initial_query: str, assembly: str) -> int:
    """
    Stores a BED file and its entries in the database.

    Args:
        file_name (str): The name of the BED file.
        results (List[Dict]): A list of dictionaries containing BED entry data.
        user_id (int): The ID of the user submitting the BED file.
        initial_query (str): The initial query made from the frontend.
        assembly (str): The assembly used for the BED file.

    Returns:
        int: The ID of the newly created BED file.
    """
    print("Initial Query:", initial_query)
    print("Assembly:", assembly)
    new_bed_file = create_bed_file(file_name, user_id, initial_query, assembly)
    
    # Use the model's create_entries method
    BedEntry.create_entries(new_bed_file.id, results)
    
    db.session.commit()
    return new_bed_file.id

def create_bed_file(file_name: str, user_id: int, initial_query: str, assembly: str) -> BedFile:
    # Collect warnings from results
    warnings = []
    initial_query_data = json.loads(initial_query)
    results = initial_query_data.get('results', [])
    
    for result in results:
        if warning := result.get('warning'):
            warnings.append({
                'identifier': result.get('identifier'),
                'message': warning.get('message'),
                'type': warning.get('type')
            })
    
    # Create a summary warning
    file_warning = None
    if warnings:
        file_warning = json.dumps({
            'summary': "Some transcripts require clinical review",
            'details': warnings
        })

    new_bed_file = BedFile(
        filename=file_name,
        status='draft',
        submitter_id=user_id,
        initial_query=initial_query,
        assembly=assembly,
        warning=file_warning
    )
    db.session.add(new_bed_file)
    db.session.flush()
    return new_bed_file