# Job Intelligence

Проект `job-intelligence` предназначен для сбора вакансий из разных онлайн-источников, фильтрации релевантных объявлений и оценки их качества с помощью кастомной системы скоринга.

## Описание

Проект состоит из набора скриптов-коллекторов, которые извлекают вакансии из API и веб-ресурсов, а также вспомогательных скриптов для фильтрации и ранжирования.

Цели:
- собрать вакансии из нескольких источников;
- отфильтровать релевантные предложения по ключевым словам;
- назначить каждой вакансии баллы на основе позитивных и негативных сигнатур;
- экспортировать итоговую таблицу в CSV и XLSX.

## Job Intelligence V2

Job Intelligence V2 начинается с каталога источников в `configs/job_sources.yaml`. Цель V2 — расширить поиск на part-time вакансии рядом с Napoli, Pozzuoli, Bacoli и Monte di Procida, а также на remote data/AI роли по Италии.

Группы источников:
- `aggregators` — крупные job boards и агрегаторы вроде Indeed, LinkedIn Jobs, InfoJobs, Jooble, Jobrapido, Trovit и Bakeca Lavoro;
- `classifieds` — classified-площадки для локальных объявлений, начиная с Subito Lavoro;
- `agencies` — кадровые агентства Италии, включая Randstad, Adecco, Manpower, Gi Group, Openjobmetis, Synergie, Humangest, During, Lavorint, Tempi Moderni и Generazione Vincente;
- `remote_data_ai` — remote/data/AI источники вроде Remotive, Arbeitnow, RemoteOK, We Work Remotely, Appen, TELUS Digital, OneForma, DataAnnotation, Outlier, TransPerfect DataForce и RWS TrainAI;
- `public_employment` — зарезервированная группа для публичных employment-сервисов;
- `duckduckgo_discovery_queries` — стартовые discovery-запросы для поиска локальных part-time и remote data/AI возможностей.

Это первый этап V2: только source catalog, без реализации парсеров и без подключения новых источников к pipeline.

### Search Coverage Expansion

`duckduckgo_discovery_queries` в `configs/job_sources.yaml` расширен примерно до 100+ запросов и сгруппирован комментариями по категориям. Фокус поиска: Campania, Napoli, Pozzuoli, Bacoli, Monte di Procida, Quarto, Fuorigrotta и Campi Flegrei, с приоритетом на `part time`, `tempo parziale`, weekend, turni, mattina и sera.

Категории поиска:
- Data / Office — data entry, inserimento dati, back office, segreteria, front office, Excel и Google Sheets;
- Hotel — reception, receptionist, housekeeping, camere и portiere notturno;
- Ristorante / Bar — cameriere, barista, aiuto cucina, lavapiatti, pizzeria, banconista и gastronomia;
- Pulizie — pulizie domestiche/uffici/hotel, imprese di pulizie и sanificazione;
- Manutenzione — manutentore, tuttofare, tecnico e operaio manutenzione;
- Magazzino — magazziniere, scaffalista, picking, carico/scarico e logistica;
- GDO — Lidl, Eurospin, Conad, MD, Deco, Esselunga, Carrefour, cassiere e addetto vendita;
- Turismo — villaggi turistici, resort, stabilimenti balneari, porto turistico e marina;
- Weekend / Turni — weekend, sabato/domenica, mattina, sera e turni;
- Remote — customer service, virtual assistant, AI trainer/annotator, transcription, data labeling, moderation e content reviewer.

### Job Site Profiler

`src/job_site_profiler.py` строит технические профили источников из `configs/job_sources.yaml` и сохраняет результат в `configs/job_site_profiles.yaml`. Profiler проверяет доступность `base_url`, HTTP status, наличие `robots.txt`, `sitemap.xml`, RSS/feed, а также job-related keywords на главной странице.

Команда запуска:

```bash
python -m src.job_site_profiler --config configs/job_sources.yaml --output configs/job_site_profiles.yaml --limit 10
```

Dry-run режим не пишет output-файл и выводит только summary:

