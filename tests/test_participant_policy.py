import uuid
import pytest
from app import app
from database import init_db, register_team, get_db_connection, get_client_question
from event_manager import end_event, start_event, reset_event_data
from quiz import QUESTIONS
from participant_policy import FEEDBACK_QUESTIONS

@pytest.fixture
def client():
    init_db(force_reset=True)
    app.config['TESTING'] = True
    with app.test_client() as client:
        client.post('/register', data={'name':'Policy team','member1':'One','member2':'Two'})
        yield client

def signal(client, kind, event_id=None):
    return client.post('/api/activity', json={'event_type':kind,'event_id':event_id or uuid.uuid4().hex})

def open_quiz(client):
    end_event()
    with client.session_transaction() as sess:
        sess['is_admin'] = True
    assert client.post('/api/admin/quiz-action', json={'action':'open'}).status_code == 200
    signal(client, 'fullscreen_enter')
    assert client.post('/api/quiz/start', json={}).status_code == 200

def complete_quiz(client):
    open_quiz(client)
    for i,(qid,_,_,key) in enumerate(QUESTIONS):
        answer=client.post('/api/quiz/answer', json={'question_id':qid,'answer_index':key if i else (key+1)%4})
        assert answer.status_code == 200
    return answer.get_json()['quiz']

def test_guard_required_from_login_through_every_round(client):
    assert b'participant-gate' in client.get('/waiting').data
    assert b'participant-gate' in client.get('/').data
    start_event()
    for route,data in [('/api/submit-bug-fix',{'question_id':'Q01'}),('/api/powerup/rubber-duck',{'question_id':'Q01'}),('/api/quiz/start',{})]:
        denied=client.post(route,json=data)
        assert denied.status_code == 403 and denied.get_json()['fullscreen_required']
    assert signal(client,'fullscreen_enter').get_json()['is_fullscreen']
    assert client.post('/api/powerup/rubber-duck',json={'question_id':'Q01'}).status_code==200
    signal(client,'fullscreen_leave')
    assert client.post('/api/quiz/start',json={}).get_json()['fullscreen_required']

def test_two_exits_persist_across_logout_login_and_block_all_rounds(client):
    signal(client,'fullscreen_enter')
    first=signal(client,'fullscreen_exit','first').get_json()
    assert first['violations']==1 and not first['blocked'] and not first['is_fullscreen']
    retry=signal(client,'fullscreen_exit','first').get_json()
    assert retry['violations']==1 and not retry['recorded']
    client.get('/logout')
    assert client.post('/register',data={'action':'login','team_lookup':'Policy team'}).status_code==302
    signal(client,'fullscreen_enter')
    second=signal(client,'fullscreen_exit','second').get_json()
    assert second['violations']==2 and second['blocked']
    for route in ['/api/quiz/status','/api/team-progress','/api/question/Q01']:
        denied=client.get(route)
        assert denied.status_code==403 and denied.get_json()['blocked']
    assert client.get('/result').location.endswith('/blocked')
    client.get('/logout')
    assert client.post('/register',data={'action':'login','team_lookup':'Policy team'}).status_code==403
    conn=get_db_connection()
    assert conn.execute('SELECT COUNT(*) FROM fullscreen_events WHERE event_type = ?',('fullscreen_exit',)).fetchone()[0]==2
    conn.close()

def test_focus_departure_signals_deduplicate_and_admin_can_restore(client):
    # Not yet participating: moving focus cannot punish an account behind the entry gate.
    for kind in ['tab_hidden','window_blur','window_focus','window_visible']:
        assert signal(client, kind).status_code == 200
    assert client.get('/api/fullscreen/status').get_json()['violations'] == 0
    signal(client,'fullscreen_enter')
    first = signal(client,'window_blur').get_json()
    assert first['counted'] and first['violations'] == 1 and not first['is_fullscreen']
    for kind in ['tab_hidden', 'fullscreen_exit', 'window_blur']:
        duplicate = signal(client,kind).get_json()
        assert not duplicate['counted'] and duplicate['violations'] == 1
    for kind in ['window_focus','window_visible']:
        signal(client,kind)
    assert not client.get('/api/fullscreen/status').get_json()['is_fullscreen']
    signal(client,'fullscreen_enter')
    assert signal(client,'tab_hidden').get_json()['blocked']
    with client.session_transaction() as sess:
        team_id=sess['team_id'];sess['is_admin']=True
    assert client.post('/api/admin/toggle-team',json={'team_id':team_id}).status_code==200
    restored=client.get('/api/fullscreen/status').get_json()
    assert not restored['blocked'] and restored['violations']==0 and not restored['is_fullscreen']
    assert reset_event_data('RESET EVENT')[0]
    conn=get_db_connection()
    for table in ['participant_security','fullscreen_sessions','fullscreen_events','quiz_feedback']:
        assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
    conn.close()


