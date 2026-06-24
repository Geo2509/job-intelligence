from src.candidate_profile import calculate_match_score, evaluate_candidate_score, load_candidate_profile


def score(title, **extra):
    job = {"title": title}
    job.update(extra)
    return evaluate_candidate_score(job)


def test_load_candidate_profile():
    profile = load_candidate_profile()

    assert profile["candidate"]["languages"]["english"] == "B1"
    assert "python" in profile["candidate"]["skills"]


def test_data_entry_scores_high():
    assert score("Data Entry Excel Napoli") >= 90


def test_back_office_scores_high():
    assert score("Back Office amministrativo") >= 90


def test_hotel_scores_positive():
    assert score("Reception Hotel Napoli") >= 75


def test_reception_scores_positive():
    assert score("Receptionist front office") >= 65


def test_python_scores_positive():
    assert score("Python data processing") >= 65


def test_excel_scores_positive():
    assert score("Impiegato Excel") >= 70


def test_laurea_obbligatoria_penalty():
    base = score("Receptionist")
    penalized = score("Receptionist laurea obbligatoria")

    assert penalized == base - 25


def test_night_shift_penalty():
    base = score("Hotel reception")
    penalized = score("Hotel reception night shift")

    assert penalized == base - 20


def test_part_time_bonus():
    base = score("Customer Service")
    part_time = score("Customer Service part time", part_time=True)

    assert part_time > base


def test_english_b1_requirement_is_not_penalized():
    base = score("Back Office")
    english = score("Back Office English B1 required")

    assert english == base


def test_only_c1_english_is_penalized():
    base = score("Back Office")
    c1 = score("Back Office English C1 required")

    assert c1 == base - 20


def test_italian_b2_penalty():
    base = score("Receptionist")
    italian_b2 = score("Receptionist italiano B2")

    assert italian_b2 == base - 10


def test_italian_c1_penalty():
    base = score("Receptionist")
    italian_c1 = score("Receptionist italiano C1")

    assert italian_c1 == base - 20


def test_match_score_formula():
    assert calculate_match_score(90, 100) == 96
