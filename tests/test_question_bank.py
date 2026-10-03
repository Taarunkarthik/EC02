"""Validate the beginner C/Python bank and the corrected programs' output."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BANK = json.loads((ROOT / "data/questions.json").read_text())
REPAIRS = {'Q01': ['range(len(numbers) - 1)', 'range(len(numbers))'],
 'Q02': ['int count = 10\n', 'int count = 10;\n'],
 'Q03': ['print(message', 'print(message)'],
 'Q04': ['if num > 0\n', 'if num > 0:\n'],
 'Q05': ['%.0f', '%.1f'],
 'Q06': ['if (number = 0)', 'if (number == 0)'],
 'Q07': ['    total = number', '    total += number'],
 'Q08': ['i < 4', 'i < 5'],
 'Q09': ['average = total / count', 'average = (double) total / count'],
 'Q10': ['return user_val * 2', 'return int(user_val) * 2'],
 'Q11': ['"Age: %d\\n", year', '"Age: %d\\n", age'],
 'Q12': ['numbers[3]', 'numbers[2]'],
 'Q13': ['item + multiplier', 'item * multiplier'],
 'Q14': ['printf("SUCCESS");', 'printf("SUCCESS"); break;'],
 'Q15': ['print(name.upper)', 'print(name.upper())'],
 'Q16': ['scores.student = val', 'scores[student] = val'],
 'Q17': ['    add(3, 4);', '    result = add(3, 4);'],
 'Q18': ['        return answer', '    return answer'],
 'Q19': ['    number * number', '    return number * number'],
 'Q20': ['word[1]', 'word[0]'],
 'Q21': ['score > 50', 'score >= 50'],
 'Q22': ['        pass', '        return 0'],
 'Q23': ['%.3s', '%s'],
 'Q24': ['word[1:3]', 'word[0:3]'],
 'Q25': ['backup = original\n', 'backup = original.copy()\n'],
 'Q26': ['2 + 3 * 4', '(2 + 3) * 4'],
 'Q27': ['number % 2 == 1', 'number % 2 == 0'],
 'Q28': ['first + second', 'int(first) + int(second)'],
 'Q29': ['i++);', 'i++)'],
 'Q30': ['number >= 1 || number <= 10', 'number >= 1 && number <= 10']}


def test_bank_languages_ids_and_descriptive_keywords():
    assert [q["id"] for q in BANK] == [f"Q{i:02d}" for i in range(1, 31)]
    assert {q["language"] for q in BANK} == {"C", "Python"}
    for question in BANK:
        assert len(set(question["cause_keywords"])) >= 2
        assert len(set(question["correction_keywords"])) >= 2


@pytest.mark.parametrize("question", BANK, ids=lambda q: q["id"])
def test_corrected_program_matches_answer_key(question, tmp_path):
    old, new = REPAIRS[question["id"]]
    assert question["code"].count(old) == 1, "Repair must identify a single location"
    corrected = question["code"].replace(old, new)
    if question["language"] == "Python":
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(compile(corrected, question["id"], "exec"), {})
        actual = output.getvalue()
    else:
        compiler = shutil.which("cc")
        if not compiler:
            pytest.skip("C compiler unavailable")
        source = tmp_path / "question.c"
        program = tmp_path / "question"
        source.write_text(corrected)
        subprocess.run([compiler, "-std=c11", "-pedantic-errors", str(source), "-o", str(program)], check=True, capture_output=True, timeout=10)
        actual = subprocess.run([str(program)], check=True, capture_output=True, text=True, timeout=2).stdout
    assert actual.strip() == question["expected_output"].strip()


@pytest.mark.parametrize("question", BANK, ids=lambda q: q["id"])
def test_reference_descriptions_meet_keyword_rule(question):
    from scoring import evaluate_submission
    answer = {field: question[field] for field in ("error_type", "expected_output", "cause", "correction")}
    answer["error_location"] = question["bug_location"]
    evaluation = evaluate_submission(question, answer)
    assert evaluation["raw_score"] == question["points"]
    assert evaluation["keyword_matches"]["cause"] >= 2
    assert evaluation["keyword_matches"]["correction"] >= 2


def test_bank_migration_preserves_competition_data_and_organizer_edits():
    from database import init_db, register_team, get_db_connection
    from scoring import process_submission
    init_db(force_reset=True)
    team_id, error = register_team("Migration preservation", "One", "Two")
    assert error is None
    q = BANK[0]
    answer = {field: q[field] for field in ("error_type", "expected_output", "cause", "correction")}
    answer["error_location"] = q["bug_location"]
    scored, error = process_submission(team_id, q["id"], answer)
    assert error is None
    conn = get_db_connection()
    conn.execute("UPDATE questions SET language='Java', code='old code', is_active=0 WHERE id='Q03'")
    conn.execute("DELETE FROM data_migrations WHERE name='c-python-beginner-bank-v1'")
    conn.commit()
    conn.close()
    init_db()
    conn = get_db_connection()
    replacement = dict(conn.execute("SELECT * FROM questions WHERE id='Q03'").fetchone())
    assert replacement["language"] in ("C", "Python") and replacement["code"] == BANK[2]["code"]
    assert replacement["is_active"] == 0 and len(json.loads(replacement["cause_keywords"])) >= 2
    assert conn.execute("SELECT COUNT(*) FROM question_assignments WHERE team_id=?", (team_id,)).fetchone()[0] == 30
    assert conn.execute("SELECT COUNT(*) FROM submissions WHERE team_id=?", (team_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT score FROM scores WHERE team_id=?", (team_id,)).fetchone()[0] == scored["total_score"]
    conn.execute("UPDATE questions SET title='Organizer title' WHERE id='Q03'")
    conn.commit()
    conn.close()
    init_db()
    conn = get_db_connection()
    assert conn.execute("SELECT title FROM questions WHERE id='Q03'").fetchone()[0] == "Organizer title"
    conn.close()
