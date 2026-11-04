"""Skill taxonomy: canonical names, aliases and detection. Used for normalization, matching and grounding."""

import re
from functools import lru_cache

# (canonical, aliases, group)
_SKILLS: list[tuple[str, list[str], str]] = [
    # languages
    ("Python", ["python", "python3"], "language"),
    ("SQL", ["sql", "t-sql", "tsql", "pl/sql", "plsql", "pl-sql"], "language"),
    ("Java", ["java"], "language"),
    ("Scala", ["scala"], "language"),
    ("JavaScript", ["javascript", "js", "ecmascript"], "language"),
    ("TypeScript", ["typescript"], "language"),
    ("C#", ["c#", "c sharp", "csharp"], "language"),
    ("C++", ["c++"], "language"),
    ("Go", ["golang", "go lang"], "language"),
    ("R", ["r programming", "r language"], "language"),
    ("Bash", ["bash", "shell scripting", "shell script"], "language"),
    ("PowerShell", ["powershell"], "language"),
    # data engineering
    ("Apache Spark", ["spark", "apache spark"], "data"),
    ("PySpark", ["pyspark"], "data"),
    ("Databricks", ["databricks"], "data"),
    ("Delta Lake", ["delta lake", "delta tables", "delta table"], "data"),
    ("Apache Kafka", ["kafka", "apache kafka"], "data"),
    ("Apache Airflow", ["airflow", "apache airflow"], "data"),
    ("dbt", ["dbt", "data build tool"], "data"),
    ("Hadoop", ["hadoop", "hdfs", "mapreduce"], "data"),
    ("Hive", ["hive", "apache hive"], "data"),
    ("Snowflake", ["snowflake"], "data"),
    ("ETL", ["etl", "elt", "etl/elt", "data pipelines", "data pipeline"], "data"),
    ("Data Modeling", ["data modeling", "data modelling", "dimensional modeling", "star schema"], "data"),
    ("Data Warehousing", ["data warehouse", "data warehousing", "dwh"], "data"),
    ("Data Lake", ["data lake", "datalake", "lakehouse"], "data"),
    ("Medallion Architecture", ["medallion architecture", "medallion"], "data"),
    ("Unity Catalog", ["unity catalog"], "data"),
    ("Power BI", ["power bi", "powerbi"], "bi"),
    ("Tableau", ["tableau"], "bi"),
    ("Looker", ["looker"], "bi"),
    ("Excel", ["excel", "advanced excel"], "bi"),
    ("DAX", ["dax"], "bi"),
    # azure
    ("Azure", ["azure", "microsoft azure"], "cloud"),
    ("Azure Data Factory", ["azure data factory", "adf"], "cloud"),
    ("Azure Synapse", ["azure synapse", "synapse analytics", "synapse"], "cloud"),
    ("Azure Data Lake Storage", ["adls", "azure data lake", "adls gen2"], "cloud"),
    ("Azure Functions", ["azure functions"], "cloud"),
    ("Azure DevOps", ["azure devops", "ado pipelines"], "devops"),
    ("Microsoft Fabric", ["microsoft fabric", "fabric lakehouse"], "cloud"),
    ("Azure Event Hubs", ["event hubs", "event hub"], "cloud"),
    ("Azure Key Vault", ["key vault"], "cloud"),
    # aws / gcp
    ("AWS", ["aws", "amazon web services"], "cloud"),
    ("AWS Glue", ["aws glue", "glue"], "cloud"),
    ("Amazon S3", ["s3", "amazon s3"], "cloud"),
    ("Amazon Redshift", ["redshift", "amazon redshift"], "cloud"),
    ("AWS Lambda", ["lambda", "aws lambda"], "cloud"),
    ("Amazon EMR", ["emr", "amazon emr"], "cloud"),
    ("GCP", ["gcp", "google cloud", "google cloud platform"], "cloud"),
    ("BigQuery", ["bigquery", "big query"], "cloud"),
    ("Dataflow", ["dataflow", "apache beam"], "cloud"),
    # databases
    ("PostgreSQL", ["postgresql", "postgres"], "database"),
    ("MySQL", ["mysql"], "database"),
    ("SQL Server", ["sql server", "mssql", "ms sql"], "database"),
    ("Oracle", ["oracle database", "oracle db", "oracle"], "database"),
    ("MongoDB", ["mongodb", "mongo"], "database"),
    ("Redis", ["redis"], "database"),
    ("Cassandra", ["cassandra"], "database"),
    ("Elasticsearch", ["elasticsearch", "elastic search"], "database"),
    # devops / infra
    ("Docker", ["docker"], "devops"),
    ("Kubernetes", ["kubernetes", "k8s"], "devops"),
    ("Terraform", ["terraform"], "devops"),
    ("Ansible", ["ansible"], "devops"),
    ("Jenkins", ["jenkins"], "devops"),
    ("GitHub Actions", ["github actions"], "devops"),
    ("GitLab CI", ["gitlab ci", "gitlab ci/cd"], "devops"),
    ("CI/CD", ["ci/cd", "cicd", "ci cd", "continuous integration"], "devops"),
    ("Git", ["git", "github", "gitlab", "bitbucket"], "devops"),
    ("Linux", ["linux", "unix"], "devops"),
    ("Prometheus", ["prometheus"], "devops"),
    ("Grafana", ["grafana"], "devops"),
    ("Infrastructure as Code", ["infrastructure as code", "iac", "bicep", "arm templates", "cloudformation"], "devops"),
    # software
    ("REST APIs", ["rest api", "rest apis", "restful", "rest"], "software"),
    ("GraphQL", ["graphql"], "software"),
    ("Microservices", ["microservices", "microservice"], "software"),
    ("FastAPI", ["fastapi"], "software"),
    ("Django", ["django"], "software"),
    ("Flask", ["flask"], "software"),
    ("Spring Boot", ["spring boot", "spring"], "software"),
    ("Node.js", ["node.js", "nodejs", "node js"], "software"),
    ("React", ["react", "react.js", "reactjs"], "software"),
    ("Next.js", ["next.js", "nextjs"], "software"),
    ("Angular", ["angular"], "software"),
    ("Vue.js", ["vue", "vue.js"], "software"),
    ("HTML/CSS", ["html", "css", "html5", "css3"], "software"),
    ("Unit Testing", ["unit testing", "pytest", "junit", "unit tests"], "software"),
    ("Agile", ["agile", "scrum", "kanban"], "process"),
    # ml / analytics
    ("Machine Learning", ["machine learning", "ml"], "ml"),
    ("Deep Learning", ["deep learning"], "ml"),
    ("scikit-learn", ["scikit-learn", "sklearn", "scikit learn"], "ml"),
    ("TensorFlow", ["tensorflow"], "ml"),
    ("PyTorch", ["pytorch"], "ml"),
    ("Pandas", ["pandas"], "ml"),
    ("NumPy", ["numpy"], "ml"),
    ("NLP", ["nlp", "natural language processing"], "ml"),
    ("LLMs", ["llm", "llms", "large language models", "generative ai", "genai"], "ml"),
    ("MLflow", ["mlflow"], "ml"),
    ("Statistics", ["statistics", "statistical analysis", "hypothesis testing"], "ml"),
    ("A/B Testing", ["a/b testing", "ab testing"], "ml"),
    ("Data Visualization", ["data visualization", "data visualisation"], "bi"),
    ("Data Governance", ["data governance", "data quality"], "data"),
]

