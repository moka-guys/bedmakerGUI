from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'user'  # Make sure this matches your actual table name
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

    bed_file = db.relationship('BedFile', back_populates='entries')

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_padding = db.Column(db.Integer, default=0)
    sambamba_padding = db.Column(db.Integer, default=0)
    exomeDepth_padding = db.Column(db.Integer, default=0)
    cnv_padding = db.Column(db.Integer, default=0)

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
            'cnv_padding': self.cnv_padding
        }