```bash
python -m src.job_site_profiler --config configs/job_sources.yaml --output configs/job_site_profiles.yaml --limit 10 --dry-run
```

Profiler не собирает вакансии и не парсит объявления. Он только оценивает источники и предлагает `recommended_strategy`: `direct`, `sitemap`, `rss`, `duckduckgo` или `manual`.

### DuckDuckGo Job Discovery Collector

`src/collectors/duckduckgo_jobs.py` использует `duckduckgo_discovery_queries` из `configs/job_sources.yaml`, выполняет поиск через пакет `ddgs` и сохраняет найденные результаты в единый JSON-формат. Collector нормализует URL, удаляет tracking-параметры, исключает нежелательные объявления, выставляет discovery score и сортирует результаты по `score` по убыванию.

Команда запуска:

```bash
python -m src.collectors.duckduckgo_jobs --config configs/job_sources.yaml --output output/duckduckgo_jobs.json --limit 3
```

`--limit` задаёт максимум поисковых результатов на один query. Если пакет `ddgs` не установлен, collector не падает: он выводит `ddgs package not installed` и возвращает пустой список.

Это discovery слой, а не финальный парсер вакансий. Он помогает находить потенциальные страницы и объявления для дальнейшей проверки, нормализации и скоринга.

### Indeed Jobs Collector

`src/collectors/indeed_jobs.py` — V2 collector для Indeed Italia по Campania part-time/data/remote направлениям. Direct mode формирует публичные Indeed search URL и делает обычные HTTP-запросы с таймаутом, без Selenium, без обхода CAPTCHA и без агрессивного scraping.

Direct mode может быть ограничен сайтом: если Indeed возвращает блокировку, CAPTCHA, ошибку или пустой результат, collector не падает и переходит на fallback через DuckDuckGo по `site:it.indeed.com` запросам.

Пример запуска:

```bash
python -m src.collectors.indeed_jobs \
  --output output/indeed_jobs.json \
  --limit 5 \
  --top 50 \
  --campania-part-time-first
```

Collector экспортирует `output/indeed_jobs.json`, `output/indeed_jobs.csv` и `output/indeed_jobs.xlsx`.

### Job Aggregator V2

`src/job_aggregator.py` объединяет результаты V2 collectors, сейчас `duckduckgo` и `indeed`, в единый список вакансий. Aggregator запускает выбранные collectors, продолжает работу если один из них упал, нормализует URL, дедуплицирует результаты, пересчитывает `priority_bucket` и сортирует вакансии по приоритету: `campania_part_time`, `remote_data`, `local_general`, `other`, затем по `score` по убыванию.

Пример запуска:

```bash
python -m src.job_aggregator \
  --collectors duckduckgo,indeed \
  --output output/v2_jobs.json \
  --limit 5 \
  --top 50 \
  --campania-part-time-first
```

Рекомендуемый режим — запускать aggregator сразу с очисткой результатов:

```bash
python -m src.job_aggregator \
  --output output/v2_jobs.json \
  --limit 5 \
  --top 50 \
  --campania-part-time-first \
  --clean-results
```

С флагом `--clean-results` aggregator применяет V2 Result Cleaner перед экспортом: удаляет search/category/aggregator страницы, добавляет поле `result_type` и сохраняет в `output/v2_jobs.json`, `output/v2_jobs.csv`, `output/v2_jobs.xlsx` только реальные вакансии с `result_type == job`.

Aggregator экспортирует:
- `output/v2_jobs.json`
- `output/v2_jobs.csv`
- `output/v2_jobs.xlsx`

### V2 Result Cleaner

`src/job_result_cleaner.py` запускается после Job Aggregator V2 и удаляет из результата страницы поиска, каталоги, статьи, профили и агрегаторные страницы, которые могли попасть в discovery-выдачу. Cleaner добавляет поля `result_type` и `url_result_type`; `result_type` может быть `job`, `search_page`, `category_page`, `aggregator_page`, `article`, `profile`, `excluded_domain` или `unknown`, а в финальный export сохраняет только `result_type == job`.

