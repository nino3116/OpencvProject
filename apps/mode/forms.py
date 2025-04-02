from flask_wtf import FlaskForm  # type: ignore
from wtforms import SelectField,IntegerField,StringField,DateTimeLocalField,TextAreaField,SubmitField  # type: ignore
from wtforms.validators import Length  # type: ignore

# Form for Add Mode Schedule
class ScheduleForm(FlaskForm):
    mode_type = SelectField(
        "모드",choices=['Running','Cleaning','Secure']
    )
    
    people_cnt = IntegerField(
        "인원",
    )
    
    rep_name = StringField(
        "대표자"
    )
    
    start_time = DateTimeLocalField(
        "시작 시각"
    )
    end_time = DateTimeLocalField(
        "종료 시각"
    )
    
    memo = TextAreaField(
        "메모"
    )

    submit = SubmitField("신규 등록")

