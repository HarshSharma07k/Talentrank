"""Cross-domain skill lexicon and matcher for TalentRank's explainability layer.

Domains are declared in the order measured 2026-08-08 to matter most: the corpus is
led by ENGINEERING (9,773), HEALTHCARE (9,019), and SALES (7,772) postings, with
INFORMATION-TECHNOLOGY fourth at 3,659 and 72,686 rows OTHER (see
`.claude/reference/measured-facts.md`). A lexicon that starts with programming terms
would make the flagship explainability feature look broken on the majority of real
results, so the non-tech domains are authored first and are not an afterthought.
"""

from __future__ import annotations

import re

# --- Domain groups (declaration order intentional -- see module docstring) -------

_HEALTHCARE_CLINICAL: dict[str, tuple[str, ...]] = {
    "registered nurse": ("registered nurse", "rn", "r.n."),
    "licensed practical nurse": ("licensed practical nurse", "lpn", "l.p.n."),
    "nurse practitioner": ("nurse practitioner", "np"),
    "certified nursing assistant": ("certified nursing assistant", "cna"),
    "electronic health records": ("electronic health records", "ehr", "emr", "electronic medical records"),
    "patient care": ("patient care",),
    "patient triage": ("patient triage", "triage"),
    "wound care": ("wound care",),
    "phlebotomy": ("phlebotomy", "phlebotomist"),
    "vital signs": ("vital signs",),
    "acls": ("acls", "advanced cardiac life support"),
    "bls": ("bls", "basic life support"),
    "cpr": ("cpr", "cardiopulmonary resuscitation"),
    "medication administration": ("medication administration",),
    "iv therapy": ("iv therapy", "intravenous therapy"),
    "clinical documentation": ("clinical documentation",),
    "hipaa": ("hipaa",),
    "icu": ("icu", "intensive care unit"),
    "emergency room": ("emergency room",),
    "operating room": ("operating room",),
    "surgical assistance": ("surgical assistance", "surgical technician"),
    "case management": ("case management",),
    "discharge planning": ("discharge planning",),
    "physical therapy": ("physical therapy",),
    "occupational therapy": ("occupational therapy",),
    "radiology": ("radiology", "radiologic technologist"),
    "medical billing": ("medical billing",),
    "medical coding": ("medical coding", "icd-10", "cpt coding"),
    "pharmacy technician": ("pharmacy technician",),
    "medical assistant": ("medical assistant", "cma"),
    "home health": ("home health", "home health aide"),
    "hospice care": ("hospice care", "hospice"),
    "infection control": ("infection control",),
    "patient education": ("patient education",),
    "care coordination": ("care coordination",),
    "telemetry": ("telemetry",),
    "dialysis": ("dialysis",),
    "anesthesia": ("anesthesia", "crna"),
    "clinical trials": ("clinical trials",),
    "hemodialysis": ("hemodialysis",),
    "geriatric care": ("geriatric care", "geriatrics"),
}