Cleaner также удаляет scam/data-entry-captcha страницы, open-data/dataset страницы, tourism/travel-guide статьи и служебные business pages вроде `fatturazione elettronica`, `marcatempo` и `rilevazione presenze`.

Пример запуска:

```bash
python -m src.job_result_cleaner \
  --input output/v2_jobs.json \
  --output output/v2_jobs_clean.json
```

Cleaner не собирает вакансии и не меняет collectors. Это отдельный post-processing слой для очистки результатов агрегатора.

### URL Pattern Engine

`src/job_url_patterns.py` использует правила из `configs/job_url_patterns.yaml`, чтобы отличать реальные страницы вакансий от search/category/blog/profile страниц по URL. Result Cleaner сначала классифицирует URL и добавляет `url_result_type`, а только затем применяет fallback-правила по title/snippet для неизвестных URL.

Поддерживаемые URL-типы: `real_job`, `search_page`, `category_page`, `aggregator_page`, `article`, `profile`, `excluded_domain`, `unknown`. В clean export попадают только записи с `result_type == job`.

Рекомендуемый запуск V2 aggregator с очисткой:

```bash
python -m src.job_aggregator --output output/v2_jobs.json --limit 5 --top 50 --campania-part-time-first --clean-results
```

### V2 Collector Plugin Registry

V2 aggregator подключает collectors через `src/job_collector_registry.py`. Registry описывает имя collector-а, включён ли он, Python module, callable для запуска и поддерживаемые параметры (`limit`, `top`, `campania_part_time_first`). Чтобы добавить новый collector, нужно добавить его metadata в registry, не меняя `src/job_aggregator.py`.

Запуск всех enabled collectors из registry:

```bash
python -m src.job_aggregator \
  --output output/v2_jobs.json \
  --limit 5 \
  --top 50 \
  --campania-part-time-first
```

Запуск только выбранных collectors:

```bash
python -m src.job_aggregator \
  --collectors duckduckgo,indeed \
  --output output/v2_jobs.json \
  --limit 5 \
  --top 50 \
  --campania-part-time-first
```

## Структура

Главные файлы:
- `scoring_jobs.py` — основной скрипт нормализации, подсчета баллов и экспорта результата;
- `duckduckgo_collector.py` — ищет вакансии и карьерные страницы через DuckDuckGo;
- `job_queries.py` — общие поисковые запросы для морской логистики и Naples-направления;
- `export_search_queries.py` — экспортирует поисковые запросы в `search_queries.csv`;
- `filter_jobs.py` — фильтр для Reddit-постов, сохраняет `filtered_jobs.csv`;
- `himalayas_filter.py` — фильтрует вакансии из `himalayas_jobs.csv`, сохраняет `filtered_himalayas_jobs.csv`;
- `*collector.py` — скрипты для сбора вакансий из источников.

Собранные CSV-файлы:
- `arbeitnow_jobs.csv`
- `remotive_jobs.csv`
- `remotejobs_org_jobs.csv`
- `remotefirstjobs_jobs.csv`
- `jobicy_jobs.csv`
- `workanywhere_jobs.csv`
- `smartjobspa_jobs.csv`
- `attalgroup_jobs.csv`
- `direzionelavoro_jobs.csv`
- `himalayas_jobs.csv`
- `reddit_jobs.csv`
- `duckduckgo_jobs.csv`

Выходные отчеты:
- `filtered_jobs.csv`
- `filtered_himalayas_jobs.csv`
- `scored_jobs.csv`
- `scored_jobs.xlsx`
- `top_50_jobs.csv`
- `top_50_jobs.xlsx`

## Последние изменения

- Добавлен `duckduckgo_collector.py` и входной файл `duckduckgo_jobs.csv`.
- DuckDuckGo collector расширен до 182 уникальных поисковых запросов.
- В DuckDuckGo-запросы добавлены направления из существующих collector-ов:
  `data annotation`, `data annotator`, `AI data annotator`, `AI trainer`,
  `data analyst`, `data operations`, `reporting analyst`, `operations analyst`,
  `workflow analyst`, `data entry`, `Google Sheets`, `Google Workspace`,
  `Excel`, `spreadsheet`, `virtual assistant`, `customer support`,
  `automation support`, `python automation`.