def test_delayed_old_document_signals_cannot_close_new_fullscreen_interval(client):
    def send(kind, eid, activation, document):
        return client.post('/api/activity',json={'event_type':kind,'event_id':eid,'activation_id':activation,'document_id':document}).get_json()
    send('fullscreen_enter','enter-old',None,'old-page')
    assert send('window_blur','old-blur','enter-old','old-page')['violations'] == 1
    send('fullscreen_enter','enter-new',None,'new-page')
    for kind in ('window_blur','fullscreen_exit','fullscreen_leave','tab_hidden'):
        stale = send(kind,'stale-'+kind,'enter-old','old-page')
        assert stale['is_fullscreen'] and stale['violations'] == 1
    # A retried old departure is still harmless even with the new interval active.
    retry = send('window_blur','old-blur','enter-old','old-page')
    assert not retry['recorded'] and retry['is_fullscreen']
    assert send('window_blur','new-blur','enter-new','new-page')['blocked']


def test_quiz_review_uses_locked_answers_and_feedback_is_validated_saved_once(client):
    ratings={q['id']:4 for q in FEEDBACK_QUESTIONS}
    signal(client,'fullscreen_enter')
    assert client.post('/api/quiz/feedback',json={'ratings':ratings}).status_code==400
    final=complete_quiz(client)
    assert final['completed'] and len(final['answers'])==10
    assert final['answers'][0]['status']=='incorrect' and final['answers'][1]['status']=='correct'
    assert not any({'key','correct_answer','answer_key','correct_index'} & set(row) for row in final['answers'])
    retry=client.post('/api/quiz/answer',json={'question_id':'R01','answer_index':QUESTIONS[0][3]}).get_json()['quiz']
    assert retry['quiz_score']==9 and retry['answers'][0]['status']=='incorrect'
    for invalid in [{}, {**ratings,'clarity':0}, {**ratings,'clarity':6}, {**ratings,'clarity':True}, {**ratings,'clarity':2.5}]:
        assert client.post('/api/quiz/feedback',json={'ratings':invalid}).status_code==400
    assert client.post('/api/quiz/feedback',json={'ratings':ratings,'note':'x'*2001}).status_code==400
    saved=client.post('/api/quiz/feedback',json={'ratings':ratings,'note':'Great session'}).get_json()['feedback']
    assert saved['submitted'] and saved['note']=='Great session'
    assert client.post('/api/quiz/feedback',json={'ratings':ratings,'note':'Changed'}).get_json()['feedback']==saved
    assert client.get('/api/quiz/status').get_json()['quiz']['feedback']==saved
    assert client.get('/api/admin/feedback').get_json()['responses'][0]['note']=='Great session'
    with app.test_client() as public:
        assert public.get('/api/admin/feedback').status_code==302

def test_quiz_close_records_all_remaining_as_unanswered(client):
    open_quiz(client)
    client.post('/api/quiz/answer',json={'question_id':'R01','answer_index':QUESTIONS[0][3]})
    client.post('/api/admin/quiz-action',json={'action':'close'})
    quiz=client.get('/api/quiz/status').get_json()['quiz']
    assert quiz['completed'] and len(quiz['answers'])==10
    assert sum(a['status']=='unanswered' for a in quiz['answers'])==9


def test_old_entry_and_released_entry_cannot_reactivate_access(client):
    def send(kind, eid, activation, document, started):
        return client.post('/api/activity',json={'event_type':kind,'event_id':eid,'activation_id':activation,'document_id':document,'document_started_at':started}).get_json()
    send('fullscreen_enter','new-entry',None,'new-document',200)
    delayed = send('fullscreen_enter','old-entry',None,'old-document',100)
    assert delayed['is_fullscreen'] and delayed['activation_id'] == 'new-entry'
    assert send('window_blur','new-departure','new-entry','new-document',200)['violations'] == 1
    # A page unload/failed response can release an entry before the delayed POST arrives.
    send('fullscreen_leave','release-cancelled-entry','cancelled-entry','cancelled-document',300)
    cancelled = send('fullscreen_enter','cancelled-entry',None,'cancelled-document',300)
    assert not cancelled['is_fullscreen'] and cancelled['violations'] == 1


def test_offline_departure_reconciles_once_after_logout_login(client):
    entered = client.post('/api/activity',json={'event_type':'fullscreen_enter','event_id':'offline-entry','document_id':'old-doc','document_started_at':100}).get_json()
    assert entered['is_fullscreen']
    client.get('/logout')
    client.post('/register',data={'action':'login','team_lookup':'Policy team'})
    queued = {'event_type':'window_blur','event_id':'offline-blur','activation_id':'offline-entry','document_id':'old-doc','document_started_at':100}
    reconciled = client.post('/api/activity',json=queued).get_json()
    assert reconciled['violations']==1 and not reconciled['is_fullscreen']
    assert client.post('/api/activity',json=queued).get_json()['violations']==1