_ENGINEERING_MECHANICAL: dict[str, tuple[str, ...]] = {
    "mechanical engineering": ("mechanical engineering", "mechanical engineer"),
    "electrical engineering": ("electrical engineering", "electrical engineer"),
    "civil engineering": ("civil engineering", "civil engineer"),
    "structural engineering": ("structural engineering", "structural engineer"),
    "autocad": ("autocad", "auto cad"),
    "solidworks": ("solidworks", "solid works"),
    "catia": ("catia",),
    "blueprint reading": ("blueprint reading", "reading blueprints"),
    "gd&t": ("gd&t", "geometric dimensioning and tolerancing"),
    "manufacturing engineering": ("manufacturing engineering", "manufacturing engineer"),
    "process engineering": ("process engineering", "process engineer"),
    "quality engineering": ("quality engineering", "quality assurance engineering", "quality engineer"),
    "six sigma": ("six sigma",),
    "lean manufacturing": ("lean manufacturing",),
    "root cause analysis": ("root cause analysis", "rca"),
    "plc programming": ("plc programming", "plc"),
    "hvac": ("hvac",),
    "piping design": ("piping design", "piping"),
    "welding": ("welding", "welder"),
    "machining": ("machining", "cnc machining"),
    "cnc": ("cnc", "cnc programming"),
    "thermodynamics": ("thermodynamics",),
    "fluid mechanics": ("fluid mechanics",),
    "project engineering": ("project engineering", "project engineer"),
    "field engineering": ("field engineering", "field engineer"),
    "maintenance engineering": ("maintenance engineering", "preventive maintenance", "maintenance engineer"),
    "industrial engineering": ("industrial engineering", "industrial engineer"),
    "safety engineering": ("safety engineering", "safety engineer"),
    "environmental engineering": ("environmental engineering", "environmental engineer"),
    "chemical engineering": ("chemical engineering", "chemical engineer"),
    "materials science": ("materials science",),
    "finite element analysis": ("finite element analysis", "fea"),
    "product lifecycle management": ("product lifecycle management", "plm"),
    "reliability engineering": ("reliability engineering", "reliability engineer"),
    "instrumentation": ("instrumentation", "instrumentation engineering"),
    "gis mapping": ("gis mapping", "gis"),
}

_SALES_CRM: dict[str, tuple[str, ...]] = {
    "salesforce": ("salesforce", "salesforce.com", "sfdc"),
    "crm": ("crm", "customer relationship management"),
    "cold calling": ("cold calling", "cold outreach"),
    "lead generation": ("lead generation", "lead gen"),
    "account management": ("account management",),
    "business development": ("business development", "biz dev"),
    "sales pipeline": ("sales pipeline", "pipeline management"),
    "quota attainment": ("quota attainment", "quota"),
    "upselling": ("upselling", "upsell"),
    "cross-selling": ("cross-selling", "cross sell"),
    "negotiation": ("negotiation", "contract negotiation"),
    "client relationship management": ("client relationship management",),
    "territory management": ("territory management",),
    "sales forecasting": ("sales forecasting",),
    "b2b sales": ("b2b sales", "b2b"),
    "b2c sales": ("b2c sales", "b2c"),
    "inside sales": ("inside sales",),
    "outside sales": ("outside sales",),
    "sales presentations": ("sales presentations",),
    "closing deals": ("closing deals", "deal closing"),
    "prospecting": ("prospecting",),
    "customer retention": ("customer retention",),
    "key account management": ("key account management", "kam"),
    "revenue growth": ("revenue growth",),
    "sales enablement": ("sales enablement",),
    "hubspot": ("hubspot",),
    "zoho crm": ("zoho crm", "zoho"),
    "channel sales": ("channel sales",),
    "consultative selling": ("consultative selling",),
    "sales quota": ("sales quota",),
}

_CONSTRUCTION_TRADES: dict[str, tuple[str, ...]] = {
    "construction management": ("construction management", "construction manager"),
    "project scheduling": ("project scheduling",),
    "osha 30": ("osha 30",),
    "osha 10": ("osha 10",),
    "carpentry": ("carpentry", "carpenter"),
    "plumbing": ("plumbing", "plumber"),
    "electrical wiring": ("electrical wiring", "electrician"),
    "masonry": ("masonry", "mason"),
    "concrete work": ("concrete work", "concrete"),
    "scaffolding": ("scaffolding",),
    "heavy equipment operation": ("heavy equipment operation", "heavy equipment operator"),
    "excavation": ("excavation",),
    "site supervision": ("site supervision", "site supervisor"),
    "subcontractor management": ("subcontractor management",),
    "building codes": ("building codes",),
    "permitting": ("permitting", "permit acquisition"),
    "quantity surveying": ("quantity surveying", "quantity surveyor"),
    "cost estimation": ("cost estimation", "cost estimating"),
    "framing": ("framing",),
    "roofing": ("roofing", "roofer"),
    "drywall": ("drywall",),
    "hvac installation": ("hvac installation",),
    "forklift operation": ("forklift operation", "forklift certified"),
    "crane operation": ("crane operation", "crane operator"),
    "general contracting": ("general contracting", "general contractor"),
    "punch list": ("punch list",),
    "safety compliance": ("safety compliance",),
    "blueprint interpretation": ("blueprint interpretation",),
    "land surveying": ("land surveying", "surveyor"),
    "site grading": ("site grading", "grading"),
}