- В DuckDuckGo-запросы также добавлены site-поиски по `himalayas.app`,
  `remotive.com`, `remotejobs.org`, `jobicy.com`, `workanywhere.pro`,
  `linkedin.com/jobs`, `it.indeed.com` и `infojobs.it`.
- Морской блок DuckDuckGo использует `MARITIME_QUERIES` и
  `NAPLES_MARITIME_COMPANY_QUERIES` из `job_queries.py`.
- `scoring_jobs.py` теперь учитывает `duckduckgo_jobs.csv`, если файл существует,
  и не падает, если файл отсутствует или пустой.
- Для DuckDuckGo добавлены `SOURCE_BONUS = 5` и `MIN_SCORE_BY_SOURCE = 25`.
- Финальный короткий отчет расширен с TOP-20 до TOP-50:
  `top_50_jobs.csv` и `top_50_jobs.xlsx`.
- Старые файлы `top_20_jobs.csv` и `top_20_jobs.xlsx` больше не используются.

Последний проверенный запуск:
- `duckduckgo_jobs.csv` — 3002 строки;
- `scored_jobs.csv` — 3078 строк;
- DuckDuckGo в `scored_jobs.csv` — 2267 строк;
- `top_50_jobs.csv` — 50 строк, из них 13 из DuckDuckGo.

## Требования

Используются стандартные библиотеки Python и сторонние пакеты:
- Python 3.10+
- pandas
- requests
- ddgs

Если используется виртуальное окружение, активируйте его перед запуском.

Пример установки зависимостей:

```bash
python -m pip install pandas requests ddgs
```

## Как запускать

### 1. Сбор вакансий

Для каждого источника запускайте соответствующий скрипт.
Примеры:

```bash
python arbeitnow_collector.py
python remotive_collector.py
python remotejobs_org_collector.py
python remotefirstjobs_collector.py
python jobicy_collector.py
python workanywhere_collector.py
python smartjobspa_collector.py
python attalgroup_collector.py
python direzionelavoro_collector.py
python himalayas_collector.py
python reddit_collector.py
python duckduckgo_collector.py
```

Для `remotive` в проекте есть два скрипта: `remotive_collector` и `remotive_collector.py`.

`remotefirstjobs_collector.py` использует базовые запросы и дополнительно подключает `MARITIME_QUERIES` из `job_queries.py`.

### DuckDuckGo collector

`duckduckgo_collector.py` ищет вакансии и карьерные страницы через DuckDuckGo по итальянским, удаленным, логистическим, административным, data/AI и spreadsheet-направлениям.

Запуск:

```bash
python duckduckgo_collector.py
```

Выход:

```text
duckduckgo_jobs.csv
```

После этого:

```bash
python scoring_jobs.py
```

Итоговые файлы:
- `scored_jobs.csv`
- `scored_jobs.xlsx`
- `top_50_jobs.csv`
- `top_50_jobs.xlsx`

DuckDuckGo используется как discovery-layer. Он может находить не только вакансии, но и карьерные страницы компаний, поэтому для него используется небольшой `SOURCE_BONUS` и повышенный `MIN_SCORE_BY_SOURCE`.

Collector фильтрует мусорные домены, удаляет дубли по URL и добавляет сигнал `preferred_domain` для результатов с job-board, career и `lavora-con-noi` доменов. Ошибка одного поискового запроса не останавливает сбор: скрипт печатает ошибку и продолжает следующий запрос.

### Ручной поиск по морской логистике

Чтобы получить CSV с готовыми поисковыми ссылками:

```bash
python export_search_queries.py
```

Скрипт создаст `search_queries.csv` с морскими запросами и отдельными запросами по maritime-компаниям Неаполя.

### 2. Фильтрация

