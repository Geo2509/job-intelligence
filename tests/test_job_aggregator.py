import json
from dataclasses import replace

from src import job_aggregator
from src.job_collector_registry import get_collector


def job(title, url="", source="duckduckgo", query="data entry Napoli", score=10, **extra):
    data = {
        "title": title,
        "company": extra.pop("company", ""),
        "location": extra.pop("location", ""),
        "url": url,
        "source": source,
        "query": query,
        "remote": extra.pop("remote", False),
        "part_time": extra.pop("part_time", False),
        "category": extra.pop("category", "general"),
        "priority_bucket": extra.pop("priority_bucket", "other"),
        "score": score,
        "found_at": "2026-06-21T00:00:00+00:00",
    }
    data.update(extra)
    return data


def test_aggregate_combines_results(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [job("Duck result", source="duckduckgo")],
        ),
        "indeed": replace(
            get_collector("indeed"),
            callable=lambda **kwargs: [job("Indeed result", source="indeed")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo", "indeed"])

    assert {item["source"] for item in jobs} == {"duckduckgo", "indeed"}
    assert len(jobs) == 2


def test_dedup_by_normalized_url():
    jobs = [
        job("First", "https://example.com/jobs/1?utm_source=x"),
        job("Second", "https://example.com/jobs/1"),
    ]

    deduped = job_aggregator.deduplicate_jobs([job_aggregator.normalize_job(item) for item in jobs])

    assert len(deduped) == 1


def test_fallback_dedup_by_title_company_location():
    jobs = [
        job("Back Office", company="Acme", location="Napoli", url="", query="q1"),
        job("Back Office", company="Acme", location="Napoli", url="", query="q2"),
    ]

    deduped = job_aggregator.deduplicate_jobs([job_aggregator.normalize_job(item) for item in jobs])

    assert len(deduped) == 1


def rotation_job(title, status, match_score=80, **extra):
    item = job(
        title,
        url=extra.pop("url", f"https://example.com/{title.lower().replace(' ', '-')}"),
        match_score=match_score,
        student_score=match_score,
        candidate_score=match_score,
        history_status=status,
    )
    item.update(extra)
    if status in {"SEEN", "RESURFACED"} and not item.get("selection_pool_status") and "sent_count" not in item:
        item["sent_count"] = 1
    if int(item.get("sent_count") or 0) > 0 and not item.get("last_sent"):
        item["last_sent"] = "2026-06-21T00:00:00+00:00"
    return item


def test_candidate_rotation_acceptance_mix():
    jobs = (
        [rotation_job(f"New {i}", "NEW", 100 - i) for i in range(20)]
        + [rotation_job(f"Updated {i}", "UPDATED", 99 - i) for i in range(15)]
        + [
            rotation_job(
                f"Never {i}",
                "SEEN",
                90 - i,
                selection_pool_status="never_sent",
                sent_count=0,
            )
            for i in range(40)
        ]
    )

    selected = job_aggregator.select_email_jobs(jobs, email_target=50, email_min_match=50)

    reasons = [item["selection_reason"] for item in selected]
    assert reasons.count("NEW") == 20
    assert reasons.count("UPDATED") == 15
    assert reasons.count("NEVER_SENT_FILL") == 15
    assert len(selected) == 50


def test_candidate_rotation_never_sent_pool_is_not_empty():
    jobs = [
        rotation_job(f"Never {i}", "SEEN", 90 - i, sent_count=0, last_sent="")
        for i in range(10)
    ]

    selected = job_aggregator.select_email_jobs(jobs, email_target=5, email_min_match=50)

    assert len(selected) == 5
    assert {item["selection_reason"] for item in selected} == {"NEVER_SENT_FILL"}


def test_candidate_rotation_new_before_never_sent():
    selected = job_aggregator.select_email_jobs(
        [
            rotation_job("Never high", "SEEN", 100, selection_pool_status="never_sent"),
            rotation_job("New lower", "NEW", 70),
        ],
        email_target=2,
        email_min_match=50,
    )

    assert [item["selection_reason"] for item in selected] == ["NEW", "NEVER_SENT_FILL"]


def test_candidate_rotation_never_sent_before_resurfaced_and_seen_skipped():
    selected = job_aggregator.select_email_jobs(
        [
            rotation_job("Seen top", "SEEN", 100, sent_count=3),
            rotation_job("Resurfaced", "RESURFACED", 95),
            rotation_job("Never", "SEEN", 75, selection_pool_status="never_sent"),
        ],
        email_target=2,
        email_min_match=50,
    )

    assert [item["selection_reason"] for item in selected] == ["NEVER_SENT_FILL", "RESURFACED"]
    assert "Seen top" not in {item["title"] for item in selected}


def test_candidate_rotation_seen_top_skips_to_lower_never_sent():
    selected = job_aggregator.select_email_jobs(
        [
            rotation_job("Seen top 1", "SEEN", 100, sent_count=2),
            rotation_job("Seen top 2", "SEEN", 95, sent_count=1),
            rotation_job("Never lower", "SEEN", 70, sent_count=0, last_sent=""),
        ],
        email_target=1,
        email_min_match=50,
    )

    assert [item["title"] for item in selected] == ["Never lower"]
    assert selected[0]["selection_reason"] == "NEVER_SENT_FILL"


def test_candidate_rotation_seen_recent_selects_zero_without_fallback():
    jobs = [
        rotation_job(f"Seen {i}", "SEEN", 90 - i, sent_count=1)
        for i in range(3)
    ]

    selected, debug = job_aggregator.select_email_jobs(
        jobs,
        email_target=5,
        email_min_match=50,
        return_debug=True,
    )

    assert selected == []
    assert debug["selected_total"] == 0
    assert debug["rejected_seen"] == 3


def test_candidate_rotation_fallback_can_fill_seen_recent_jobs():
    selected = job_aggregator.select_email_jobs(
        [
            rotation_job("Seen high", "SEEN", 90, sent_count=1),
            rotation_job("Seen lower", "SEEN", 80, sent_count=1),
        ],
        email_target=1,
        email_min_match=50,
        fallback_enabled=True,
    )

    assert [item["selection_reason"] for item in selected] == ["FALLBACK_FILL"]


def test_candidate_rotation_does_not_collapse_large_candidate_pool_to_one():
    jobs = [rotation_job(f"Randstad {i}", "NEW", 90 - (i % 10)) for i in range(80)]

    selected, debug = job_aggregator.select_email_jobs(
        jobs,
        email_target=50,
        email_min_match=50,
        return_debug=True,
    )

    assert len(selected) == 50
    assert debug["candidate_pool_total"] == 80
    assert debug["eligible_new"] == 80
    assert debug["selected_total"] == 50


def test_selection_debug_accounts_for_every_candidate_pool_row():
    jobs = [
        rotation_job("Selected", "NEW", 90),
        rotation_job("Limited", "NEW", 89),
        rotation_job("Low", "NEW", 49),
        rotation_job("Seen", "SEEN", 88, sent_count=1),
        rotation_job("Profile", "NEW", 87, negative_reason="excluded title seniority"),
        rotation_job("Location", "NEW", 86, location_fit="excluded_far"),
        rotation_job("No bucket", "ARCHIVED", 85, sent_count=1),
    ]

    _, debug = job_aggregator.select_email_jobs(
        jobs,
        email_target=1,
        email_min_match=50,
        return_debug=True,
    )

    explained = (
        debug["selected_total"]
        + debug["rejected_low_match"]
        + debug["rejected_profile"]
        + debug["rejected_location"]
        + debug["rejected_seen_recently"]
        + debug["rejected_no_selection_bucket"]
        + debug["rejected_not_selected_due_to_limit"]
    )
    assert debug["candidate_pool_total"] == len(jobs)
    assert explained == len(jobs)


def test_aggregate_selects_from_full_randstad_candidate_pool(monkeypatch, tmp_path):
    collector_jobs = [
        job(
            f"Randstad back office {i}",
            f"https://it.indeed.com/viewjob?jk=randstad{i}",
            source="randstad",
            location="Napoli",
            query="back office Napoli",
        )
        for i in range(50)
    ]
    plugin = replace(
        get_collector("randstad"),
        callable=lambda **kwargs: collector_jobs,
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "randstad" else None)

    jobs, stats, artifacts = job_aggregator.aggregate_jobs(
        ["randstad"],
        email_clean_results=True,
        history_path=tmp_path / "history.json",
        email_target=20,
        return_stats=True,
        return_artifacts=True,
    )

    assert len(artifacts["candidate_pool"]) == 50
    assert len(jobs) == 20
    assert stats["selection_debug"]["candidate_pool_total"] == 50
    assert stats["selection_debug"]["eligible_new"] == 50
    assert stats["selection_debug"]["selected_total"] == 20
    assert {item["source"] for item in jobs} == {"randstad"}


def test_aggregate_fallback_selects_seen_gigroup_candidate_pool(monkeypatch, tmp_path):
    collector_jobs = [
        job(
            f"GiGroup back office {i}",
            f"https://it.indeed.com/viewjob?jk=gigroup{i}",
            source="gigroup",
            location="Napoli",
            query="back office Napoli",
        )
        for i in range(37)
    ]
    history_records = []
    for item in collector_jobs:
        normalized = job_aggregator.normalize_job(
            item,
            include_profile_scores=False,
            search_profile=job_aggregator.LOCAL_STUDENT_PROFILE,
        )
        scored = job_aggregator.add_profile_scores([normalized])[0]
        history_records.append(
            {
                "job_id": job_aggregator.job_id(scored),
                "url": scored["url"],
                "title": scored["title"],
                "source": scored["source"],
                "first_seen": "2026-06-26T00:00:00+00:00",
                "last_seen": "2026-06-26T00:00:00+00:00",
                "last_sent": "2026-06-26T00:00:00+00:00",
                "sent_count": 1,
                "content_hash": job_aggregator.content_hash(scored),
                "match_score": scored["match_score"],
            }
        )
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(history_records), encoding="utf-8")
    plugin = replace(
        get_collector("gigroup"),
        callable=lambda **kwargs: collector_jobs,
    )
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugin if name == "gigroup" else None)

    jobs, stats, artifacts = job_aggregator.aggregate_jobs(
        ["gigroup"],
        email_clean_results=True,
        history_path=history_path,
        email_target=10,
        selection_fallback=True,
        return_stats=True,
        return_artifacts=True,
    )

    assert len(artifacts["candidate_pool"]) == 37
    assert len(jobs) == 10
    assert {item["selection_reason"] for item in jobs} == {"FALLBACK_FILL"}
    assert stats["selection_debug"]["candidate_pool_total"] == 37
    assert stats["selection_debug"]["eligible_fallback"] == 37
    assert stats["selection_debug"]["selected_total"] == 10