_FINANCE_ACCOUNTING: dict[str, tuple[str, ...]] = {
    "financial analysis": ("financial analysis", "financial analyst"),
    "financial modeling": ("financial modeling",),
    "gaap": ("gaap", "generally accepted accounting principles"),
    "accounts payable": ("accounts payable",),
    "accounts receivable": ("accounts receivable",),
    "general ledger": ("general ledger",),
    "bookkeeping": ("bookkeeping", "bookkeeper"),
    "reconciliation": ("reconciliation", "account reconciliation"),
    "budgeting": ("budgeting", "budget management"),
    "forecasting": ("forecasting", "financial forecasting"),
    "variance analysis": ("variance analysis",),
    "quickbooks": ("quickbooks",),
    "sap": ("sap", "sap erp"),
    "financial statements": ("financial statements",),
    "auditing": ("auditing", "auditor"),
    "tax preparation": ("tax preparation",),
    "tax compliance": ("tax compliance",),
    "payroll": ("payroll", "payroll processing"),
    "cost accounting": ("cost accounting",),
    "cpa": ("cpa", "certified public accountant"),
    "cfa": ("cfa", "chartered financial analyst"),
    "risk management": ("risk management",),
    "credit analysis": ("credit analysis",),
    "investment analysis": ("investment analysis",),
    "portfolio management": ("portfolio management",),
    "treasury management": ("treasury management",),
    "month-end close": ("month-end close", "month end close"),
    "accrual accounting": ("accrual accounting",),
    "fp&a": ("fp&a", "financial planning and analysis"),
    "excel": ("excel", "microsoft excel", "ms excel"),
}

_HR_RECRUITING: dict[str, tuple[str, ...]] = {
    "talent acquisition": ("talent acquisition",),
    "recruiting": ("recruiting", "recruiter"),
    "applicant tracking system": ("applicant tracking system", "ats"),
    "onboarding": ("onboarding", "employee onboarding"),
    "employee relations": ("employee relations",),
    "benefits administration": ("benefits administration",),
    "compensation": ("compensation", "compensation and benefits"),
    "performance management": ("performance management",),
    "hris": ("hris", "human resources information system"),
    "workday": ("workday",),
    "hr policies": ("hr policies", "hr policy"),
    "employee engagement": ("employee engagement",),
    "conflict resolution": ("conflict resolution",),
    "training and development": ("training and development",),
    "succession planning": ("succession planning",),
    "diversity and inclusion": ("diversity and inclusion", "dei"),
    "labor relations": ("labor relations",),
    "workforce planning": ("workforce planning",),
    "offer negotiation": ("offer negotiation",),
    "background checks": ("background checks",),
    "exit interviews": ("exit interviews",),
    "hr compliance": ("hr compliance",),
    "employee handbook": ("employee handbook",),
    "organizational design": ("organizational design", "org design"),
}

