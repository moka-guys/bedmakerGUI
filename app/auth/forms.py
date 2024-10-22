from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField
from wtforms.validators import ValidationError

class SettingsForm(FlaskForm):
    data_padding = IntegerField('Data Padding')
    sambamba_padding = IntegerField('Sambamba Padding')
    exomeDepth_padding = IntegerField('ExomeDepth Padding')
    cnv_padding = IntegerField('CNV Padding')
    submit = SubmitField('Save Settings')
    def validate_data_padding(self, field):
        self._validate_non_negative(field)

    def validate_sambamba_padding(self, field):
        self._validate_non_negative(field)

    def validate_exomeDepth_padding(self, field):
        self._validate_non_negative(field)

    def validate_cnv_padding(self, field):
        self._validate_non_negative(field)

    def _validate_non_negative(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError('Value must be 0 or greater')
