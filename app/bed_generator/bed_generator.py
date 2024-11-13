"""
bed_generator.py - Provides functions to format individual BED lines and create content for different use cases.

Functions:
- format_bed_line: Formats a single BED line based on the specified format type.
- create_bed: Creates BED file content from a list of results in a specified format.
- create_data_bed: Creates BED file content in the 'data' format.
- create_sambamba_bed: Creates BED file content in the 'sambamba' format.
- create_exome_depth_bed: Creates BED file content in the 'exome_depth' format.
- create_cnv_bed: Creates BED file content in the 'cnv' format.
- create_raw_bed: Creates raw BED file content without additional formatting.
"""

from typing import List, Dict
from flask import current_app
import os

class BedGenerator:
    # Define format configurations as a class attribute
    BED_FORMATS = {
        'data': {
            'fields': [
                lambda r: str(r['entrez_id']),
                lambda r: f"{r['gene']};{r['accession']}"
            ]
        },
        'sambamba': {
            'fields': [
                lambda r: f"{r['loc_region']}-{r['loc_start']}-{r['loc_end']}", 
                lambda r: "0",
                lambda r: '+' if r.get('loc_strand', 1) > 0 else '-',
                lambda r: f"{r['gene']};{r['accession']}",
                lambda r: str(r['entrez_id'])
            ]
        },
        'exome_depth': {
            'fields': [
                lambda r: f"{r['gene']}_{r.get('exon_number', '')}"
            ]
        },
        'cnv': {
            'fields': [
                lambda r: r['accession']
            ]
        }
    }

    @staticmethod
    def format_bed_line(r: Dict, padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        """Formats a single BED line based on the specified format type."""
        if format_type not in BedGenerator.BED_FORMATS:
            raise ValueError("Invalid format type")

        # Basic BED fields
        loc_region = f"chr{r['loc_region']}" if add_chr_prefix else r['loc_region']
        
        # Get strand information (default to forward/1 if not specified)
        strand = r.get('loc_strand', 1)
        
        # Apply padding based on strand direction
        if strand > 0:  # Forward strand
            loc_start = r['loc_start'] - padding
            loc_end = r['loc_end'] + padding
        else:  # Reverse strand
            loc_start = r['loc_start'] - padding
            loc_end = r['loc_end'] + padding
        
        # Get additional fields based on format
        format_config = BedGenerator.BED_FORMATS[format_type]
        additional_fields = [field_func(r) for field_func in format_config['fields']]
        
        return '\t'.join([loc_region, str(loc_start), str(loc_end)] + additional_fields)

    @classmethod
    def create_bed(cls, results: List[Dict], padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        return '\n'.join([cls.format_bed_line(r, padding, format_type, add_chr_prefix) for r in results])

    # Single factory method for generating BED content in any supported format
    @classmethod
    def create_formatted_bed(cls, results: List[Dict], format_type: str, padding: int = 0, add_chr_prefix: bool = False) -> str:
        """Factory method to create BED content in any supported format."""
        return cls.create_bed(results, padding, format_type, add_chr_prefix)

    @staticmethod
    def create_raw_bed(results: List[Dict], add_chr_prefix: bool = False) -> str:
        """
        Creates raw BED file content without additional formatting.

        Args:
            results (List[Dict]): A list of dictionaries containing BED entry data.
            add_chr_prefix (bool): Whether to add 'chr' prefix to chromosomes.

        Returns:
            str: The raw BED file content.
        """
        return '\n'.join([f"{'chr' if add_chr_prefix else ''}{r['loc_region']}\t{r['loc_start']}\t{r['loc_end']}\t{r['gene']}" for r in results])

def generate_bed_files(filename: str, results: List[Dict], settings: Dict) -> None:
    """
    Generates different BED file formats based on stored settings in database.
    """
    bed_dir = current_app.config.get('DRAFT_BED_FILES_DIR')
    os.makedirs(bed_dir, exist_ok=True)

    bed_types = {
        'raw': lambda r, p: BedGenerator.create_raw_bed(r, add_chr_prefix=False),
        'data': lambda r, p: BedGenerator.create_formatted_bed(r, 'data', p),
        'sambamba': lambda r, p: BedGenerator.create_formatted_bed(r, 'sambamba', p),
        'exomeDepth': lambda r, p: BedGenerator.create_formatted_bed(r, 'exome_depth', p),
        'CNV': lambda r, p: BedGenerator.create_formatted_bed(r, 'cnv', p)
    }

    for bed_type, create_function in bed_types.items():
        padding = settings.get('padding', {}).get(bed_type, 0)
        content = create_function(results, padding)
        
        file_path = os.path.join(bed_dir, f"{filename}_{bed_type}.bed")
        with open(file_path, 'w') as f:
            f.write(content)