_EDUCATION: dict[str, tuple[str, ...]] = {
    "curriculum development": ("curriculum development",),
    "lesson planning": ("lesson planning",),
    "classroom management": ("classroom management",),
    "differentiated instruction": ("differentiated instruction",),
    "student assessment": ("student assessment",),
    "iep": ("iep", "individualized education program"),
    "special education": ("special education",),
    "esl instruction": ("esl instruction", "esl", "english as a second language"),
    "tutoring": ("tutoring", "tutor"),
    "k-12 education": ("k-12 education", "k-12"),
    "higher education": ("higher education",),
    "instructional design": ("instructional design",),
    "learning management system": ("learning management system", "lms"),
    "canvas lms": ("canvas lms",),
    "blackboard": ("blackboard",),
    "google classroom": ("google classroom",),
    "standardized testing": ("standardized testing",),
    "parent communication": ("parent communication",),
    "behavior management": ("behavior management",),
    "literacy instruction": ("literacy instruction",),
    "stem education": ("stem education", "stem"),
    "early childhood education": ("early childhood education",),
    "academic advising": ("academic advising",),
    "syllabus design": ("syllabus design",),
}

_LOGISTICS_SUPPLY: dict[str, tuple[str, ...]] = {
    "supply chain management": ("supply chain management",),
    "inventory management": ("inventory management",),
    "logistics coordination": ("logistics coordination", "logistics"),
    "warehouse management": ("warehouse management", "warehouse operations"),
    "procurement": ("procurement",),
    "sourcing": ("sourcing", "strategic sourcing"),
    "demand planning": ("demand planning",),
    "freight coordination": ("freight coordination", "freight"),
    "shipping and receiving": ("shipping and receiving",),
    "fleet management": ("fleet management",),
    "distribution management": ("distribution management",),
    "erp": ("erp", "enterprise resource planning"),
    "warehouse management system": ("warehouse management system", "wms"),
    "dispatching": ("dispatching", "dispatch"),
    "route optimization": ("route optimization",),
    "vendor management": ("vendor management",),
    "purchasing": ("purchasing",),
    "import export": ("import export", "import/export"),
    "customs compliance": ("customs compliance",),
    "cycle counting": ("cycle counting",),
    "order fulfillment": ("order fulfillment",),
    "just in time": ("just in time", "jit"),
    "material handling": ("material handling",),
}

_LEGAL: dict[str, tuple[str, ...]] = {
    "contract review": ("contract review",),
    "contract drafting": ("contract drafting",),
    "legal research": ("legal research",),
    "litigation support": ("litigation support", "litigation"),
    "regulatory compliance": ("regulatory compliance", "compliance"),
    "due diligence": ("due diligence",),
    "paralegal": ("paralegal",),
    "legal writing": ("legal writing",),
    "westlaw": ("westlaw",),
    "lexisnexis": ("lexisnexis", "lexis nexis"),
    "intellectual property": ("intellectual property", "ip law"),
    "e-discovery": ("e-discovery", "discovery"),
    "depositions": ("depositions", "deposition"),
    "corporate law": ("corporate law",),
    "employment law": ("employment law",),
    "real estate law": ("real estate law",),
    "legal documentation": ("legal documentation",),
    "mediation": ("mediation", "mediator"),
    "trial preparation": ("trial preparation",),
    "case law analysis": ("case law analysis",),
}

_HOSPITALITY_FOOD: dict[str, tuple[str, ...]] = {
    "food safety": ("food safety",),
    "servsafe": ("servsafe", "servsafe certified"),
    "menu planning": ("menu planning",),
    "inventory control": ("inventory control",),
    "culinary arts": ("culinary arts",),
    "food preparation": ("food preparation",),
    "kitchen management": ("kitchen management",),
    "customer service": ("customer service",),
    "point of sale systems": ("point of sale systems", "pos system", "pos"),
    "catering": ("catering",),
    "banquet operations": ("banquet operations", "banquets"),
    "front desk operations": ("front desk operations", "front desk"),
    "guest services": ("guest services",),
    "housekeeping": ("housekeeping",),
    "event planning": ("event planning",),
    "food cost control": ("food cost control",),
    "line cooking": ("line cooking", "line cook"),
    "baking and pastry": ("baking and pastry", "pastry"),
    "bartending": ("bartending", "bartender"),
    "hotel management": ("hotel management",),
}

