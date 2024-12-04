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
from app.models import BedFile
from app.extensions import db

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
                lambda r, p: f"{r['loc_region']}-{r['loc_start']}-{r['loc_end']}", 
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
                lambda r, _: str(r['entrez_id'])
            ]
        }
    }

    @classmethod
    def format_bed_line(cls, result: Dict, padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        """Formats a single BED line."""
        try:
            # Format chromosome/region
            loc_region = str(result['loc_region'])
            if add_chr_prefix and not loc_region.lower().startswith('chr'):
                loc_region = f'chr{loc_region}'

            # Get coordinates
            start = int(result['loc_start'])
            end = int(result['loc_end'])
            
            # Apply padding if this is not a SNP
            if not result.get('is_snp', False):
                padding_value = int(result.get('_padding', padding))
                if padding_value > 0:
                    start = max(0, start - padding_value)
                    end = end + padding_value
            
            # Format the basic BED fields
            bed_line = f"{loc_region}\t{start}\t{end}"
            
            # Add format-specific fields
            if format_type in cls.BED_FORMATS:
                format_config = cls.BED_FORMATS[format_type]
                additional_fields = []
                for field_func in format_config['fields']:
                    try:
                        field_value = field_func(result, padding)
                        additional_fields.append(str(field_value))
                    except Exception as e:
                        current_app.logger.error(f"Error processing field for format {format_type}: {str(e)}")
                        raise
                
                if additional_fields:
                    bed_line += '\t' + '\t'.join(additional_fields)

            return bed_line
            
        except Exception as e:
            current_app.logger.error(f"Error formatting BED line: {str(e)}")
            current_app.logger.error(f"Result: {result}")
            raise

    @classmethod
    def create_bed(cls, results: List[Dict], padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        return '\n'.join([cls.format_bed_line(r, padding, format_type, add_chr_prefix) for r in results])

    # Single factory method for generating BED content in any supported format
    @classmethod
    def create_formatted_bed(cls, results: List[Dict], format_type: str, add_chr_prefix: bool = False) -> str:
        """Creates formatted BED file content."""
        print(f"\n=== BedGenerator.create_formatted_bed ===")
        print(f"Format type: {format_type}")
        
        bed_lines = []
        for result in results:
            try:
                print(f"\nInput result:")
                print(f"Gene: {result.get('gene')}")
                print(f"Coordinates: {result.get('loc_start')}-{result.get('loc_end')}")
                print(f"Existing padding: {result.get('_padding')}")
                print(f"UTR info - 5': {result.get('five_prime_utr')}, 3': {result.get('three_prime_utr')}")
                
                # Don't apply additional padding if already present
                padding = 0 if result.get('_padding') is not None else result.get('_padding', 0)
                print(f"Applied padding: {padding}")
                
                bed_line = cls.format_bed_line(
                    result=result,
                    padding=padding,
                    format_type=format_type,
                    add_chr_prefix=add_chr_prefix
                )
                bed_lines.append(bed_line)
            except Exception as e:
                current_app.logger.error(f"Error formatting BED line: {str(e)}")
                continue
        
        return '\n'.join(bed_lines)

def generate_bed_files(filename: str, results: List[Dict], settings: Dict) -> None:
    """
    Generates different BED file formats and stores them both in the database and filesystem.
    """
    bed_dir = current_app.config.get('DRAFT_BED_FILES_DIR')
    os.makedirs(bed_dir, exist_ok=True)

    # Map of bed types to their creation functions
    bed_types = {
        'data': lambda r, p: BedGenerator.create_formatted_bed(r, 'data', False),
        'sambamba': lambda r, p: BedGenerator.create_formatted_bed(r, 'sambamba', False),
        'exomeDepth': lambda r, p: BedGenerator.create_formatted_bed(r, 'exomeDepth', False),
        'cnv': lambda r, p: BedGenerator.create_formatted_bed(r, 'cnv', False)
    }

    # Get the actual filename without the type suffix
    base_filename = filename.rsplit('_', 1)[0] if '_' in filename else filename

    for bed_type, create_function in bed_types.items():
        # Only process if this is the matching bed type for the current file
        if filename.endswith(f"_{bed_type}"):
            padding = settings.get('padding', {}).get(bed_type, 0)
            content = create_function(results, padding)
            
            # Save to filesystem
            file_path = os.path.join(bed_dir, f"{filename}.bed")
            with open(file_path, 'w') as f:
                f.write(content)
                
            # Save to database using the exact filename
            bed_file = BedFile.query.filter_by(filename=filename).first()
            if bed_file:
                print(f"Found BedFile record for {filename}")
                bed_file.file_blob = content.encode('utf-8')
                db.session.add(bed_file)
                db.session.commit()
                break  # Exit after processing the matching type