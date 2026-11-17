"""Collect an explicit end to the project list without replacing earlier projects."""
import re
from backend.app.services.assistant_answers import fold
from backend.app.schemas.assistant import IntakeSignal


def project_list_signal(intake, path, text):
    awaiting = intake.get('project_next_index') == len(intake['profile']['project']) and path == f"project.{len(intake['profile']['project'])}.project_name"
    if path != 'project.more' and not awaiting:
        return None
    plain = fold(' '.join(text.split())).strip(' .!…')
    plain = re.sub(r'^(?:(?:minh|toi|em) )?', '', plain)
    plain = re.sub(r' (?:nhe|nha|a)$', '', plain)
    done = {'chua co', 'khong', 'khong con', 'khong co', 'khong con du an nao', 'khong co du an nao khac',
            'het roi', 'het', 'da het', 'da nhap het', 'xong', 'da xong', 'chi co du an nay',
            'chi co mot du an', 'khong them nua', 'khong muon them', 'bo qua', 'de sau'}
    more = {'co', 'con', 'co con', 'van con', 'con nua', 'co them', 'them du an', 'them du an khac',
            'muon them du an', 'con du an khac', 'con mot du an nua', 'chua het'}
    if plain in done:
        return IntakeSignal(kind='section_complete',section='project',evidence=text)
    if plain in more:
        return IntakeSignal(kind='more_entries',section='project',evidence=text)
    return None