_PROGRAMMING: dict[str, tuple[str, ...]] = {
    "python": ("python",),
    "java": ("java",),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript",),
    "c++": ("c++",),
    "c#": ("c#",),
    "golang": ("golang", "go programming"),
    "rust": ("rust",),
    "git": ("git", "version control"),
    "object-oriented programming": ("object-oriented programming", "oop"),
    "data structures": ("data structures",),
    "algorithms": ("algorithms",),
    "unit testing": ("unit testing",),
    "debugging": ("debugging",),
    "rest api": ("rest api", "restful api", "rest apis"),
    "agile methodology": ("agile methodology", "agile"),
    "scrum": ("scrum", "scrum master"),
    "microservices": ("microservices", "microservice architecture"),
    "node.js": ("node.js", "nodejs", "node js"),
    "django": ("django",),
    "flask": ("flask",),
    "spring boot": ("spring boot", "spring framework"),
    "linux": ("linux", "unix"),
    "bash scripting": ("bash scripting", "shell scripting", "bash"),
    "software architecture": ("software architecture",),
    "design patterns": ("design patterns",),
    "test-driven development": ("test-driven development", "tdd"),
    "code review": ("code review", "code reviews"),
    "php": ("php",),
    "ruby on rails": ("ruby on rails", "ruby"),
    "swift": ("swift",),
    "kotlin": ("kotlin",),
    ".net": (".net", "dotnet", "dot net"),
    "graphql": ("graphql",),
    "c programming": ("c programming",),
}

_DATA_ML: dict[str, tuple[str, ...]] = {
    "machine learning": ("machine learning", "ml"),
    "deep learning": ("deep learning",),
    "data analysis": ("data analysis", "data analytics"),
    "data science": ("data science",),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "tensorflow": ("tensorflow",),
    "pytorch": ("pytorch",),
    "natural language processing": ("natural language processing", "nlp"),
    "computer vision": ("computer vision",),
    "statistical analysis": ("statistical analysis", "statistics"),
    "data visualization": ("data visualization",),
    "tableau": ("tableau",),
    "power bi": ("power bi", "powerbi"),
    "etl": ("etl", "extract transform load"),
    "data engineering": ("data engineering",),
    "data pipelines": ("data pipelines", "data pipeline"),
    "feature engineering": ("feature engineering",),
    "model deployment": ("model deployment",),
    "a/b testing": ("a/b testing", "ab testing"),
    "predictive modeling": ("predictive modeling",),
    "data mining": ("data mining",),
    "big data": ("big data",),
    "apache spark": ("apache spark", "spark"),
    "hadoop": ("hadoop",),
    "r programming": ("r programming",),
}

_CLOUD_DEVOPS: dict[str, tuple[str, ...]] = {
    "aws": ("aws", "amazon web services"),
    "azure": ("azure", "microsoft azure"),
    "gcp": ("gcp", "google cloud platform", "google cloud"),
    "terraform": ("terraform",),
    "ansible": ("ansible",),
    "jenkins": ("jenkins",),
    "ci/cd": ("ci/cd", "continuous integration", "continuous deployment"),
    "docker": ("docker", "containerization"),
    "kubernetes": ("kubernetes", "k8s"),
    "cloudformation": ("cloudformation",),
    "infrastructure as code": ("infrastructure as code", "iac"),
    "prometheus": ("prometheus",),
    "grafana": ("grafana",),
    "site reliability engineering": ("site reliability engineering", "sre"),
    "load balancing": ("load balancing",),
    "autoscaling": ("autoscaling", "auto scaling"),
    "computer networking": ("computer networking", "networking"),
    "amazon s3": ("amazon s3", "s3"),
    "amazon ec2": ("amazon ec2", "ec2"),
    "aws lambda": ("aws lambda", "lambda functions"),
    "devsecops": ("devsecops",),
}

