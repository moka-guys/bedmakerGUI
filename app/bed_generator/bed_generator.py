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
            print(f"Formatting BED line for result: {result}")  # Debug print
            
            # Format chromosome/region
            loc_region = str(result['loc_region'])
            if add_chr_prefix and not loc_region.startswith('chr'):
                loc_region = f'chr{loc_region}'

            # Get coordinates - use the processed coordinates directly
            start = int(result['loc_start'])
            end = int(result['loc_end'])
            
            print(f"Initial coordinates: start={start}, end={end}")  # Debug print
            
            # Apply padding if specified in the result
            padding = int(result.get('_padding', 0))
            if padding > 0:
                start = max(0, start - padding)
                end = end + padding
                
            print(f"After padding: start={start}, end={end}")  # Debug print

            # Format the basic BED fields (chromosome, start, end)
            bed_line = f"{loc_region}\t{start}\t{end}"
            
            # Add format-specific fields
            if format_type in cls.BED_FORMATS:
                format_fields = cls.BED_FORMATS[format_type]['fields']
                additional_fields = [field(result, padding) for field in format_fields]
                bed_line += '\t' + '\t'.join(additional_fields)
            
            print(f"Final BED line: {bed_line}")  # Debug print
            return bed_line
            
        except Exception as e:
            current_app.logger.error(f"Error formatting BED line: {str(e)}")
            current_app.logger.error(f"Result: {result}")
            current_app.logger.error(f"Padding: {padding}")
            raise

    @classmethod
    def create_bed(cls, results: List[Dict], padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        return '\n'.join([cls.format_bed_line(r, padding, format_type, add_chr_prefix) for r in results])

    # Single factory method for generating BED content in any supported format
    @classmethod
    def create_formatted_bed(cls, results: List[Dict], format_type: str, add_chr_prefix: bool = False) -> str:
        """Creates formatted BED file content."""
        print(f"\nCreating formatted BED with format_type: {format_type}")  # Debug print
        bed_lines = []
        
        for result in results:
            try:
                print(f"\nProcessing result for BED line: {result}")  # Debug print
                bed_line = cls.format_bed_line(
                    result=result,
                    padding=result.get('_padding', 0),  # Get padding from result
                    format_type=format_type,
                    add_chr_prefix=add_chr_prefix
                )
                bed_lines.append(bed_line)
            except Exception as e:
                current_app.logger.error(f"Error formatting BED line for result {result}: {str(e)}")
                current_app.logger.error("Full traceback:", exc_info=True)
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