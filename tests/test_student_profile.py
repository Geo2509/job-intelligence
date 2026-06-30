from src.student_profile import (
    PREFERRED_TITLE_BONUS,
    detect_location_fit,
    evaluate_student_score,
    load_student_profile,
)


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


def test_napoli_is_allowed_local():
    fit = detect_location_fit({"title": "Back office", "location": "Napoli"}, load_student_profile())

    assert fit == "allowed_local"


def test_pozzuoli_is_allowed_local():
    fit = detect_location_fit({"title": "Reception", "location": "Pozzuoli"}, load_student_profile())

    assert fit == "allowed_local"


def test_bacoli_is_allowed_local():
    fit = detect_location_fit({"title": "Pulizie", "location": "Bacoli"}, load_student_profile())

    assert fit == "allowed_local"


def test_remote_ai_trainer_is_remote_location_fit():
    fit = detect_location_fit({
        "title": "Remote AI Trainer",
        "location": "Italia",
        "remote": True,
    }, load_student_profile())

    assert fit == "remote"


def test_milano_is_excluded_far():
    fit = detect_location_fit({"title": "Data Entry Milano", "location": "Milano"}, load_student_profile())

    assert fit == "excluded_far"


def test_bologna_is_excluded_far():
    fit = detect_location_fit({"title": "Back office", "location": "Bologna"}, load_student_profile())

    assert fit == "excluded_far"


def test_roma_non_remote_is_excluded_far():
    fit = detect_location_fit({"title": "Receptionist Roma", "location": "Roma"}, load_student_profile())

    assert fit == "excluded_far"


def test_excluded_far_student_score_is_capped():
    score = evaluate_student_score({
        "title": "Back office part time Milano",
        "location": "Milano",
        "part_time": True,
        "category": "data_office",
    })

    assert score <= 40


def test_unknown_location_student_score_is_capped():
    score = evaluate_student_score({
        "title": "Back office part time",
        "location": "Caserta",
        "part_time": True,
        "category": "data_office",
    })

    assert score <= 70


def test_url_lonate_pozzolo_is_excluded_far():
    fit = detect_location_fit({
        "title": "Magazziniere",
        "url": "https://www.randstad.it/offerte-lavoro/magazziniere_lonate-pozzolo_123/",
    }, load_student_profile())

    assert fit == "excluded_far"


def test_url_san_giuliano_milanese_is_excluded_far():
    fit = detect_location_fit({
        "title": "Back office",
        "url": "https://www.randstad.it/offerte-lavoro/back-office_san-giuliano-milanese_123/",
    }, load_student_profile())

    assert fit == "excluded_far"


def test_url_castello_d_argile_is_excluded_far():
    fit = detect_location_fit({
        "title": "Impiegato",
        "url": "https://www.randstad.it/offerte-lavoro/impiegato_castello-d-argile_123/",
    }, load_student_profile())

    assert fit == "excluded_far"


def test_url_pozzuolo_martesana_is_excluded_far():
    fit = detect_location_fit({
        "title": "Receptionist",
        "url": "https://www.randstad.it/offerte-lavoro/receptionist_pozzuolo-martesana_123/",
    }, load_student_profile())

    assert fit == "excluded_far"


def test_url_livorno_is_excluded_far():
    fit = detect_location_fit({
        "title": "Impiegato data entry",
        "url": "https://www.randstad.it/offerte-lavoro/impiegato-data-entry_livorno_123/",
    }, load_student_profile())

    assert fit == "excluded_far"


def test_url_napoli_is_allowed_local():
    fit = detect_location_fit({
        "title": "Back office",
        "url": "https://www.randstad.it/offerte-lavoro/back-office_napoli_123/",
    }, load_student_profile())

    assert fit == "allowed_local"


def test_url_bacoli_is_allowed_local():
    fit = detect_location_fit({
        "title": "Pulizie",
        "url": "https://www.randstad.it/offerte-lavoro/pulizie_bacoli_123/",
    }, load_student_profile())

    assert fit == "allowed_local"


def test_unwanted_titles_are_rejected_with_diagnostics():
    titles = [
        "Operatore telefonico Napoli",
        "Call Center Part Time",
        "Teleseller",
        "Telemarketing",
        "Vendita telefonica",
        "Recupero crediti",
    ]

    for title in titles:
        job = {"title": title, "location": "Napoli", "part_time": True}

        assert evaluate_student_score(job) == 0
        assert job["profile_match"] is False
        assert job["selection_rejection_reason"] == "unwanted_title"
        assert job["profile_reason"] == "unwanted_title"
        assert job["candidate_score"] == 0
        assert job["matched_keyword"]


def test_unwanted_title_matching_normalizes_punctuation_and_whitespace():
    job = {"title": "Call-Center   Part Time", "location": "Napoli", "part_time": True}

    assert evaluate_student_score(job) == 0
    assert job["matched_keyword"] == "call center"


def test_preferred_titles_get_small_bonus_and_diagnostics():
    preferred_titles = [
        "Impiegato amministrativo",
        "Back Office",
        "Receptionist",
        "Data Entry",
        "Magazziniere",
    ]

    for title in preferred_titles:
        preferred_job = {"title": title, "location": "Napoli"}
        generic_job = {"title": "Impiegato generico", "location": "Napoli"}

        preferred_score = evaluate_student_score(preferred_job)
        generic_score = evaluate_student_score(generic_job)

        assert preferred_score >= generic_score + PREFERRED_TITLE_BONUS
        assert preferred_job["profile_match"] is True
        assert preferred_job["profile_reason"] == "preferred_title"
        assert preferred_job["matched_keyword"]