_WEB: dict[str, tuple[str, ...]] = {
    "html": ("html", "html5"),
    "css": ("css", "css3"),
    "react": ("react", "react.js", "reactjs"),
    "angular": ("angular", "angularjs"),
    "vue.js": ("vue.js", "vuejs", "vue"),
    "next.js": ("next.js", "nextjs"),
    "responsive design": ("responsive design",),
    "web accessibility": ("web accessibility", "wcag"),
    "frontend development": ("frontend development", "front-end development", "front end development"),
    "backend development": ("backend development", "back-end development", "back end development"),
    "full stack development": ("full stack development", "full-stack development"),
    "wordpress": ("wordpress",),
    "sass": ("sass", "scss"),
    "tailwind css": ("tailwind css", "tailwindcss"),
    "webpack": ("webpack",),
    "seo": ("seo", "search engine optimization"),
    "cross-browser compatibility": ("cross-browser compatibility",),
    "web performance optimization": ("web performance optimization",),
    "asp.net": ("asp.net", "aspnet"),
}

_DATABASES: dict[str, tuple[str, ...]] = {
    "sql": ("sql",),
    "mysql": ("mysql",),
    "postgresql": ("postgresql", "postgres"),
    "mongodb": ("mongodb", "mongo"),
    "oracle database": ("oracle database", "oracle db"),
    "sql server": ("sql server", "microsoft sql server", "mssql"),
    "database design": ("database design",),
    "database administration": ("database administration", "dba"),
    "data modeling": ("data modeling",),
    "query optimization": ("query optimization",),
    "nosql": ("nosql",),
    "redis": ("redis",),
    "database migration": ("database migration",),
    "stored procedures": ("stored procedures",),
    "database indexing": ("database indexing", "indexing"),
}

_DESIGN_CREATIVE: dict[str, tuple[str, ...]] = {
    "graphic design": ("graphic design",),
    "adobe photoshop": ("adobe photoshop", "photoshop"),
    "adobe illustrator": ("adobe illustrator", "illustrator"),
    "adobe indesign": ("adobe indesign", "indesign"),
    "ui/ux design": ("ui/ux design", "ui ux design", "ux design", "ui design"),
    "figma": ("figma",),
    "sketch app": ("sketch app",),
    "wireframing": ("wireframing", "wireframes"),
    "prototyping": ("prototyping",),
    "typography": ("typography",),
    "branding": ("branding", "brand identity"),
    "visual design": ("visual design",),
    "video editing": ("video editing",),
    "adobe premiere": ("adobe premiere", "premiere pro"),
    "after effects": ("after effects", "adobe after effects"),
    "3d modeling": ("3d modeling", "3d rendering"),
    "motion graphics": ("motion graphics",),
    "print design": ("print design",),
    "packaging design": ("packaging design",),
}

_SOFT_PROFESSIONAL: dict[str, tuple[str, ...]] = {
    "communication skills": ("communication skills", "verbal communication", "written communication"),
    "problem solving": ("problem solving", "problem-solving"),
    "team leadership": ("team leadership", "leadership"),
    "project management": ("project management", "pmp", "project manager"),
    "time management": ("time management",),
    "critical thinking": ("critical thinking",),
    "team collaboration": ("team collaboration", "collaboration"),
    "presentation skills": ("presentation skills",),
    "adaptability": ("adaptability",),
    "attention to detail": ("attention to detail",),
    "multitasking": ("multitasking",),
    "decision making": ("decision making", "decision-making"),
    "interpersonal skills": ("interpersonal skills",),
    "analytical skills": ("analytical skills",),
    "organizational skills": ("organizational skills",),
    "strategic planning": ("strategic planning",),
    "mentoring": ("mentoring", "mentorship"),
    "cross-functional collaboration": ("cross-functional collaboration",),
    "stakeholder management": ("stakeholder management",),
    "public speaking": ("public speaking",),
    "work ethic": ("work ethic",),
    "creativity": ("creativity",),
    "emotional intelligence": ("emotional intelligence",),
}

