from src.student_profile import evaluate_student_score, load_student_profile


def test_load_student_profile():
    profile = load_student_profile()

    assert profile["profile"]["home_city"] == "Monte di Procida"
    assert "Napoli" in profile["profile"]["preferred_locations"]


def test_remote_gets_high_student_score():
    score = evaluate_student_score({
        "title": "Remote AI Trainer",
        "location": "Italia",
        "remote": True,
        "category": "ai_data",
    })

    assert score >= 80


def test_part_time_napoli_scores_higher_than_full_time_caserta():
    part_time_napoli = evaluate_student_score({
        "title": "Back Office Napoli part time",
        "location": "Napoli",
        "part_time": True,
        "category": "data_office",
    })
    full_time_caserta = evaluate_student_score({
        "title": "Impiegato full time",
        "location": "Caserta",
        "part_time": False,
        "category": "administration",
    })

    assert part_time_napoli > full_time_caserta


def test_night_shift_gets_penalty():
    score = evaluate_student_score({
        "title": "Night Shift Hotel",
        "location": "Napoli",
        "category": "hotel",
    })

    assert score < 50


def test_pozzuoli_gets_bonus():
    pozzuoli = evaluate_student_score({
        "title": "Reception part time",
        "location": "Pozzuoli",
        "category": "reception",
    })
    caserta = evaluate_student_score({
        "title": "Reception part time",
        "location": "Caserta",
        "category": "reception",
    })

    assert pozzuoli > caserta


def test_monte_di_procida_gets_bonus():
    monte = evaluate_student_score({
        "title": "Pulizie mattina",
        "location": "Monte di Procida",
        "category": "cleaning",
    })
    caserta = evaluate_student_score({
        "title": "Pulizie mattina",
        "location": "Caserta",
        "category": "cleaning",
    })

    assert monte > caserta
