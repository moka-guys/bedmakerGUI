"""
transcript_processing.py - Functions for processing transcript data.

Functions:
- select_transcripts: Selects relevant transcripts based on assembly and version.
- process_transcripts: Processes transcript data into a standardized format.
- process_grch38_mane_select: Processes GRCh38 MANE SELECT transcripts.
- process_base_accession: Processes transcripts using base accession.
- process_coordinate_data: Processes coordinate data into gene information.
"""

from typing import List, Dict, Optional
from .utils import standardize_result

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
        # First try to find MANE Select transcript
        grch38_mane = next((t for t in data if t['assembly'] == 'GRCh38' and 
                            t.get('mane_transcript_type') == 'MANE SELECT' and 
                            t['stable_id'].startswith('NM')), None)
        if grch38_mane:
            matching_grch37 = [t for t in assembly_transcripts if t['stable_id'] == grch38_mane['stable_id']]
            if matching_grch37:
                selected = max(matching_grch37, key=lambda x: int(x['stable_id_version']))
                identifier = f"{selected['stable_id']}.{selected['stable_id_version']}"
                selected['warning'] = {
                    'message': f"Transcript selected based on GRCh38 MANE transcript {grch38_mane['stable_id']}.{grch38_mane['stable_id_version']}",
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
    """
    Processes transcript data into a standardized format.
    """
    results = []
    for transcript in transcripts:
        if not transcript:
            continue

        print(f"\nProcessing transcript: {transcript.get('stable_id')}")
        print(f"Assembly: {transcript.get('assembly')}")
        
        # Get Ensembl ID and Entrez ID from genes data
        ensembl_id = None
        entrez_id = None
        if transcript.get('genes'):
            for gene in transcript['genes']:
                if gene.get('ensembl_id'):
                    ensembl_id = gene['ensembl_id']
                    entrez_id = gene['ensembl_id']
                    break
                elif gene.get('stable_id'):
                    ensembl_id = gene['stable_id']
                    entrez_id = gene['stable_id']
                    break

        # Handle MANE transcript and type based on assembly
        assembly = transcript.get('assembly')
        mane_transcript = ''
        mane_transcript_type = None
        if assembly == 'GRCh38':
            mane_transcript = transcript.get('mane_transcript', '')
            mane_transcript_type = transcript.get('mane_transcript_type', '')
        
        print(f"Found Ensembl ID from genes: {ensembl_id}")
        print(f"Found Entrez ID from genes: {entrez_id}")
        print(f"MANE transcript (only for GRCh38): {mane_transcript}")
        print(f"MANE transcript type (only for GRCh38): {mane_transcript_type}")

        # Build the result dictionary
        for index, exon in enumerate(transcript.get('exons', []), start=1):
            result = {
                'loc_region': exon['loc_region'],
                'loc_start': exon['loc_start'],
                'loc_end': exon['loc_end'],
                'loc_strand': exon['loc_strand'],
                'accession': f"{transcript['stable_id']}.{transcript['stable_id_version']}",
                'ensembl_id': ensembl_id,
                'gene': next((gene['name'] for gene in transcript.get('genes', []) if gene['name']), identifier),
                'entrez_id': entrez_id,
                'exon_id': exon['stable_id'],
                'exon_number': index,
                'transcript_biotype': transcript.get('biotype', ''),
                'mane_transcript': mane_transcript,
                'mane_transcript_type': mane_transcript_type,
                'status': None,  # Initialize status as None
                'identifier': identifier,
                'five_prime_utr': {
                    'start': transcript.get('five_prime_utr_start'),
                    'end': transcript.get('five_prime_utr_end')
                },
                'three_prime_utr': {
                    'start': transcript.get('three_prime_utr_start'),
                    'end': transcript.get('three_prime_utr_end')
                }
            }
            
            # Set status based on MANE type if present, handling case-insensitively
            if mane_transcript_type:
                mane_type_upper = mane_transcript_type.upper()
                if mane_type_upper == 'MANE SELECT':
                    result['status'] = 'MANE Select transcript'
                elif mane_type_upper == 'MANE PLUS CLINICAL':
                    result['status'] = 'MANE Plus Clinical transcript'
            elif transcript.get('warning'):
                result['status'] = transcript['warning'].get('message') if isinstance(transcript['warning'], dict) else transcript['warning']
            
            results.append(result)

        print(f"Final result for transcript: {results[-1]}")

    return results

def process_grch38_mane_select(data: List[Dict], base_accession: str, identifier: str) -> Optional[List[Dict]]:
    """
    Helper function to process GRCh38 MANE SELECT transcripts.
    """
    grch38_transcripts = [t for t in data if t['assembly'] == 'GRCh38']
    mane_select = next((t for t in grch38_transcripts 
                      if t.get('mane_transcript_type') == 'MANE SELECT'), None)
    
    if mane_select:
        warning = {
            'message': f"No direct GRCh37 transcript found. Using GRCh38 MANE SELECT transcript {mane_select['stable_id']} to find matching GRCh37 version",
            'identifier': identifier,
            'type': 'assembly_mapping'
        }
        matching_grch37 = [t for t in data 
                         if t['assembly'] == 'GRCh37' 
                         and t['stable_id'] == mane_select['stable_id']]
        
        if matching_grch37:
            selected = max(matching_grch37, 
                         key=lambda x: int(x.get('stable_id_version', 0)))
            selected['warning'] = warning
            return process_transcripts([selected], base_accession)
    return None

def process_base_accession(data: List[Dict], base_accession: str, identifier: str) -> Optional[List[Dict]]:
    """
    Helper function to process base accession transcripts.
    """
    warning = {
        'message': "No MANE SELECT transcript found. Using base accession for GRCh37 lookup - clinical review recommended",
        'identifier': identifier,
        'type': 'assembly_mapping'
    }
    grch37_transcripts = [t for t in data if t['assembly'] == 'GRCh37']
    if grch37_transcripts:
        selected = max(grch37_transcripts, 
                     key=lambda x: int(x.get('stable_id_version', 0)))
        selected['warning'] = warning
        return process_transcripts([selected], base_accession)
    return None

def process_coordinate_data(data: List[Dict], chrom: str, start: int, end: int, coord: str) -> List[Dict]:
    """
    Processes coordinate data to extract relevant gene overlap information.
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
    