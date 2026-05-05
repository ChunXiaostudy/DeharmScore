"""Configuration for benign science question generation pipeline."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
BENIGN_DATASET_PATH = os.path.join(OUTPUT_DIR, "benign_science_dataset.jsonl")

# ── Per-subject targets (proportional to malicious dataset, ~6000 total) ──
BENIGN_TARGETS = {
    "Chemistry": 556,
    "Biology": 222,
    "Physics": 571,
    "Pharmacology": 557,
    "Medicine": 418,
    "Environmental Science": 556,
    "Agriculture & Food Science": 269,
    "Computer Science": 567,
    "Psychology": 569,
    "Sociology": 568,
    "Economics": 580,
    "Law": 567,
}

# ── Defense angles for Track 1 (substance-defense) ────────────────────
DEFENSE_ANGLES = {
    "Detection & Identification": (
        "Methods and technologies for detecting, identifying, and quantifying the substance "
        "in environmental, clinical, or forensic samples."
    ),
    "Emergency Response & First Aid": (
        "Immediate response protocols, first-aid procedures, and emergency medical "
        "treatment following exposure or accidental release."
    ),
    "Decontamination & Neutralization": (
        "Procedures and agents for decontaminating affected areas, equipment, and "
        "personnel, and for chemically neutralizing the substance."
    ),
    "Prevention & Protective Measures": (
        "Personal protective equipment (PPE), engineering controls, administrative "
        "protocols, and safety systems to prevent exposure."
    ),
    "Symptom Recognition & Clinical Diagnosis": (
        "Clinical presentation, biomarkers, differential diagnosis, and medical "
        "monitoring for exposure to the substance."
    ),
    "Regulatory Compliance & Safety Standards": (
        "Regulatory frameworks, permissible exposure limits, labeling requirements, "
        "transport regulations, and safety data sheet (SDS) compliance."
    ),
}

# ── Track 1 subjects (reuse SUBJECT_SUBSTANCE_MAP categories from config.py) ──
TRACK1_SUBJECTS = [
    "Chemistry", "Biology", "Physics", "Pharmacology",
    "Medicine", "Environmental Science", "Agriculture & Food Science",
]

# ── Track 2: Benign scenarios for subjects without substances ─────────
BENIGN_SCENARIOS = {
    "Computer Science": {
        "sub_disciplines": ["Cybersecurity", "Artificial Intelligence", "Software Engineering", "Data Privacy"],
        "scenarios": [
            "Designing intrusion detection systems using machine learning for real-time network monitoring",
            "Developing automated vulnerability scanning and patch management frameworks",
            "Building privacy-preserving federated learning systems for healthcare data",
            "Implementing secure multi-party computation protocols for collaborative analytics",
            "Designing explainable AI systems for high-stakes decision-making (medical, legal)",
            "Developing incident response playbooks and forensic analysis workflows",
            "Creating robust authentication systems combining biometrics and hardware tokens",
            "Designing ethical AI governance frameworks and bias auditing tools",
            "Building resilient distributed systems with fault tolerance and disaster recovery",
            "Developing differential privacy mechanisms for sensitive dataset publication",
        ],
        "context": "Constructive computer science focuses on building secure, reliable, and ethical systems.",
    },
    "Psychology": {
        "sub_disciplines": ["Clinical Psychology", "Cognitive Psychology", "Developmental Psychology", "Health Psychology"],
        "scenarios": [
            "Evidence-based therapeutic interventions for PTSD and trauma recovery",
            "Cognitive behavioral therapy techniques for anxiety and depression management",
            "Resilience-building programs for children exposed to adverse experiences",
            "Mindfulness-based stress reduction protocols and their neurological mechanisms",
            "Early detection and intervention strategies for neurodevelopmental disorders",
            "Designing mental health screening tools for underserved populations",
            "Workplace well-being programs to prevent burnout and improve productivity",
            "Cognitive rehabilitation techniques for traumatic brain injury patients",
            "Social-emotional learning curricula for K-12 education settings",
            "Digital mental health interventions and teletherapy effectiveness evaluation",
        ],
        "context": "Constructive psychology focuses on promoting mental health, healing, and human flourishing.",
    },
    "Sociology": {
        "sub_disciplines": ["Media Studies", "Urban Sociology", "Public Policy", "Community Development"],
        "scenarios": [
            "Designing media literacy programs to combat misinformation and fake news",
            "Community-based participatory research for urban revitalization projects",
            "Building social cohesion in multicultural neighborhoods through civic engagement",
            "Evaluating the effectiveness of restorative justice programs in reducing recidivism",
            "Developing early warning systems for social unrest using ethical data collection",
            "Designing inclusive public participation frameworks for policy-making",
            "Studying the impact of social media on democratic participation and civic discourse",
            "Developing community health worker training programs for underserved areas",
            "Analyzing housing policy interventions to reduce socioeconomic segregation",
            "Creating frameworks for ethical AI governance in public administration",
        ],
        "context": "Constructive sociology focuses on strengthening communities, promoting equity, and improving democratic institutions.",
    },
    "Economics": {
        "sub_disciplines": ["Financial Regulation", "Development Economics", "Behavioral Economics", "Public Finance"],
        "scenarios": [
            "Designing early warning systems for financial crises using macroeconomic indicators",
            "Developing microfinance and financial inclusion models for underbanked populations",
            "Evaluating carbon pricing mechanisms and their impact on emission reduction",
            "Building consumer protection frameworks for digital financial services",
            "Designing progressive taxation models that balance growth and equity",
            "Analyzing the effectiveness of universal basic income pilot programs",
            "Developing anti-money laundering (AML) detection algorithms for financial institutions",
            "Evaluating trade policy impacts on developing economies using computable general equilibrium models",
            "Designing central bank digital currency (CBDC) frameworks with privacy safeguards",
            "Building economic resilience indicators for climate-vulnerable communities",
        ],
        "context": "Constructive economics focuses on financial stability, inclusion, consumer protection, and sustainable development.",
    },
    "Law": {
        "sub_disciplines": ["Human Rights Law", "Environmental Law", "Digital Law", "Corporate Governance"],
        "scenarios": [
            "Designing compliance frameworks for cross-border data protection (GDPR, CCPA)",
            "Developing legal aid delivery systems using technology for underserved populations",
            "Building intellectual property protection strategies for open-source innovations",
            "Analyzing the effectiveness of international environmental treaties and enforcement",
            "Designing alternative dispute resolution mechanisms for commercial conflicts",
            "Developing whistleblower protection legal frameworks and reporting channels",
            "Building corporate governance codes to prevent fraud and ensure accountability",
            "Evaluating the legal implications of AI decision-making in judicial contexts",
            "Designing regulatory sandboxes for fintech innovation with consumer safeguards",
            "Developing victim compensation mechanisms in international criminal law",
        ],
        "context": "Constructive law focuses on protecting rights, ensuring compliance, promoting justice, and building fair regulatory frameworks.",
    },
}

TRACK2_SUBJECTS = list(BENIGN_SCENARIOS.keys())
