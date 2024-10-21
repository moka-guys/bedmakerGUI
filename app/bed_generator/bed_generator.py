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

class BedGenerator:
    @staticmethod
    def format_bed_line(r: Dict, padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        """
        Formats a single BED line based on the specified format type.

        Args:
            r (Dict): A dictionary containing BED entry data.
            padding (int): The number of bases to add to the start and end positions.
            format_type (str): The format type for the BED line ('data', 'sambamba', 'exome_depth', 'cnv').
            add_chr_prefix (bool): Whether to add 'chr' prefix to chromosomes.

        Returns:
            str: The formatted BED line.
        """
        loc_region = f"chr{r['loc_region']}" if add_chr_prefix else r['loc_region']
        loc_start = r['loc_start'] - padding
        loc_end = r['loc_end'] + padding
        gene = r['gene']
        accession = r['accession']
        entrez_id = r['entrez_id']
        
        if format_type == 'data':
            return f"{loc_region}\t{loc_start}\t{loc_end}\t{entrez_id}\t{gene};{accession}"
        elif format_type == 'sambamba':
            loc_strand = '+' if r.get('loc_strand', 1) > 0 else '-'
            return f"{loc_region}\t{loc_start}\t{loc_end}\t{r['loc_region']}-{loc_start}-{loc_end}\t0\t{loc_strand}\t{gene};{accession}\t{entrez_id}"
        elif format_type == 'exome_depth':
            exon_number = r.get('exon_number', '')
            return f"{loc_region}\t{loc_start}\t{loc_end}\t{gene}_{exon_number}"
        elif format_type == 'cnv':
            return f"{loc_region}\t{loc_start}\t{loc_end}\t{accession}"
        else:
            raise ValueError("Invalid format type")

    @classmethod
    def create_bed(cls, results: List[Dict], padding: int, format_type: str, add_chr_prefix: bool = False) -> str:
        return '\n'.join([cls.format_bed_line(r, padding, format_type, add_chr_prefix) for r in results])

    @classmethod
    def create_data_bed(cls, results: List[Dict], padding: int, add_chr_prefix: bool = False) -> str:
        return cls.create_bed(results, padding, 'data', add_chr_prefix)

    @classmethod
    def create_sambamba_bed(cls, results: List[Dict], padding: int, add_chr_prefix: bool = False) -> str:
        return cls.create_bed(results, padding, 'sambamba', add_chr_prefix)

    @classmethod
    def create_exome_depth_bed(cls, results: List[Dict], padding: int, add_chr_prefix: bool = False) -> str:
        return cls.create_bed(results, padding, 'exome_depth', add_chr_prefix)

    @classmethod
    def create_cnv_bed(cls, results: List[Dict], padding: int, add_chr_prefix: bool = False) -> str:
        return cls.create_bed(results, padding, 'cnv', add_chr_prefix)

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