# Typical certification patterns for detection in job text and resumes.
CERT_PATTERNS = [
    r"\bDP-\d{3}\b", r"\bAZ-\d{3}\b", r"\bPL-\d{3}\b", r"\bDA-\d{3}\b", r"\bAI-\d{3}\b",
    r"\bAWS Certified [A-Za-z\- ]+", r"\bDatabricks Certified [A-Za-z\- ]+",
    r"\bGoogle (?:Cloud )?(?:Professional|Associate) [A-Za-z\- ]+", r"\bCKA\b", r"\bCKAD\b",
    r"\bPMP\b", r"\bSnowPro [A-Za-z\- ]*",
]

_ALIAS_TO_CANON: dict[str, str] = {}
for canon, aliases, _group in _SKILLS:
    _ALIAS_TO_CANON[canon.lower()] = canon
    for a in aliases:
        _ALIAS_TO_CANON.setdefault(a.lower(), canon)

SKILL_GROUPS: dict[str, str] = {c: g for c, _a, g in _SKILLS}


def canonical(skill: str) -> str:
    """Canonical skill name; unknown skills are returned stripped and unchanged."""
    s = skill.strip()
    return _ALIAS_TO_CANON.get(s.lower(), s)


def canonical_key(skill: str) -> str:
    return canonical(skill).lower()


@lru_cache
def _patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for alias, canon in sorted(_ALIAS_TO_CANON.items(), key=lambda kv: -len(kv[0])):
        esc = re.escape(alias)
        # Word boundaries that also work for names ending in symbols (c#, c++, node.js).
        pat = re.compile(rf"(?<![A-Za-z0-9+#]){esc}(?![A-Za-z0-9+#])", re.IGNORECASE)
        out.append((canon, pat))
    return out


def extract_skills(text: str) -> list[str]:
    """Return canonical skills mentioned in `text`, preserving first-appearance order."""
    found: dict[str, int] = {}
    for canon, pat in _patterns():
        m = pat.search(text)
        if m and canon not in found:
            found[canon] = m.start()
    return [c for c, _ in sorted(found.items(), key=lambda kv: kv[1])]


def extract_certifications(text: str) -> list[str]:
    out: list[str] = []
    for p in CERT_PATTERNS:
        for m in re.finditer(p, text):
            val = m.group(0).strip()
            if val not in out:
                out.append(val)
    return out


def skill_set(skills: list[str]) -> set[str]:
    return {canonical_key(s) for s in skills if s and s.strip()}
