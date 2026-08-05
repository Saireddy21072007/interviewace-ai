"""
The knowledge base behind resume analysis, ATS scoring and the roadmap.

WHY A HAND-BUILT TAXONOMY AND NOT AN LLM CALL
---------------------------------------------
Three reasons, in the order that matters for this product:

1. Determinism. A candidate who uploads the same resume twice must see the
   same ATS score. A model that re-reads the resume each time will drift by a
   few points and destroy trust in the number.
2. Explainability. "You are missing Docker and system design" is a claim we
   can point at a row in this file. An LLM's opinion is not auditable.
3. Cost and latency. Skill matching runs on every upload; it should be free
   and instant.

The LLM's job is the part rules are bad at: phrasing questions, judging the
quality of a spoken answer, and writing feedback. Matching a resume against a
role is a set-intersection problem, so we solve it as one.

Every skill listed here is CANONICAL. `SKILL_ALIASES` maps the messy strings
that actually appear on resumes ("node", "nodejs", "node.js") onto it.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# 1. Canonical skills, grouped only for readability of this file.
# --------------------------------------------------------------------------- #

SKILL_ALIASES: dict[str, list[str]] = {
    # --- languages ---
    "Python": ["python", "python3", "py"],
    "Java": ["java", "core java", "java se"],
    "JavaScript": ["javascript", "js", "es6", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "C": ["c programming", "ansi c"],
    "C++": ["c++", "cpp", "c plus plus"],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": ["golang", "go lang"],
    "SQL": ["sql", "ansi sql", "t-sql", "pl/sql", "plsql"],
    "R": ["r language", "r programming"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift", "swiftui"],
    "Rust": ["rust", "rustlang"],
    "Bash": ["bash", "shell scripting", "shell script"],
    # --- frontend ---
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs", "next js"],
    "Angular": ["angular", "angularjs", "angular 2+"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Redux": ["redux", "redux toolkit", "rtk"],
    "Responsive Design": ["responsive design", "mobile first", "media queries"],
    "Web Accessibility": ["accessibility", "a11y", "wcag"],
    # --- backend ---
    "Node.js": ["node", "nodejs", "node.js"],
    "Express": ["express", "express.js", "expressjs"],
    "FastAPI": ["fastapi", "fast api"],
    "Django": ["django", "django rest framework", "drf"],
    "Flask": ["flask"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "REST APIs": ["rest", "rest api", "restful", "rest apis", "restful api"],
    "GraphQL": ["graphql", "apollo"],
    "WebSockets": ["websocket", "websockets", "socket.io", "socketio"],
    "Microservices": ["microservice", "microservices", "service oriented"],
    "Authentication": ["jwt", "oauth", "oauth2", "authentication", "auth0", "sso"],
    "Caching": ["redis", "memcached", "caching", "cache"],
    "Message Queues": ["kafka", "rabbitmq", "sqs", "celery", "message queue"],
    # --- data ---
    "PostgreSQL": ["postgres", "postgresql", "psql"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongo", "mongodb", "mongoose"],
    "SQLite": ["sqlite", "sqlite3"],
    "Database Design": ["database design", "schema design", "normalization", "erd"],
    "Query Optimisation": ["query optimization", "query optimisation", "indexing", "explain plan"],
    "ETL": ["etl", "elt", "data pipeline", "airflow", "dbt"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Spark": ["spark", "pyspark", "apache spark"],
    "Data Visualisation": ["matplotlib", "seaborn", "plotly", "tableau", "power bi", "d3.js"],
    # --- ai / ml ---
    "Machine Learning": ["machine learning", "ml", "supervised learning", "scikit-learn", "sklearn"],
    "Deep Learning": ["deep learning", "neural network", "neural networks", "cnn", "rnn", "lstm"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow", "tf", "keras"],
    "NLP": ["nlp", "natural language processing", "spacy", "nltk", "text classification"],
    "Computer Vision": ["computer vision", "opencv", "image classification", "object detection"],
    "LLMs": ["llm", "llms", "large language model", "gpt", "claude", "gemini", "llama"],
    "Prompt Engineering": ["prompt engineering", "prompting", "few-shot", "chain of thought"],
    "RAG": ["rag", "retrieval augmented", "vector database", "embeddings", "pinecone", "faiss", "chroma"],
    "Model Evaluation": ["model evaluation", "cross validation", "f1 score", "confusion matrix", "auc"],
    "Feature Engineering": ["feature engineering", "feature selection"],
    "MLOps": ["mlops", "mlflow", "model deployment", "model serving", "model monitoring"],
    "Statistics": ["statistics", "probability", "hypothesis testing", "a/b testing", "regression analysis"],
    # --- infra ---
    "Git": ["git", "github", "gitlab", "version control", "bitbucket"],
    "Docker": ["docker", "containerization", "containerisation", "dockerfile"],
    "Kubernetes": ["kubernetes", "k8s", "helm"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "github actions", "jenkins", "gitlab ci"],
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda", "dynamodb"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "bigquery", "cloud run"],
    "Linux": ["linux", "unix", "ubuntu"],
    "Monitoring": ["monitoring", "observability", "prometheus", "grafana", "datadog", "sentry"],
    "Terraform": ["terraform", "infrastructure as code", "iac"],
    # --- cs fundamentals ---
    "Data Structures": ["data structures", "dsa", "arrays", "linked list", "hash map", "binary tree"],
    "Algorithms": ["algorithms", "dynamic programming", "graph algorithms", "sorting", "complexity analysis"],
    "System Design": ["system design", "distributed systems", "scalability", "load balancing", "sharding"],
    "Operating Systems": ["operating systems", "os concepts", "concurrency", "multithreading", "threads"],
    "Computer Networks": ["computer networks", "tcp/ip", "http", "dns", "networking"],
    "Object Oriented Design": ["oop", "object oriented", "design patterns", "solid principles"],
    # --- quality / process ---
    "Testing": ["testing", "unit testing", "pytest", "jest", "junit", "test driven", "tdd"],
    "Agile": ["agile", "scrum", "kanban", "sprint"],
    "Code Review": ["code review", "pull request", "peer review"],
    "Technical Writing": ["technical writing", "documentation", "api docs"],
    # --- soft skills (matched from bullet phrasing, weighted lightly) ---
    "Communication": ["communication", "presented", "stakeholder", "cross-functional"],
    "Leadership": ["led", "leadership", "mentored", "managed a team", "team lead"],
    "Problem Solving": ["problem solving", "debugging", "root cause", "troubleshooting"],
    "Ownership": ["ownership", "end-to-end", "owned", "drove"],
}

# Reverse index: every surface form -> canonical skill. Built once at import.
ALIAS_TO_SKILL: dict[str, str] = {}
for _canonical, _forms in SKILL_ALIASES.items():
    ALIAS_TO_SKILL[_canonical.lower()] = _canonical
    for _form in _forms:
        ALIAS_TO_SKILL[_form.lower()] = _canonical

ALL_SKILLS: list[str] = sorted(SKILL_ALIASES)

SOFT_SKILLS = {"Communication", "Leadership", "Problem Solving", "Ownership"}


# --------------------------------------------------------------------------- #
# 2. Roles. `must_have` drives the ATS score; `good_to_have` adds bonus points.
# --------------------------------------------------------------------------- #

ROLES: dict[str, dict] = {
    "frontend-developer": {
        "title": "Frontend Developer",
        "family": "engineering",
        "must_have": ["JavaScript", "React", "HTML", "CSS", "Git", "REST APIs"],
        "good_to_have": ["TypeScript", "Tailwind CSS", "Redux", "Testing", "Next.js",
                         "Responsive Design", "Web Accessibility"],
        "focus": ["component design", "state management", "browser rendering", "accessibility"],
    },
    "backend-developer": {
        "title": "Backend Developer",
        "family": "engineering",
        "must_have": ["Python", "REST APIs", "SQL", "Git", "Database Design", "Testing"],
        "good_to_have": ["FastAPI", "Docker", "Caching", "Authentication", "Microservices",
                         "Message Queues", "PostgreSQL", "System Design"],
        "focus": ["API design", "data modelling", "concurrency", "failure handling"],
    },
    "full-stack-developer": {
        "title": "Full Stack Developer",
        "family": "engineering",
        "must_have": ["JavaScript", "React", "REST APIs", "SQL", "Git", "Node.js"],
        "good_to_have": ["TypeScript", "Docker", "CI/CD", "Authentication", "Testing",
                         "PostgreSQL", "System Design", "Tailwind CSS"],
        "focus": ["end-to-end feature delivery", "API contracts", "deployment", "trade-offs"],
    },
    "data-analyst": {
        "title": "Data Analyst",
        "family": "data",
        "must_have": ["SQL", "Python", "Data Visualisation", "Statistics", "Pandas"],
        "good_to_have": ["Excel", "ETL", "Query Optimisation", "Communication", "GCP"],
        "focus": ["metric definition", "SQL depth", "insight communication", "experiment reading"],
    },
    "data-scientist": {
        "title": "Data Scientist",
        "family": "data",
        "must_have": ["Python", "Machine Learning", "Statistics", "Pandas", "SQL", "Model Evaluation"],
        "good_to_have": ["Deep Learning", "Feature Engineering", "NLP", "MLOps",
                         "Data Visualisation", "Spark"],
        "focus": ["problem framing", "validation strategy", "leakage", "business impact"],
    },
    "ml-engineer": {
        "title": "Machine Learning Engineer",
        "family": "ai",
        "must_have": ["Python", "Machine Learning", "Deep Learning", "Model Evaluation", "Git", "Docker"],
        "good_to_have": ["PyTorch", "TensorFlow", "MLOps", "AWS", "CI/CD", "Data Structures", "Spark"],
        "focus": ["training pipelines", "serving latency", "drift monitoring", "reproducibility"],
    },
    "ai-engineer": {
        "title": "AI / LLM Engineer",
        "family": "ai",
        "must_have": ["Python", "LLMs", "Prompt Engineering", "REST APIs", "Git", "Model Evaluation"],
        "good_to_have": ["RAG", "NLP", "PyTorch", "Docker", "MLOps", "FastAPI", "Caching"],
        "focus": ["prompt and eval design", "retrieval quality", "cost per request", "guardrails"],
    },
    "devops-engineer": {
        "title": "DevOps / Cloud Engineer",
        "family": "infra",
        "must_have": ["Linux", "Docker", "CI/CD", "AWS", "Bash", "Git"],
        "good_to_have": ["Kubernetes", "Terraform", "Monitoring", "Python", "Computer Networks"],
        "focus": ["pipeline design", "incident response", "cost control", "infrastructure as code"],
    },
    "sde-fresher": {
        "title": "Software Engineer (Fresher)",
        "family": "engineering",
        "must_have": ["Data Structures", "Algorithms", "Object Oriented Design", "SQL", "Git"],
        "good_to_have": ["Operating Systems", "Computer Networks", "Python", "Java",
                         "System Design", "Testing"],
        "focus": ["DSA fluency", "CS fundamentals", "project depth", "learning ability"],
    },
    "qa-engineer": {
        "title": "QA / SDET",
        "family": "engineering",
        "must_have": ["Testing", "Python", "Git", "REST APIs", "SQL"],
        "good_to_have": ["CI/CD", "Docker", "Selenium", "Agile", "Problem Solving"],
        "focus": ["test strategy", "automation design", "edge cases", "bug reporting"],
    },
}

DEFAULT_ROLE = "full-stack-developer"


def role_or_default(role_key: str | None) -> tuple[str, dict]:
    """Look up a role, tolerating unknown keys and free-text titles."""
    if not role_key:
        return DEFAULT_ROLE, ROLES[DEFAULT_ROLE]
    key = role_key.strip().lower().replace(" ", "-").replace("_", "-")
    if key in ROLES:
        return key, ROLES[key]
    for candidate, spec in ROLES.items():
        if spec["title"].lower() == role_key.strip().lower():
            return candidate, spec
    return DEFAULT_ROLE, ROLES[DEFAULT_ROLE]


# --------------------------------------------------------------------------- #
# 3. Company interview profiles - drives question mix on the setup screen.
# --------------------------------------------------------------------------- #

COMPANIES: dict[str, dict] = {
    "generic": {
        "name": "Generic / Any company",
        "mix": {"technical": 4, "behavioral": 2, "situational": 1, "resume": 2},
        "notes": "Balanced mix. Good default for practice.",
    },
    "product-startup": {
        "name": "Product Startup",
        "mix": {"technical": 4, "resume": 3, "situational": 2, "behavioral": 1},
        "notes": "Depth on what you personally built, and ownership under ambiguity.",
    },
    "service-company": {
        "name": "Service Company (TCS / Infosys / Wipro style)",
        "mix": {"technical": 5, "behavioral": 3, "resume": 2, "situational": 0},
        "notes": "Fundamentals-heavy: DSA, DBMS, OS, OOP, plus HR questions.",
    },
    "faang": {
        "name": "Big Tech (FAANG style)",
        "mix": {"technical": 5, "situational": 2, "behavioral": 2, "resume": 1},
        "notes": "Algorithms and system design depth, plus leadership-principle style behaviourals.",
    },
    "ai-lab": {
        "name": "AI Research / ML Team",
        "mix": {"technical": 5, "resume": 3, "situational": 1, "behavioral": 1},
        "notes": "Modelling choices, evaluation rigour and why-you-did-it-that-way follow-ups.",
    },
}

DEFAULT_COMPANY = "generic"


def company_or_default(key: str | None) -> tuple[str, dict]:
    """Look up a company profile, falling back to the balanced generic mix."""
    if key and key.strip().lower() in COMPANIES:
        return key.strip().lower(), COMPANIES[key.strip().lower()]
    return DEFAULT_COMPANY, COMPANIES[DEFAULT_COMPANY]


# --------------------------------------------------------------------------- #
# 4. Learning resources - what the roadmap points a candidate at.
#    `hours` is the realistic study time, used to pack the weekly plan.
# --------------------------------------------------------------------------- #

RESOURCES: dict[str, list[dict]] = {
    "Data Structures": [
        {"title": "NeetCode 150 - core patterns", "url": "https://neetcode.io/practice", "kind": "practice", "hours": 20},
        {"title": "CS50 - Data Structures lecture", "url": "https://cs50.harvard.edu/x/", "kind": "course", "hours": 4},
    ],
    "Algorithms": [
        {"title": "Striver's A2Z DSA Sheet", "url": "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2", "kind": "practice", "hours": 24},
        {"title": "MIT 6.006 Introduction to Algorithms", "url": "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/", "kind": "course", "hours": 12},
    ],
    "System Design": [
        {"title": "System Design Primer", "url": "https://github.com/donnemartin/system-design-primer", "kind": "reading", "hours": 12},
        {"title": "Design a URL shortener - write your own doc", "url": "https://github.com/donnemartin/system-design-primer#design-a-url-shortener", "kind": "project", "hours": 4},
    ],
    "SQL": [
        {"title": "SQLBolt interactive lessons", "url": "https://sqlbolt.com/", "kind": "practice", "hours": 5},
        {"title": "LeetCode SQL 50", "url": "https://leetcode.com/studyplan/top-sql-50/", "kind": "practice", "hours": 8},
    ],
    "Database Design": [
        {"title": "Use The Index, Luke", "url": "https://use-the-index-luke.com/", "kind": "reading", "hours": 6},
        {"title": "Model your project's schema to 3NF and write the ERD", "url": "", "kind": "project", "hours": 4},
    ],
    "PostgreSQL": [
        {"title": "PostgreSQL Tutorial", "url": "https://www.postgresqltutorial.com/", "kind": "reading", "hours": 6},
    ],
    "Python": [
        {"title": "Real Python - intermediate track", "url": "https://realpython.com/", "kind": "reading", "hours": 10},
    ],
    "JavaScript": [
        {"title": "javascript.info - the modern tutorial", "url": "https://javascript.info/", "kind": "reading", "hours": 12},
    ],
    "TypeScript": [
        {"title": "TypeScript Handbook", "url": "https://www.typescriptlang.org/docs/handbook/intro.html", "kind": "reading", "hours": 6},
        {"title": "Convert one of your JS projects to TS", "url": "", "kind": "project", "hours": 5},
    ],
    "React": [
        {"title": "react.dev - Learn React", "url": "https://react.dev/learn", "kind": "course", "hours": 10},
        {"title": "Build a dashboard with data fetching + routing", "url": "", "kind": "project", "hours": 8},
    ],
    "Node.js": [
        {"title": "Node.js official guides", "url": "https://nodejs.org/en/learn", "kind": "reading", "hours": 6},
    ],
    "FastAPI": [
        {"title": "FastAPI tutorial - user guide", "url": "https://fastapi.tiangolo.com/tutorial/", "kind": "course", "hours": 8},
    ],
    "REST APIs": [
        {"title": "REST API design best practices", "url": "https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design", "kind": "reading", "hours": 3},
        {"title": "Ship a CRUD API with auth, pagination and errors", "url": "", "kind": "project", "hours": 8},
    ],
    "Docker": [
        {"title": "Docker - get started", "url": "https://docs.docker.com/get-started/", "kind": "course", "hours": 5},
        {"title": "Containerise your own project and push the image", "url": "", "kind": "project", "hours": 4},
    ],
    "Kubernetes": [
        {"title": "Kubernetes basics tutorial", "url": "https://kubernetes.io/docs/tutorials/kubernetes-basics/", "kind": "course", "hours": 8},
    ],
    "CI/CD": [
        {"title": "GitHub Actions quickstart", "url": "https://docs.github.com/en/actions/quickstart", "kind": "course", "hours": 4},
        {"title": "Add a test + deploy workflow to your repo", "url": "", "kind": "project", "hours": 3},
    ],
    "AWS": [
        {"title": "AWS Cloud Practitioner Essentials", "url": "https://aws.amazon.com/training/digital/aws-cloud-practitioner-essentials/", "kind": "course", "hours": 10},
    ],
    "Git": [
        {"title": "Pro Git (free book), chapters 1-3", "url": "https://git-scm.com/book/en/v2", "kind": "reading", "hours": 5},
    ],
    "Testing": [
        {"title": "pytest - getting started", "url": "https://docs.pytest.org/en/stable/getting-started.html", "kind": "course", "hours": 4},
        {"title": "Get one of your projects to 60% coverage", "url": "", "kind": "project", "hours": 6},
    ],
    "Machine Learning": [
        {"title": "Andrew Ng - Machine Learning Specialization", "url": "https://www.coursera.org/specializations/machine-learning-introduction", "kind": "course", "hours": 30},
        {"title": "Kaggle Intro to Machine Learning", "url": "https://www.kaggle.com/learn/intro-to-machine-learning", "kind": "practice", "hours": 6},
    ],
    "Deep Learning": [
        {"title": "fast.ai - Practical Deep Learning", "url": "https://course.fast.ai/", "kind": "course", "hours": 25},
    ],
    "PyTorch": [
        {"title": "PyTorch 60-minute blitz", "url": "https://pytorch.org/tutorials/beginner/deep_learning_60min_blitz.html", "kind": "course", "hours": 4},
    ],
    "NLP": [
        {"title": "Hugging Face NLP Course", "url": "https://huggingface.co/learn/nlp-course", "kind": "course", "hours": 20},
    ],
    "LLMs": [
        {"title": "Anthropic - build with Claude docs", "url": "https://docs.anthropic.com/", "kind": "reading", "hours": 5},
        {"title": "Build a tool-using agent from scratch", "url": "", "kind": "project", "hours": 8},
    ],
    "Prompt Engineering": [
        {"title": "Anthropic prompt engineering guide", "url": "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview", "kind": "reading", "hours": 4},
    ],
    "RAG": [
        {"title": "Build a RAG pipeline over your own notes", "url": "", "kind": "project", "hours": 10},
    ],
    "Model Evaluation": [
        {"title": "Google - ML crash course: classification metrics", "url": "https://developers.google.com/machine-learning/crash-course/classification/accuracy", "kind": "course", "hours": 4},
    ],
    "MLOps": [
        {"title": "Made With ML - MLOps course", "url": "https://madewithml.com/", "kind": "course", "hours": 20},
    ],
    "Statistics": [
        {"title": "StatQuest - statistics fundamentals", "url": "https://www.youtube.com/@statquest", "kind": "course", "hours": 10},
    ],
    "Pandas": [
        {"title": "Kaggle Pandas course", "url": "https://www.kaggle.com/learn/pandas", "kind": "practice", "hours": 5},
    ],
    "Data Visualisation": [
        {"title": "Storytelling with Data - core ideas", "url": "https://www.storytellingwithdata.com/", "kind": "reading", "hours": 5},
    ],
    "Operating Systems": [
        {"title": "OSTEP (free textbook)", "url": "https://pages.cs.wisc.edu/~remzi/OSTEP/", "kind": "reading", "hours": 15},
    ],
    "Computer Networks": [
        {"title": "Computer Networking: A Top-Down Approach - ch. 1-3", "url": "", "kind": "reading", "hours": 10},
    ],
    "Object Oriented Design": [
        {"title": "Refactoring Guru - design patterns", "url": "https://refactoring.guru/design-patterns", "kind": "reading", "hours": 8},
    ],
    "Linux": [
        {"title": "Linux Journey", "url": "https://linuxjourney.com/", "kind": "course", "hours": 8},
    ],
    "Communication": [
        {"title": "Record yourself answering 5 questions and rewatch", "url": "", "kind": "project", "hours": 3},
    ],
}

GENERIC_RESOURCE = {
    "kind": "reading",
    "hours": 6,
    "url": "https://roadmap.sh/",
}


def resources_for(skill: str) -> list[dict]:
    """Return learning resources for a skill, synthesising one if unknown."""
    if skill in RESOURCES:
        return RESOURCES[skill]
    return [{"title": f"Learn {skill} - pick one course and one small project", **GENERIC_RESOURCE}]