def test_candidate_rotation_target_and_min_match_are_enforced():
    selected = job_aggregator.select_email_jobs(
        [
            rotation_job("New high", "NEW", 90),
            rotation_job("New low", "NEW", 49),
            rotation_job("Updated high", "UPDATED", 80),
        ],
        email_target=1,
        email_min_match=50,
    )

    assert len(selected) == 1
    assert selected[0]["title"] == "New high"
    assert all(int(item["match_score"]) >= 50 for item in selected)


def test_remote_detection_ignores_query_without_remote_signal():
    normalized = job_aggregator.normalize_job(
        job(
            "Addetto/addetta ufficio acquisti",
            location="San Marco Evangelista, CE, Campania",
            query="remote back office Napoli",
        )
    )

    assert normalized["remote"] is False
    assert normalized["remote_reason"] == "none"
    assert normalized["location_fit"] == "allowed_local"


def test_negative_remote_pattern_wins():
    normalized = job_aggregator.normalize_job(
        job(
            "Customer Service smart working in sede",
            location="Napoli",
            query="remote",
        )
    )

    assert normalized["remote"] is False
    assert normalized["remote_reason"] == "negative: in sede"
    assert normalized["location_fit"] == "allowed_local"


def test_remote_detection_requires_explicit_job_signal():
    normalized = job_aggregator.normalize_job(
        job(
            "Customer Service 100% SMARTWORKING",
            location="Italia",
            query="customer service Napoli",
        )
    )

    assert normalized["remote"] is True
    assert normalized["remote_reason"] == "title: smartworking"
    assert normalized["location_fit"] == "remote"


