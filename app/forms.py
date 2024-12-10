from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField, SelectField, TextAreaField, FileField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional, InputRequired

class SettingsForm(FlaskForm):
    data_padding = IntegerField('Data Padding', validators=[InputRequired(), NumberRange(min=0, message="Padding must be 0 or greater")], default=0)
    sambamba_padding = IntegerField('Sambamba Padding', validators=[InputRequired(), NumberRange(min=0, message="Padding must be 0 or greater")], default=0)
    exomeDepth_padding = IntegerField('ExomeDepth Padding', validators=[InputRequired(), NumberRange(min=0, message="Padding must be 0 or greater")], default=0)
    cnv_padding = IntegerField('CNV Padding', validators=[InputRequired(), NumberRange(min=0, message="Padding must be 0 or greater")], default=0)
    data_snp_padding = IntegerField('Data SNP Padding', validators=[InputRequired(), NumberRange(min=0, message="SNP padding must be 0 or greater")], default=0)
    sambamba_snp_padding = IntegerField('Sambamba SNP Padding', validators=[InputRequired(), NumberRange(min=0, message="SNP padding must be 0 or greater")], default=0)
    exomeDepth_snp_padding = IntegerField('ExomeDepth SNP Padding', validators=[InputRequired(), NumberRange(min=0, message="SNP padding must be 0 or greater")], default=0)
    cnv_snp_padding = IntegerField('CNV SNP Padding', validators=[InputRequired(), NumberRange(min=0, message="SNP padding must be 0 or greater")], default=0)
    data_include_5utr = BooleanField("Include 5' UTR for Data BED")
    data_include_3utr = BooleanField("Include 3' UTR for Data BED")
    sambamba_include_5utr = BooleanField("Include 5' UTR for Sambamba BED")
    sambamba_include_3utr = BooleanField("Include 3' UTR for Sambamba BED")
    exomeDepth_include_5utr = BooleanField("Include 5' UTR for ExomeDepth BED")
    exomeDepth_include_3utr = BooleanField("Include 3' UTR for ExomeDepth BED")
    cnv_include_5utr = BooleanField("Include 5' UTR for CNV BED")
    cnv_include_3utr = BooleanField("Include 3' UTR for CNV BED")
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