- `python filter_jobs.py` — фильтрует `reddit_jobs.csv` и сохраняет `filtered_jobs.csv`.
- `python himalayas_filter.py` — фильтрует `himalayas_jobs.csv` и сохраняет `filtered_himalayas_jobs.csv`.

### 3. Сортировка и скоринг

Запустите основной скрипт:

```bash
python scoring_jobs.py
```

Он соберет данные из всех доступных файлов, нормализует их, применит скоринг и создаст:
- `scored_jobs.csv`
- `scored_jobs.xlsx`
- `top_50_jobs.csv`
- `top_50_jobs.xlsx`

## Как работает `scoring_jobs.py`

### Нормализация

Скрипт загружает данные из нескольких CSV-файлов и приводит их к общей форме:
- `source`
- `title`
- `company`
- `location`
- `url`
- `description`
- `source_score` (для Reddit берется рейтинг поста)

### Отбор

Перед расчетом баллов выполняется фильтрация по `SIGNAL_PATTERN` — вакансии без хотя бы одной ключевой сигнатуры отбрасываются.

### Скоринг

Баллы считаются так:
- `POSITIVE_WEIGHTS` — добавочные баллы за целевые фразы в тексте;
- `COMBO_WEIGHTS` — дополнительные бонусы за сочетания фраз;
- `NEGATIVE_WEIGHTS` — штрафы за нежелательные фразы;
- `HARD_EXCLUDE_TITLE` — жесткие исключения по заголовку, сразу дают `-100`.

Также есть бонусы за источник в `SOURCE_BONUS` и минимальный порог `MIN_SCORE_BY_SOURCE` для некоторых источников.

#### Морской блок

Проект ориентирован на **морскую логистику**, особенно:

**Ключевые фразы:**
- `ocean freight`, `sea freight`, `freight forwarding` — основные направления
- `bill of lading`, `shipping documentation`, `export/import documentation` — документация
- `port agent`, `ship agent`, `vessel agent`, `shipping agency` — агентства
- `cargo operations`, `container shipping`, `vessel operations`
- `husbandry` — услуги в портах

**Региональный фокус:**
- Naples (Napoli) как региональный центр с реальными агентствами: Agenzia Genovese, F. Andolfi, Rigel, Wilhelmsen
- Ключевые поисковые запросы в `MARITIME_QUERIES` для поиска как удалённых позиций, так и местных агентств

## Удалённый запуск через GitHub Actions

Проект можно запускать полностью удалённо через GitHub Actions, без локального компьютера:

```bash
python -m src.main --queries configs/queries.yaml --scoring configs/scoring.yaml
```

Единый запуск выполняет:
- все текущие collectors;
- фильтрацию Reddit и Himalayas;
- scoring с текущей формулой;
- экспорт итогов в `output/latest/jobs_scored.csv` и `output/latest/jobs_scored.xlsx`;
- создание `output/latest/run_summary.md`;
- отправку HTML email-отчёта, если включены email-настройки.

### Конфигурация queries

Все текущие поисковые запросы перенесены в:

```text
configs/queries.yaml
```

В файле сохранена группировка по источникам:
- `job_queries.maritime` и `job_queries.naples_maritime_company`;
- `duckduckgo`;
- `remotefirstjobs`;
- `jobicy`;
- `reddit`;
- `workanywhere`.

Чтобы изменить запросы, отредактируйте только `configs/queries.yaml`. Не нужно менять Python-код collectors.

### Конфигурация scoring

Все текущие веса scoring перенесены в:

```text
configs/scoring.yaml
```

В файле сохранены:
- `positive_weights`;
- `negative_weights`;
- `combo_weights`;
- `hard_exclude_title`;
- `source_bonus`;
- `min_score_by_source`;
- `filters` для Reddit и Himalayas;
- параметры экспорта.

Формула подсчёта score осталась в `scoring_jobs.py`; YAML меняет только значения весов, порогов и существующие списки фильтрации.

### Запуск workflow с телефона

