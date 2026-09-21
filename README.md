# Job Intelligence

Python data-processing pipeline for collecting, normalizing, validating and ranking job-listing data from multiple public sources.

## What it demonstrates

- multi-source web-data collection;
- normalization of heterogeneous records;
- URL cleaning and classification;
- duplicate detection;
- rule-based filtering and scoring;
- location and candidate-fit validation;
- structured JSON, CSV and XLSX exports;
- processing history and collector-quality diagnostics.

## Pipeline

```
Collectors -> Normalize -> Clean -> Deduplicate -> Validate
           -> Score -> Candidate Pool -> JSON / CSV / XLSX
```

Collectors are designed to fail independently so that one unavailable source does not stop the complete processing run. Search or category pages can be separated from likely job-detail pages before final export.

## Main tools

Python, Pandas, Requests, DDGS, PyYAML and structured CSV/JSON/XLSX processing.

## Data quality features

The project includes rule-based result cleaning, URL normalization, duplicate handling, location checks, candidate matching and collector diagnostics. Intermediate and final records retain status fields that help explain why a result was accepted, excluded or ranked differently.

## Scope

The current configuration focuses on job discovery in Italy, particularly Campania, together with selected remote data/AI roles. Runtime exports and local secrets are excluded from Git.

This is a personal automation and data-processing project, not a commercial recruitment service.
