from config_loader import load_queries_config


_CONFIG = load_queries_config()
_JOB_QUERY_CONFIG = _CONFIG.get("job_queries", {})

MARITIME_QUERIES = _JOB_QUERY_CONFIG.get("maritime", [
    # Ocean freight / forwarding
    "ocean freight coordinator",
    "ocean operations coordinator",
    "ocean export coordinator",
    "ocean import coordinator",
    "sea freight coordinator",
    "sea freight specialist",
    "freight forwarding specialist",
    "freight operations coordinator",
    "international freight coordinator",
    "multimodal logistics coordinator",
    # Documentation
    "ocean freight documentation specialist",
    "shipping documentation specialist",
    "export documentation specialist",
    "import documentation specialist",
    "bill of lading specialist",
    "documentation coordinator freight forwarding",
    "logistics documentation specialist",
    "trade documentation specialist",
    "customs documentation coordinator",
    # Container shipping
    "container shipping coordinator",
    "container logistics specialist",
    "container booking coordinator",
    "carrier coordinator",
    "shipping line coordinator",
    "vessel schedule coordinator",
    "container operations coordinator",
    # Port / vessel agency
    "port agent",
    "ship agent",
    "vessel agent",
    "shipping agent",
    "husbandry agent",
    "boarding agent",
    "marine operations agent",
    "port operations agent",
    "vessel operations coordinator",
    "ship agency operator",
    "shipping agency operator",
    # Cargo operations
    "cargo operations coordinator",
    "cargo documentation specialist",
    "terminal operations coordinator",
    "stevedoring coordinator",
    "loading discharge coordinator",
    "vessel loading operations",
    "port call coordinator",
    # Remote / hybrid
    "remote ocean freight coordinator",
    "remote freight forwarding",
    "remote shipping coordinator",
    "remote logistics documentation",
    "remote import export coordinator",
    "work from home ocean freight",
    "hybrid ocean freight coordinator",
    "hybrid logistics coordinator",
    # Russian / Ukrainian language angle
    "ocean freight forwarder russian",
    "logistics coordinator russian speaking",
    "shipping coordinator russian speaking",
    "freight forwarding russian",
    "export documentation russian speaking",
    "ukrainian logistics coordinator",
    "russian speaking freight forwarder",
    # Italy / Naples local agent angle
    "shipping agency Naples jobs",
    "port agent Naples",
    "ship agent Naples",
    "vessel agent Naples",
    "maritime agency Naples",
    "husbandry services Naples",
    "port operations Naples",
    "shipping agency Napoli",
    "agente marittimo Napoli",
    "agenzia marittima Napoli lavoro",
    "operativo mare Napoli",
    "spedizioni mare Napoli",
    "documentazione export Napoli",
])


NAPLES_MARITIME_COMPANY_QUERIES = _JOB_QUERY_CONFIG.get("naples_maritime_company", [
    "Agenzia Genovese Napoli careers",
    "F Andolfi Napoli lavoro",
    "Rigel Shipping Agency Napoli careers",
    "Wilhelmsen Napoli port services jobs",
    "Inchcape Napoli port agency jobs",
    "shipping agency Napoli lavora con noi",
    "agenzia marittima Napoli lavora con noi",
    "spedizioniere mare Napoli lavoro",
])