1. Откройте репозиторий на GitHub.
2. Перейдите в `Actions`.
3. Выберите workflow `Run Job Collectors`.
4. Нажмите `Run workflow`.
5. При необходимости измените inputs:
   - `queries_file`: по умолчанию `configs/queries.yaml`;
   - `scoring_file`: по умолчанию `configs/scoring.yaml`;
   - `email_enabled`: `true` или `false`.
6. Нажмите зелёную кнопку запуска.

### Скачать artifact

После завершения workflow:

1. Откройте завершённый run в `Actions`.
2. Внизу страницы найдите `Artifacts`.
3. Скачайте artifact `job-results`.

Внутри будут файлы из `output/latest/`, включая:
- `jobs_scored.csv`;
- `jobs_scored.xlsx`;
- `top_jobs.xlsx`;
- `run_summary.md`.

### Run V2 jobs from GitHub Actions

V2 запускается из того же workflow `Run Job Collectors`.

1. Откройте репозиторий на GitHub.
2. Перейдите в `Actions`.
3. Выберите workflow `Run Job Collectors`.
4. Нажмите `Run workflow`.
5. Установите inputs:
   - `run_v2_jobs`: `true`;
   - `v2_limit`: сколько результатов брать у коллектора, по умолчанию `2`;
   - `v2_top`: максимум вакансий в экспорте и email, по умолчанию `100`;
   - `v2_clean_results`: `true`, чтобы убрать search/result pages перед экспортом;
   - `email_enabled`: `true`, чтобы отправить V2 email.
6. Нажмите зелёную кнопку запуска.

Команды V2 внутри workflow:

```bash
python -m src.job_aggregator \
  --output output/v2_jobs.json \
  --limit "$v2_limit" \
  --top "$v2_top" \
  --campania-part-time-first \
  --clean-results \
  --min-remote 20

python -m src.v2_email_report \
  --input output/v2_jobs.json \
  --top "$v2_top"
```

V2 export использует balanced TOP, чтобы расширенные Campania запросы не вытесняли remote/data/AI вакансии из `v2_jobs.json`, `v2_jobs.csv` и `v2_jobs.xlsx`. Перед финальным добором по score агрегатор берёт квоты:

- до `--min-remote` из `remote_data`;
- до `--min-data-office` из `data_office`, `campania_part_time_data` и data/back-office сигналов;
- до `--min-hospitality` из hospitality/hotel/restaurant;
- до `--min-cleaning` из cleaning/pulizie;
- до `--min-maintenance` из maintenance/manutenzione.

Если в категории меньше вакансий, чем квота, берётся сколько есть. Дубли не добавляются, а итоговый список всё равно ограничен `--top`; свободные места заполняются оставшимися вакансиями по score.

Локальный пример:

```bash
python -m src.job_aggregator --output output/v2_jobs.json --limit 2 --top 100 --campania-part-time-first --clean-results --min-remote 20
```

Для email нужны GitHub Actions secrets:

```text
EMAIL_SMTP_HOST
EMAIL_SMTP_PORT
EMAIL_SMTP_USER
EMAIL_SMTP_PASSWORD
EMAIL_FROM
EMAIL_TO
```

V2 письмо отправляется только если `email_enabled=true`, `EMAIL_ENABLED=true` в окружении workflow и все SMTP secrets заполнены. Если `output/v2_jobs.json` пустой, письмо не отправляется, а в лог выводится `No V2 jobs to email`.

Тема V2 письма:

```text
Job Intelligence V2: Campania Part-Time + Remote Jobs
```

После завершения workflow скачайте artifact `job-results` внизу страницы run. Для V2 внутри будут:

- `output/v2_jobs.json`;
- `output/v2_jobs.csv`;
- `output/v2_jobs.xlsx`.

### Email-отчёт

Email отправляется только если:

```text
EMAIL_ENABLED=true
```

HTML-письмо содержит статистику запуска и TOP-20 вакансий прямо в теле письма: title, score, source, краткое описание, причины высокого score и прямую ссылку.
Также письмо показывает статистику этапов (`Collected`, `After deduplication`, `After filtering`, `After scoring threshold`, `Top jobs emailed`) и блок `Apply Priority`:
- `HIGH` — score >= 500;
- `MEDIUM` — score >= 350;
- `LOW` — score < 350.

