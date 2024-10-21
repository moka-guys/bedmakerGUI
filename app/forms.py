from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField, SelectField, TextAreaField, FileField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional

class SettingsForm(FlaskForm):
    data_padding = IntegerField('Data Padding', validators=[DataRequired(), NumberRange(min=0)])
    sambamba_padding = IntegerField('Sambamba Padding', validators=[DataRequired(), NumberRange(min=0)])
    exomeDepth_padding = IntegerField('ExomeDepth Padding', validators=[DataRequired(), NumberRange(min=0)])
    cnv_padding = IntegerField('CNV Padding', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Save Settings')

class BedGeneratorForm(FlaskForm):
    assembly = SelectField('Assembly', choices=[('GRCh37', 'GRCh37 (hg19)'), ('GRCh38', 'GRCh38 (hg38)')], validators=[DataRequired()])
    coordinates = TextAreaField('Coordinates', validators=[Optional()])
    bedFiles = FileField('BED Files', validators=[Optional()])
    csvFile = FileField('CSV/TXT File', validators=[Optional()])
    identifiers = TextAreaField('Identifiers', validators=[Optional()])
    include5UTR = BooleanField("Include 5' UTR", default=False)
    include3UTR = BooleanField("Include 3' UTR", default=False)
    padding_5 = IntegerField("5' Padding", validators=[Optional()])
    padding_3 = IntegerField("3' Padding", validators=[Optional()])
    submit = SubmitField('Generate BED File')