"""
models.py - Defines the database models for the application.

Models:
- User: Represents user accounts with authentication and role information.
- BedFile: Represents a BED file submission, including metadata and processing status.
- BedEntry: Represents individual entries within a BED file, containing genomic information.
- Settings: Stores application-wide settings, particularly padding values for various operations.

Each model corresponds to a table in the database and includes relationships and methods
as needed for the application's functionality.
"""

from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json
from typing import List, Dict

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    is_authorizer = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(120), index=True, unique=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(128))
    status = db.Column(db.String(20), default='pending')
    submitter_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    authorizer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    assembly = db.Column(db.String(10), default='GRCh38')
    initial_query = db.Column(db.Text)
    include_3utr = db.Column(db.Boolean, default=False)
    include_5utr = db.Column(db.Boolean, default=False)
    warning = db.Column(db.Text)

    submitter = db.relationship('User', foreign_keys=[submitter_id], backref='submitted_bed_files')
    authorizer = db.relationship('User', foreign_keys=[authorizer_id], backref='authorized_bed_files')
    entries = db.relationship('BedEntry', back_populates='bed_file', cascade='all, delete-orphan')

class BedEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bed_file_id = db.Column(db.Integer, db.ForeignKey('bed_file.id'), nullable=False)
    chromosome = db.Column(db.String(50))
    start = db.Column(db.Integer)
    end = db.Column(db.Integer)
    gene = db.Column(db.String(100))
    entrez_id = db.Column(db.String(50))
    accession = db.Column(db.String(50))
    exon_id = db.Column(db.String(50))
    exon_number = db.Column(db.Integer)
    transcript_biotype = db.Column(db.String(50))
    mane_transcript = db.Column(db.String(50))
    mane_transcript_type = db.Column(db.String(50))
    warning = db.Column(db.String(255))

    bed_file = db.relationship('BedFile', back_populates='entries')

    @classmethod
    def create_entries(cls, bed_file_id: int, results: List[Dict], padding_5: int = 0, padding_3: int = 0) -> List['BedEntry']:
        """
        Creates BED entries for a given file ID.
        
        Args:
            bed_file_id: ID of the parent BED file
            results: List of result dictionaries containing entry data
            padding_5: 5' padding to apply (default: 0)
            padding_3: 3' padding to apply (default: 0)
            
        Returns:
            List of created BedEntry instances
        """
        entries = []
        for result in results:
            entry = cls(
                bed_file_id=bed_file_id,
                chromosome=result['loc_region'],
                start=int(result['loc_start']) - padding_5,
                end=int(result['loc_end']) + padding_3,
                entrez_id=result['entrez_id'],
                gene=result['gene'],
                accession=result['accession'],
                exon_id=result.get('exon_id'),
                exon_number=result.get('exon_number'),
                transcript_biotype=result.get('transcript_biotype'),
                mane_transcript=result.get('mane_transcript'),
                mane_transcript_type=result.get('mane_transcript_type'),
                warning=json.dumps(result.get('warning')) if result.get('warning') else None
            )
            entries.append(entry)
            db.session.add(entry)
        return entries

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_padding = db.Column(db.Integer, default=0)
    sambamba_padding = db.Column(db.Integer, default=0)
    exomeDepth_padding = db.Column(db.Integer, default=0)
    cnv_padding = db.Column(db.Integer, default=0)
    data_include_5utr = db.Column(db.Boolean, default=False)
    data_include_3utr = db.Column(db.Boolean, default=False)
    sambamba_include_5utr = db.Column(db.Boolean, default=False)
    sambamba_include_3utr = db.Column(db.Boolean, default=False)
    exomeDepth_include_5utr = db.Column(db.Boolean, default=False)
    exomeDepth_include_3utr = db.Column(db.Boolean, default=False)
    cnv_include_5utr = db.Column(db.Boolean, default=False)
    cnv_include_3utr = db.Column(db.Boolean, default=False)

    @classmethod
    def get_settings(cls):
        settings = cls.query.first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings

    def to_dict(self):
        return {
            'data_padding': self.data_padding,
            'sambamba_padding': self.sambamba_padding,
            'exomeDepth_padding': self.exomeDepth_padding,
            'cnv_padding': self.cnv_padding,
            'data_include_5utr': self.data_include_5utr,
            'data_include_3utr': self.data_include_3utr,
            'sambamba_include_5utr': self.sambamba_include_5utr,
            'sambamba_include_3utr': self.sambamba_include_3utr,
            'exomeDepth_include_5utr': self.exomeDepth_include_5utr,
            'exomeDepth_include_3utr': self.exomeDepth_include_3utr,
            'cnv_include_5utr': self.cnv_include_5utr,
            'cnv_include_3utr': self.cnv_include_3utr
        }

    def update_from_form(self, form):
        """Updates settings from form data."""
        fields = [
            'data_padding', 'sambamba_padding', 'exomeDepth_padding', 'cnv_padding',
            'data_include_5utr', 'data_include_3utr',
            'sambamba_include_5utr', 'sambamba_include_3utr',
            'exomeDepth_include_5utr', 'exomeDepth_include_3utr',
            'cnv_include_5utr', 'cnv_include_3utr'
        ]
        for field in fields:
            setattr(self, field, getattr(form, field).data)
        db.session.commit()

    def populate_form(self, form):
        """Populates a form with current settings values."""
        fields = [
            'data_padding', 'sambamba_padding', 'exomeDepth_padding', 'cnv_padding',
            'data_include_5utr', 'data_include_3utr',
            'sambamba_include_5utr', 'sambamba_include_3utr',
            'exomeDepth_include_5utr', 'exomeDepth_include_3utr',
            'cnv_include_5utr', 'cnv_include_3utr'
        ]
        for field in fields:
            getattr(form, field).data = getattr(self, field)
