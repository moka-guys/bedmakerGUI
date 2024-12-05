"""
validators.py - Contains validation functions for the bed generator application.

Functions:
- validate_coordinates: Validates the format of genomic coordinates from frontend.
"""

import re
from typing import Optional

def validate_coordinates(coordinates: str) -> Optional[str]:
    """
    Validates the format of genomic coordinates from frontend.

    Args:
        coordinates (str): The genomic coordinates in the format 'chromosome:start-end'.

    Returns:
        Optional[str]: An error message if the format is invalid, otherwise None.
    """
    # Validates the coordinate format using a regular expression.
    regex = r'^(chr)?([1-9][0-9]?|[XYM]):(\d+)-(\d+)$'
    match = re.match(regex, coordinates, re.IGNORECASE)

    if not match:
        return "Invalid format. Use 'chromosome:start-end' (e.g., 1:200-300 or chr1:200-300)."

    start, end = int(match.group(3)), int(match.group(4))

    # Ensures the end position is not less than the start position
    if start > end:
        return "End position cannot be less than start position."

    return None 