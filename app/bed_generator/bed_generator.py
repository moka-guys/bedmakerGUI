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

from typing import List, Dict, Union
from flask import current_app
import os

class BedGenerator:
    # Define format configurations as a class attribute
    BED_FORMATS = {
        'data': {
            'fields': [
                lambda r, _: str(r['entrez_id']),
                lambda r, _: f"{r['gene']};{r['accession']}"
            ]
        },
        'sambamba': {
            'fields': [
                lambda r, p: f"{r['loc_region']}-{int(r['loc_start']) - p}-{int(r['loc_end']) + p}", 
                lambda r, _: "0",
                lambda r, _: '+' if r.get('loc_strand', 1) > 0 else '-',
                lambda r, _: f"{r['gene']};{r['accession']}",
                lambda r, _: str(r['entrez_id'])
            ]
        },
        'exomeDepth': {
            'fields': [
                lambda r, _: f"{r['gene']}_{r.get('exon_number', '')}"
            ]
        },
        'cnv': {
            'fields': [
                lambda r, _: r['accession']
            ]
        }
    }

    @classmethod
    def format_bed_line(cls, result: Dict, padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        """Formats a single BED line."""
        try:
            # Ensure padding is an integer
            padding = int(padding)
            
            # Format chromosome/region
            loc_region = str(result['loc_region'])
            if add_chr_prefix and not loc_region.startswith('chr'):
                loc_region = f'chr{loc_region}'

            # Get strand information (default to forward/1 if not specified)
            strand = int(result.get('loc_strand', 1))
            
            # Use the stored original positions if available and ensure they're integers
            original_start = int(result.get('original_loc_start', result['loc_start']))
            original_end = int(result.get('original_loc_end', result['loc_end']))
            
            # Apply padding based on strand direction
            if strand > 0:  # Forward strand
                loc_start = original_start - padding
                loc_end = original_end + padding
            else:  # Reverse strand
                loc_start = original_start - padding
                loc_end = original_end + padding
            
            # Get additional fields based on format
            format_config = cls.BED_FORMATS.get(format_type)
            if not format_config:
                raise ValueError(f"Unknown format type: {format_type}")
            
            additional_fields = [field_func(result, padding) for field_func in format_config['fields']]
            
            return '\t'.join([loc_region, str(loc_start), str(loc_end)] + additional_fields)
            
        except Exception as e:
            current_app.logger.error(f"Error in format_bed_line: {str(e)}")
            current_app.logger.error(f"Result: {result}")
            current_app.logger.error(f"Padding: {padding}, type: {type(padding)}")
            raise

    @classmethod
    def create_bed(cls, results: List[Dict], padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        return '\n'.join([cls.format_bed_line(r, padding, format_type, add_chr_prefix) for r in results])

    # Single factory method for generating BED content in any supported format
    @classmethod
    def create_formatted_bed(cls, results, format_type, add_chr_prefix=False):
        """Creates formatted BED file content."""
        bed_lines = []
        for result in results:
            try:
                # Get the padding from the result's _padding field
                padding = int(result.get('_padding', 0))
                
                current_app.logger.debug(f"Processing result with padding {padding}: {result}")
                
                bed_line = cls.format_bed_line(
                    result=result,
                    padding=padding,  # Pass the padding value correctly
                    format_type=format_type,
                    add_chr_prefix=add_chr_prefix
                )
                bed_lines.append(bed_line)
            except Exception as e:
                current_app.logger.error(f"Error formatting BED line for result {result}: {str(e)}")
                current_app.logger.error(f"Padding value: {result.get('_padding')}, type: {type(result.get('_padding'))}")
                current_app.logger.error(f"Full traceback:", exc_info=True)
                continue
        
        return '\n'.join(bed_lines)

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
        'exomeDepth': lambda r, p: BedGenerator.create_formatted_bed(r, 'exomeDepth', p),
        'CNV': lambda r, p: BedGenerator.create_formatted_bed(r, 'cnv', p)
    }

    for bed_type, create_function in bed_types.items():
        padding = settings.get('padding', {}).get(bed_type, 0)
        content = create_function(results, padding)
        
        file_path = os.path.join(bed_dir, f"{filename}_{bed_type}.bed")
        with open(file_path, 'w') as f:
            f.write(content)