_DOMAIN_GROUPS: tuple[tuple[str, dict[str, tuple[str, ...]]], ...] = (
    ("healthcare_clinical", _HEALTHCARE_CLINICAL),
    ("engineering_mechanical", _ENGINEERING_MECHANICAL),
    ("sales_crm", _SALES_CRM),
    ("construction_trades", _CONSTRUCTION_TRADES),
    ("finance_accounting", _FINANCE_ACCOUNTING),
    ("hr_recruiting", _HR_RECRUITING),
    ("education", _EDUCATION),
    ("logistics_supply", _LOGISTICS_SUPPLY),
    ("legal", _LEGAL),
    ("hospitality_food", _HOSPITALITY_FOOD),
    ("programming", _PROGRAMMING),
    ("data_ml", _DATA_ML),
    ("cloud_devops", _CLOUD_DEVOPS),
    ("web", _WEB),
    ("databases", _DATABASES),
    ("design_creative", _DESIGN_CREATIVE),
    ("soft_professional", _SOFT_PROFESSIONAL),
)

SKILL_LEXICON: dict[str, tuple[str, ...]] = {}
SKILL_DOMAINS: dict[str, tuple[str, ...]] = {}
for _domain_name, _domain_terms in _DOMAIN_GROUPS:
    SKILL_LEXICON.update(_domain_terms)
    for _canonical in _domain_terms:
        SKILL_DOMAINS[_canonical] = SKILL_DOMAINS.get(_canonical, ()) + (_domain_name,)

# --- Matcher -----------------------------------------------------------------
# `\b` breaks on `c++`, `c#`, `.net`, `node.js` (word-boundary is defined over
# `[A-Za-z0-9_]`, so it doesn't fire next to `+`, `#`, or `.`). Lookarounds against an
# explicit "boundary" character class avoid that trap: a match is only accepted when
# neither the character before nor after it is itself part of a token, where "part of
# a token" includes the symbols aliases legitimately contain.
#
# `.` is deliberately *not* in this class, even though aliases like `.net` and
# `node.js` contain one. Compound tokens like `asp.net` are already protected from a
# bare `.net` match by the alnum check alone (the `p` before `.net` blocks it) plus
# longest-alias-first ordering -- `.` doesn't need to join the class for that. Putting
# it in anyway breaks something far more common than the compound-token edge case:
# `.` is also how English sentences end, so "...general contracting." or
# "...with Node.js." would silently fail to match with `.` included, since the
# lookahead sees the very next character (the sentence's own trailing period) and
# concludes the alias must continue further. Caught by this doc's own manual
# real-corpus verification step, not by a unit test written against comma-separated
# resume bullets -- see engineering-challenges.md.
_BOUNDARY_CLASS = r"[a-z0-9+#]"

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.lower(): canonical for canonical, aliases in SKILL_LEXICON.items() for alias in aliases
}

# Longest-first so "machine learning" wins over "learning" -- Python's `re` tries
# alternatives in listed order and takes the first that matches at a given position,
# so sorting by length descending makes that "first that matches" the longest one.
_SORTED_ALIASES: tuple[str, ...] = tuple(
    sorted({alias for aliases in SKILL_LEXICON.values() for alias in aliases}, key=len, reverse=True)
)

_SKILL_PATTERN = re.compile(
    rf"(?<!{_BOUNDARY_CLASS})(?:{'|'.join(re.escape(alias) for alias in _SORTED_ALIASES)})(?!{_BOUNDARY_CLASS})",
    re.IGNORECASE,
)


def extract_skills(text: str) -> frozenset[str]:
    """Return the canonical skills whose aliases appear in `text`.

    Two passes over `text` (this compiled pattern), no `\\b` boundary trap, and no
    dependency on `data._normalize_text` -- that function strips `+ # . /`, which
    would destroy `c++`, `c#`, `.net`, and `node.js` before this pattern ever saw them.
    """

    if not text:
        return frozenset()

    matches = _SKILL_PATTERN.findall(text)
    return frozenset(_ALIAS_TO_CANONICAL[match.lower()] for match in matches)