def test_job_classification_v2_categories_and_score_guards():
    examples = {
        "Talent Acquisition Consultant": ("hr_recruiting", 75),
        "GRAFICO": ("design", 75),
        "Contabile con SAP": ("accounting", 100),
        "Impiegato/a spedizioni aeree": ("logistics", 100),
        "Facilities junior officer": ("facilities", 100),
        "Stage addetto amministrativo": ("administration", 100),
        "Addetto/addetta ufficio acquisti": ("administration", 100),
        "Data Entry Excel Napoli": ("data_entry", 100),
    }

    for title, (category, max_match) in examples.items():
        normalized = job_aggregator.normalize_job(job(title, location="Napoli"))

        assert normalized["category"] == category
        assert normalized["match_score"] <= max_match


def test_gigroup_local_examples_are_not_remote():
    for title in [
        "Addetto/addetta ufficio acquisti",
        "Impiegato/a spedizioni aeree",
    ]:
        normalized = job_aggregator.normalize_job(
            job(title, source="gigroup", location="San Marco Evangelista, CE, Campania")
        )

        assert normalized["remote"] is False
        assert normalized["remote_reason"] == "none"


def test_sorting_prioritizes_match_score_then_student_score_then_candidate_score_then_score():
    remote = job(
        "Remote data entry",
        remote=True,
        priority_bucket="remote_data",
        score=100,
        query="remote data entry",
        student_score=80,
        candidate_score=100,
        match_score=91,
        location_fit="remote",
    )
    local_part_time = job(
        "Back office part-time Napoli",
        part_time=True,
        priority_bucket="campania_part_time",
        score=10,
        query="back office Napoli part time",
        student_score=95,
        candidate_score=70,
        match_score=81,
        location_fit="allowed_local",
    )

    sorted_jobs = job_aggregator.sort_jobs([remote, local_part_time])

    assert sorted_jobs[0]["title"] == "Remote data entry"
    assert sorted_jobs[1]["title"] == "Back office part-time Napoli"