### Защита email от повторных вакансий

Перед формированием письма pipeline загружает историю уже отправленных вакансий из `output/sent_jobs_history.json`. Для каждой вакансии строится стабильный ключ:
- если есть `url`, `link`, `apply_url` или `job_url`, используется нормализованный URL;
- при нормализации из URL удаляются tracking-параметры `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `fbclid`, `gclid`;
- домен приводится к lowercase, trailing slash убирается;
- если URL нет, используется fallback `title + company + location` в lowercase.

В email попадают только вакансии, которых ещё нет в истории. После успешной отправки письма в историю добавляются только реально отправленные вакансии с датой отправки.

TTL истории — 90 дней: записи старше 90 дней удаляются при загрузке истории. Если после фильтрации новых вакансий нет, пустое письмо не отправляется, а в лог выводится `No new jobs to email.`.

Для GitHub Actions история должна сохраняться между чистыми запусками. Workflow `Run Job Collectors` после успешного запуска с `email_enabled=true` автоматически коммитит обновлённый `output/sent_jobs_history.json` обратно в репозиторий, если файл изменился.

Тема письма:

```text
Job Intelligence Report — YYYY-MM-DD
```

Чтобы отключить отправку email, запустите workflow с:

```text
email_enabled=false
```

или установите переменную окружения:

```text
EMAIL_ENABLED=false
```

### GitHub Secrets для email

В GitHub откройте `Settings` -> `Secrets and variables` -> `Actions` и добавьте secrets:

```text
EMAIL_SMTP_HOST
EMAIL_SMTP_PORT
EMAIL_SMTP_USER
EMAIL_SMTP_PASSWORD
EMAIL_FROM
EMAIL_TO
```

Если `EMAIL_ENABLED=true`, но какой-то secret отсутствует, pipeline завершится понятной ошибкой с именами недостающих переменных.

**Языковая специализация:**
- `russian speaking`, `ukrainian speaking` — критические сигналы
- Комбо-бонусы за `freight forwarding + russian/ukrainian`

**Стратегия поиска:**
1. **Основная формула:** `ocean freight + documentation + Russian/Ukrainian + Italy/Naples`
2. **Альтернативная:** `ship agency / port agent + Naples + part-time / freelance / local representative`

### Дедупликация

Перед экспортом убираются дубликаты по:
- `url`
- комбинации `source`, `title`, `company`

### Экспорт

Финальный набор сортируется по `job_score` по убыванию и сохраняется в:
- `scored_jobs.csv`
- `scored_jobs.xlsx`
- `top_50_jobs.csv`
- `top_jobs.xlsx`

`top_50_jobs.csv` и `top_jobs.xlsx` берут первые 50 строк из финального отсортированного DataFrame, оставляя только вакансии с `job_score >= 70`.

В Excel создается столбец `clickable`, который хранит текст `Open`, а ссылка в URL добавляется в XLSX как гиперссылка.

### DuckDuckGo Campania part-time first

Для DuckDuckGo export добавлен режим V2: `--campania-part-time-first`. Он сортирует вакансии так:
1) сначала `part_time=true` и местные упоминания Napoli, Pozzuoli, Bacoli, Monte di Procida, Quarto, Fuorigrotta, Campi Flegrei, Campania;
2) затем `remote=true`;
3) затем по `score` по убыванию.

Новый CSV/XLSX/JSON экспорт теперь сохраняет до 50 результатов по умолчанию и больше не обрезает вывод до 20.

Пример запуска:

```bash
python -m src.collectors.duckduckgo_jobs --config configs/job_sources.yaml --output output/duckduckgo_jobs.json --limit 5 --top 50 --campania-part-time-first
```

## Дополнительные детали

### Источники данных

Проект собирает данные из следующих платформ:
- ArbeitNow
- Remotive
- Remotejobs.org
- RemoteFirstJobs
- Jobicy
- WorkAnywhere
- SmartJobSpa
- Attalgroup
- DirezioneLavoro
- Himalayas
- Reddit
- DuckDuckGo

### Итальянские источники

Скрипт `arca24_collector.py` служит общей базой для итальянских сайтов с похожей структурой и может использоваться для источников `smartjobspa`, `attalgroup` и `direzionelavoro`.

## Добавление нового источника

Чтобы добавить новый источник:
1. Создайте новый collector-скрипт, который сохраняет CSV.
2. Добавьте normalize-функцию в `scoring_jobs.py`.
3. Укажите `source` для нормализации.
4. При необходимости добавьте `SOURCE_BONUS` и `MIN_SCORE_BY_SOURCE`.
5. Запустите `python scoring_jobs.py`.

## Структура данных

Итоговый `scored_jobs.csv` содержит колонки:
- `job_score` — итоговый балл вакансии;
- `source` — источник вакансии;
- `title` — заголовок вакансии;
- `company` — компания;
- `location` — локация;
- `url` — ссылка;
- `clickable` — текст для открытия ссылки в XLSX;
- `score_reason` — причина начисления баллов.

## Замечания

- `scoring_jobs.py` не использует сторонние библиотеки для записи XLSX: он формирует файл руками через `zipfile` и XML.
- Скрипты ориентированы на CSV-файлы в корне проекта.
- `filter_jobs.py` и `himalayas_filter.py` используют разные наборы ключевых слов и предназначены для конкретных источников.

## Рекомендации

### Базовый workflow

- Чтобы получить актуальные данные, предварительно запустите все нужные collector-скрипты.
- Затем отфильтруйте данные там, где это необходимо.
- В конце выполните `python scoring_jobs.py`.

### Стратегия поиска по Неаполю

`MARITIME_QUERIES` и `NAPLES_MARITIME_COMPANY_QUERIES` оптимизированы для поиска позиций в морской логистике Неаполя.

**Где искать:**
- Agenzia Genovese, F. Andolfi, Rigel, Wilhelmsen — реальные агентства
- Платформы: remotejobs.org, jobicy, arbeitnow для удалённых позиций
- Локальные итальянские платформы: smartjobspa, attalgroup, direzionelavoro

**На что обратить внимание:**
- Вакансии с баллом > 100 — сильные кандидаты
- Комбинации языков (Russian/Ukrainian) + морские роли получают 30-80 баллов бонуса
- Naples/Napoli + агентства получают дополнительные 35-40 баллов

---

## Морской блок (Maritime Block)

Проект оптимизирован для поиска позиций в **морской логистике** (ocean freight, shipping, port operations) с фокусом на:

### Ключевые направления
- **Документация:** bill of lading, export/import documentation, shipping documentation
- **Агентства:** port agent, ship agent, vessel agent, shipping agency (особенно Naples)
- **Операции:** cargo operations, container shipping, vessel operations, husbandry services
- **Удалённые роли:** remote freight coordinators, remote logistics documentation

### Языковая специализация
- Русский и украинский языки — критические сигналы (18 баллов + комбо-бонусы)
- Комбинации `freight forwarding + russian/ukrainian` получают +30 баллов
- `Russian/Ukrainian + shipping agency/port agent + Naples` — максимальные бонусы

### Местные агентства (Naples)
Список целевых компаний в `NAPLES_MARITIME_COMPANY_QUERIES` для ручного поиска:
- Agenzia Genovese
- F. Andolfi
- Rigel Shipping Agency
- Wilhelmsen
- Inchcape

### Формула успеха
```
ocean freight + documentation + Russian/Ukrainian + Italy/Naples = 50-80+ баллов
ship agency / port agent + Naples = 40-60+ баллов
```

Используйте `MARITIME_QUERIES` для кастомных поисковых запросов в collector-скриптах или для ручного поиска на LinkedIn, Indeed и местных итальянских платформах.

Если хочешь, могу также сделать краткую схему запуска в виде Bash-сценария или помочь оформить `requirements.txt` для проекта.