def test_sorting_uses_student_score_as_match_tiebreaker():
    lower_student = job("Lower student", score=100, student_score=70, match_score=90)
    higher_student = job("Higher student", score=10, student_score=80, match_score=90)

    sorted_jobs = job_aggregator.sort_jobs([lower_student, higher_student])

    assert [item["title"] for item in sorted_jobs] == ["Higher student", "Lower student"]


def test_sorting_uses_candidate_score_as_student_tiebreaker():
    lower_candidate = job(
        "Lower candidate",
        score=100,
        match_score=90,
        student_score=80,
        candidate_score=70,
    )
    higher_candidate = job(
        "Higher candidate",
        score=10,
        match_score=90,
        student_score=80,
        candidate_score=90,
    )

    sorted_jobs = job_aggregator.sort_jobs([lower_candidate, higher_candidate])

    assert [item["title"] for item in sorted_jobs] == ["Higher candidate", "Lower candidate"]


def test_drop_unknown_locations_removes_unknown_non_remote():
    jobs = [
        job("Unknown local-ish", location_fit="unknown", remote=False),
        job("Allowed Napoli", location_fit="allowed_local", remote=False),
    ]

    filtered = job_aggregator.drop_unknown_location_jobs(jobs)

    assert [item["title"] for item in filtered] == ["Allowed Napoli"]


def test_drop_unknown_locations_keeps_unknown_remote():
    jobs = [
        job("Unknown remote", location_fit="unknown", remote=True),
        job("Unknown non-remote", location_fit="unknown", remote=False),
    ]

    filtered = job_aggregator.drop_unknown_location_jobs(jobs)

    assert [item["title"] for item in filtered] == ["Unknown remote"]


def test_drop_unknown_locations_keeps_allowed_local():
    jobs = [
        job("Allowed Napoli", location_fit="allowed_local", remote=False),
        job("Remote fit", location_fit="remote", remote=True),
    ]

    filtered = job_aggregator.drop_unknown_location_jobs(jobs)

    assert [item["title"] for item in filtered] == ["Allowed Napoli", "Remote fit"]


def test_drop_far_locations_removes_excluded_far():
    jobs = [
        job("Excluded far", location_fit="excluded_far", remote=False),
        job("Allowed Napoli", location_fit="allowed_local", remote=False),
    ]

    filtered = job_aggregator.drop_far_location_jobs(jobs)

    assert [item["title"] for item in filtered] == ["Allowed Napoli"]


def test_one_collector_failure_does_not_break_aggregator(monkeypatch, capsys):
    def broken_collector(**kwargs):
        raise RuntimeError("boom")

    plugins = {
        "duckduckgo": replace(get_collector("duckduckgo"), callable=broken_collector),
        "indeed": replace(
            get_collector("indeed"),
            callable=lambda **kwargs: [job("Indeed result", source="indeed")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo", "indeed"])

    assert len(jobs) == 1
    assert jobs[0]["source"] == "indeed"
    assert "Collector failed: duckduckgo" in capsys.readouterr().out


def test_unknown_collector_does_not_break_aggregator(capsys):
    jobs = job_aggregator.aggregate_jobs(["unknown"])

    assert jobs == []
    assert "Unknown collector skipped: unknown" in capsys.readouterr().out


def test_without_collectors_uses_enabled_registry_collectors(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [job("Duck result", source="duckduckgo")],
        ),
        "indeed": replace(
            get_collector("indeed"),
            callable=lambda **kwargs: [job("Indeed result", source="indeed")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "enabled_collectors", lambda: ["duckduckgo", "indeed"])
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(None)

    assert {item["source"] for item in jobs} == {"duckduckgo", "indeed"}


def test_export_json_csv_xlsx(tmp_path):
    output_path = tmp_path / "v2_jobs.json"
    jobs = [
        job_aggregator.normalize_job(
            job(
                "Data Entry Napoli",
                "https://example.com/jobs/1",
                company="Acme",
                location="Napoli",
                part_time=True,
                query="data entry Napoli part time",
            )
        )
    ]

    job_aggregator.export_jobs(jobs, output_path)

    csv_header = output_path.with_suffix(".csv").read_text(encoding="utf-8").splitlines()[0]

    assert output_path.exists()
    assert output_path.with_suffix(".csv").exists()
    assert output_path.with_suffix(".xlsx").exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["title"] == "Data Entry Napoli"
    assert "student_score" in csv_header
    assert "candidate_score" in csv_header
    assert "match_score" in csv_header
    assert "location_fit" in csv_header


def test_aggregate_with_clean_results_excludes_search_page(monkeypatch, capsys):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Data Entry Napoli", "https://it.indeed.com/viewjob?jk=1"),
                job("Search results", "https://example.com/search/data-entry"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=True)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Entry Napoli"
    assert jobs[0]["result_type"] == "job"
    output = capsys.readouterr().out
    assert "Total before cleaning: 2" in output
    assert "Removed search_page: 1" in output
    assert "Total after cleaning: 1" in output


def test_export_includes_result_type_when_cleaned(tmp_path):
    output_path = tmp_path / "v2_jobs.json"
    jobs = [
        {
            **job_aggregator.normalize_job(job("Data Entry Napoli", "https://it.indeed.com/viewjob?jk=1")),
            "result_type": "job",
            "url_result_type": "real_job",
        }
    ]

    job_aggregator.export_jobs(jobs, output_path)

    exported_json = json.loads(output_path.read_text(encoding="utf-8"))
    csv_header = output_path.with_suffix(".csv").read_text(encoding="utf-8").splitlines()[0]

    assert exported_json[0]["result_type"] == "job"
    assert exported_json[0]["url_result_type"] == "real_job"
    assert "result_type" in csv_header
    assert "url_result_type" in csv_header


def test_clean_results_scores_only_surviving_jobs(monkeypatch):
    calls = []

    def fake_student_score(job):
        calls.append(job["title"])
        return 77

    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Kept job", "https://it.indeed.com/viewjob?jk=1"),
                job("Removed search", "https://www.jobbydoo.it/lavoro-data-entry"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))
    monkeypatch.setattr(job_aggregator, "evaluate_student_score", fake_student_score)

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=True)

    assert [item["title"] for item in jobs] == ["Kept job"]
    assert calls == ["Kept job"]
    assert jobs[0]["student_score"] == 77
    assert "candidate_score" in jobs[0]
    assert "match_score" in jobs[0]


def test_aggregate_soft_clean_keeps_trusted_pages(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Subito offerte lavoro", "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/"),
                job("Removed search", "https://www.jobbydoo.it/lavoro-data-entry"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=True)

    assert [item["title"] for item in jobs] == ["Subito offerte lavoro"]
    assert jobs[0]["result_type"] == "search_page"
    assert "student_score" in jobs[0]
    assert "candidate_score" in jobs[0]
    assert "match_score" in jobs[0]


def test_aggregate_email_clean_removes_soft_search_pages(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Subito offerte lavoro", "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/"),
                job("Jooble job", "https://it.jooble.org/jdp/123456"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], email_clean_results=True)

    assert [item["title"] for item in jobs] == ["Jooble job"]
    assert jobs[0]["url_result_type"] == "real_job"
    assert "student_score" in jobs[0]
    assert "candidate_score" in jobs[0]
    assert "match_score" in jobs[0]


def test_aggregate_email_clean_keeps_adecco_real_jobs(monkeypatch):
    plugins = {
        "adecco": replace(
            get_collector("adecco"),
            callable=lambda **kwargs: [
                job(
                    "Adecco back office",
                    "https://www.adecco.it/lavoro/back-office-part-time_napoli_123456/",
                    source="adecco",
                ),
                job(
                    "Adecco search",
                    "https://www.adecco.it/lavoro/?k=napoli",
                    source="adecco",
                ),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["adecco"], email_clean_results=True)

    assert [item["title"] for item in jobs] == ["Adecco back office"]
    assert jobs[0]["source"] == "adecco"
    assert jobs[0]["url_result_type"] == "real_job"
    assert "student_score" in jobs[0]
    assert "candidate_score" in jobs[0]
    assert "match_score" in jobs[0]


def test_aggregate_drop_far_locations_removes_excluded_far(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job(
                    "Back office Napoli",
                    "https://it.indeed.com/viewjob?jk=napoli",
                    location="Napoli",
                ),
                job(
                    "Back office Milano",
                    "https://it.indeed.com/viewjob?jk=milano",
                    location="Milano",
                ),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        email_clean_results=True,
        drop_far_locations=True,
    )

    assert [item["title"] for item in jobs] == ["Back office Napoli"]
    assert jobs[0]["location_fit"] == "allowed_local"


def test_aggregate_drop_far_and_unknown_locations_keeps_only_allowed_local_and_remote(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job(
                    "Back office Napoli",
                    "https://it.indeed.com/viewjob?jk=napoli",
                    location="Napoli",
                ),
                job(
                    "Remote data",
                    "https://it.indeed.com/viewjob?jk=remote",
                    location="Italia",
                    remote=True,
                ),
                job(
                    "Back office Zola Predosa",
                    "https://it.indeed.com/viewjob?jk=zola",
                    location="Zola Predosa",
                ),
                job(
                    "Back office Milano",
                    "https://it.indeed.com/viewjob?jk=milano",
                    location="Milano",
                ),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        email_clean_results=True,
        drop_far_locations=True,
        drop_unknown_locations=True,
    )

    assert {item["title"] for item in jobs} == {"Back office Napoli", "Remote data"}
    assert {item["location_fit"] for item in jobs} == {"allowed_local", "remote"}


def test_aggregate_strict_clean_keeps_only_real_jobs(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [
                job("Indeed job", "https://it.indeed.com/viewjob?jk=1"),
                job("Subito offerte lavoro", "https://www.subito.it/annunci-campania/vendita/offerte-lavoro/napoli/"),
            ],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(
        ["duckduckgo"],
        clean_results=True,
        strict_job_detail_only=True,
    )

    assert [item["title"] for item in jobs] == ["Indeed job"]
    assert jobs[0]["url_result_type"] == "real_job"


def test_without_clean_results_keeps_old_behavior(monkeypatch):
    plugins = {
        "duckduckgo": replace(
            get_collector("duckduckgo"),
            callable=lambda **kwargs: [job("Search results", "https://example.com/search/data-entry")],
        ),
    }
    monkeypatch.setattr(job_aggregator, "get_collector", lambda name: plugins.get(name))

    jobs = job_aggregator.aggregate_jobs(["duckduckgo"], clean_results=False)

    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://example.com/search/data-entry"
    assert "result_type" not in jobs[0]


def test_balanced_top_keeps_remote_data_when_local_scores_are_higher():
    jobs = [
        job("Local part time high", "https://example.com/local-1", score=900),
        job("Local part time higher", "https://example.com/local-2", score=800),
        job(
            "Remote data analyst",
            "https://example.com/remote-1",
            remote=True,
            priority_bucket="remote_data",
            score=10,
        ),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=2, min_remote=1)

    assert {item["title"] for item in balanced} == {"Remote data analyst", "Local part time high"}


def test_balanced_top_does_not_exceed_top():
    jobs = [
        job(
            f"Remote data {index}",
            f"https://example.com/remote-{index}",
            remote=True,
            priority_bucket="remote_data",
            score=index,
        )
        for index in range(5)
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=20)

    assert len(balanced) == 3


def test_balanced_top_does_not_add_duplicates():
    jobs = [
        job(
            "Remote data duplicate",
            "https://example.com/same?utm_source=x",
            remote=True,
            priority_bucket="remote_data",
            score=100,
        ),
        job(
            "Remote data duplicate copy",
            "https://example.com/same",
            remote=True,
            priority_bucket="remote_data",
            score=90,
        ),
        job("Fallback", "https://example.com/fallback", score=80),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=20)

    assert len(balanced) == 2
    assert [item["url"] for item in balanced] == [
        "https://example.com/same?utm_source=x",
        "https://example.com/fallback",
    ]


def test_balanced_top_takes_available_remote_when_less_than_min_remote():
    jobs = [
        job(
            "Only remote",
            "https://example.com/remote",
            remote=True,
            priority_bucket="remote_data",
            score=30,
        ),
        job("Local one", "https://example.com/local-1", score=90),
        job("Local two", "https://example.com/local-2", score=80),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=20)

    assert {item["title"] for item in balanced} == {"Only remote", "Local one", "Local two"}


def test_balanced_top_fallback_fills_remaining_by_score():
    jobs = [
        job(
            "Remote low",
            "https://example.com/remote",
            remote=True,
            priority_bucket="remote_data",
            score=10,
        ),
        job("Fallback high", "https://example.com/high", score=100),
        job("Fallback medium", "https://example.com/medium", score=70),
        job("Fallback low", "https://example.com/low", score=20),
    ]

    balanced = job_aggregator.balanced_top(jobs, top=3, min_remote=1)

    assert {item["title"] for item in balanced} == {
        "Remote low",
        "Fallback high",
        "Fallback medium",
    }
