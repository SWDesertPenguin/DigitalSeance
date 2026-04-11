# NIST AI 100-2 Adversarial ML Taxonomy

# Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations
**NIST Trustworthy and Responsible AI** | NIST AI 100-2e2025 | 2025-03

This report describes a taxonomy and terminology for adversarial machine learning (AML) that may aid in securing AI against adversarial manipulations and attacks. It covers both predictive AI (PredAI) and generative AI (GenAI) systems, classifying attacks by system type, lifecycle stage, attacker goals/objectives, attacker capabilities, and attacker knowledge.

---

## Taxonomy Index
### predictive_ai
{'availability_violations': {'id': 'NISTAML.01', 'attacks': [{'id': 'NISTAML.011', 'name': 'Model Poisoning'}, {'id': 'NISTAML.012', 'name': 'Clean-label Poisoning'}, {'id': 'NISTAML.013', 'name': 'Data Poisoning'}, {'id': 'NISTAML.014', 'name': 'Energy-latency'}]}, 'integrity_violations': {'id': 'NISTAML.02', 'attacks': [{'id': 'NISTAML.012', 'name': 'Clean-label Poisoning'}, {'id': 'NISTAML.021', 'name': 'Clean-label Backdoor'}, {'id': 'NISTAML.022', 'name': 'Evasion'}, {'id': 'NISTAML.023', 'name': 'Backdoor Poisoning'}, {'id': 'NISTAML.024', 'name': 'Targeted Poisoning'}, {'id': 'NISTAML.025', 'name': 'Black-box Evasion'}, {'id': 'NISTAML.026', 'name': 'Model Poisoning'}]}, 'privacy_compromises': {'id': 'NISTAML.03', 'attacks': [{'id': 'NISTAML.031', 'name': 'Model Extraction'}, {'id': 'NISTAML.032', 'name': 'Reconstruction'}, {'id': 'NISTAML.033', 'name': 'Membership Inference'}, {'id': 'NISTAML.034', 'name': 'Property Inference'}]}, 'supply_chain_attacks': {'id': 'NISTAML.05', 'attacks': [{'id': 'NISTAML.051', 'name': 'Model Poisoning'}]}}

### generative_ai
{'availability_violations': {'id': 'NISTAML.01', 'attacks': [{'id': 'NISTAML.013', 'name': 'Data Poisoning'}, {'id': 'NISTAML.015', 'name': 'Indirect Prompt Injection'}, {'id': 'NISTAML.018', 'name': 'Prompt Injection'}]}, 'integrity_violations': {'id': 'NISTAML.02', 'attacks': [{'id': 'NISTAML.013', 'name': 'Data Poisoning'}, {'id': 'NISTAML.015', 'name': 'Indirect Prompt Injection'}, {'id': 'NISTAML.018', 'name': 'Prompt Injection'}, {'id': 'NISTAML.023', 'name': 'Backdoor Poisoning'}, {'id': 'NISTAML.024', 'name': 'Targeted Poisoning'}, {'id': 'NISTAML.027', 'name': 'Misaligned Outputs'}]}, 'privacy_compromises': {'id': 'NISTAML.03', 'attacks': [{'id': 'NISTAML.015', 'name': 'Indirect Prompt Injection'}, {'id': 'NISTAML.018', 'name': 'Prompt Injection'}, {'id': 'NISTAML.023', 'name': 'Backdoor Poisoning'}, {'id': 'NISTAML.033', 'name': 'Membership Inference'}, {'id': 'NISTAML.035', 'name': 'Prompt Extraction'}, {'id': 'NISTAML.036', 'name': 'Leaking information from user interactions'}, {'id': 'NISTAML.037', 'name': 'Training Data Attacks'}, {'id': 'NISTAML.038', 'name': 'Data Extraction'}, {'id': 'NISTAML.039', 'name': 'Compromising connected resources'}]}, 'misuse_violations': {'id': 'NISTAML.04', 'attacks': [{'id': 'NISTAML.018', 'name': 'Prompt Injection'}]}, 'supply_chain_attacks': {'id': 'NISTAML.05', 'attacks': [{'id': 'NISTAML.051', 'name': 'Model Poisoning'}]}}

---

## Attack Classification
### dimensions
['AI system type (PredAI vs GenAI)', 'Stage of the ML life cycle when the attack is mounted', 'Attacker goals and objectives', 'Attacker capabilities and access', 'Attacker knowledge of the learning process']

### stages_of_learning
{'training_stage': {'description': 'Attacker controls part of the training data, labels, model parameters, or code — resulting in poisoning attacks', 'attack_types': ['Data Poisoning', 'Model Poisoning']}, 'deployment_stage': {'description': 'ML model is already trained; adversary mounts evasion attacks, privacy attacks, or prompt injection', 'attack_types': ['Evasion', 'Privacy attacks', 'Prompt Injection', 'Indirect Prompt Injection']}}

### attacker_objectives
[{'name': 'Availability Breakdown', 'id': 'NISTAML.01', 'description': 'Deliberate interference to disrupt the ability of other users or processes to obtain timely and reliable access to AI system services'}, {'name': 'Integrity Violation', 'id': 'NISTAML.02', 'description': "Deliberate interference to force misperformance against intended objectives and produce predictions that align with the adversary's objective"}, {'name': 'Privacy Compromise', 'id': 'NISTAML.03', 'description': 'Unintended leakage of restricted or proprietary information from a system, including training data, weights, or architecture'}, {'name': 'Misuse Enablement', 'id': 'NISTAML.04', 'description': "(GenAI only) Circumventing technical restrictions imposed by the GenAI system's owner to prevent harmful outputs", 'genai_only': True}]

### attacker_capabilities
[{'name': 'Training Data Control', 'description': 'Insert or modify training samples; used in data poisoning attacks'}, {'name': 'Model Control', 'description': 'Control model parameters by inserting Trojans or sending malicious federated learning updates'}, {'name': 'Testing Data Control', 'description': 'Add perturbations at deployment time for evasion or backdoor poisoning'}, {'name': 'Label Limit', 'description': 'Restrict adversarial control over training labels (clean-label vs regular poisoning)'}, {'name': 'Source Code Control', 'description': 'Modify ML algorithm source code, random number generators, or third-party libraries'}, {'name': 'Query Access', 'description': 'Submit queries and receive predictions/labels/confidences from the deployed model'}, {'name': 'Resource Control', 'description': '(GenAI) Modify resources ingested by the GenAI model at runtime; enables indirect prompt injection'}]

### attacker_knowledge
[{'level': 'White-box', 'description': 'Full knowledge of training data, model architecture, and hyperparameters. Used for worst-case vulnerability testing.'}, {'level': 'Black-box', 'description': 'Minimal or no knowledge of the ML system. Query access only. Most practical threat model.'}, {'level': 'Gray-box', 'description': 'Partial knowledge — e.g., knows architecture but not parameters, or has data distributed identically to training data.'}]

---

## Predictive Ai Attacks
### NISTAML.022
Adversary generates adversarial examples — samples whose classification can be changed to an arbitrary class with minimal perturbation
**category:** Evasion Attacks
**mitigations:**
- Adversarial training — Augment training with adversarial examples generated iteratively using correct labels
- Randomized smoothing — Transform classifier into certifiable robust smooth classifier under Gaussian noise perturbations
- Formal verification — Use SMT solvers, abstract interpretation, DeepPoly, ReluVal to certify neural network robustness
**key_challenge:** Inherent trade-off between robustness and accuracy; all mitigations have limitations

### ?
**category:** Poisoning Attacks
**subtypes:**
- Availability Poisoning — Indiscriminately degrade entire ML model performance via data poisoning or label flipping
- Targeted Poisoning — Induce misclassification on a small number of targeted samples. Often clean-label (attacker doesn't control labels). Includes subpopulation poisoning.
- Backdoor Poisoning — Insert a backdoor pattern/trigger that causes misclassification of samples containing the trigger. Requires training and testing data control.
- Model Poisoning — Directly modify trained ML model by injecting malicious functionality. Common in federated learning via malicious client updates.
- Supply Chain Model Poisoning — Models or components provided by suppliers are poisoned with malicious code (e.g., Dropout Attack)

### ?
**category:** Privacy Attacks
**subtypes:**
- Data Reconstruction — Recover individual data from released aggregate information or from access to a trained model. Includes model inversion attacks.
- Membership Inference — Determine whether a particular record was in the training dataset. Techniques include loss-based attacks, shadow models, and LiRA.
- Property Inference — Learn global properties about training data distribution (e.g., fraction with a sensitive attribute) via model queries.
- Model Extraction — Extract model architecture and parameters by submitting queries. Techniques include direct extraction, active learning, side-channel attacks (electromagnetic, Rowhammer).
**mitigations:**
- Differential Privacy (DP) — Bounds information leaked about any individual record. DP-SGD is the most widely used algorithm. Provides mitigation against reconstruction and membership inference but NOT model extraction.
- Privacy Auditing — Empirically measure actual privacy guarantees by inserting canaries and measuring their detectability
- Machine Unlearning — Remove a user's data from a trained model via exact retraining or approximate parameter updates
- Query limiting — Restrict number of queries to prevent model extraction (can be circumvented)
- Robust architectures — Design architectures resistant to side-channel information leakage

---

## Generative Ai Attacks
### ?
**category:** Attack Classification
**genai_attacker_capabilities:**
- Training Data Control — Insert/modify training samples for data poisoning
- Query Access — Submit crafted queries for prompt injection, prompt extraction, model extraction
- Resource Control — Modify documents/web pages/databases ingested at runtime for indirect prompt injection
- Model Control — Modify model parameters via fine-tuning APIs for model poisoning or fine-tuning circumvention attacks

### NISTAML.05
**category:** Supply Chain Attacks and Mitigations
**attacks:**
- Data Poisoning — Web-scale data scraping creates large attack surface. Attackers can buy expired domains in training datasets and replace content.
- Model Poisoning — Offer maliciously designed pre-trained models (backdoors persist even after downstream fine-tuning or safety training)
**mitigations:**
- Verify web downloads with cryptographic hashes
- Data filtering to remove poisoned samples
- Vulnerability scanning of model artifacts
- Mechanistic interpretability to identify backdoor features

### NISTAML.018
Attacker is the primary user interacting with the model through query access. Subset: direct prompt injection (user-provided instructions override system prompt).
**category:** Direct Prompting Attacks and Mitigations
**attacker_goals:**
- Enable misuse (jailbreaking)
- Invade privacy (extract system prompt or in-context data)
- Violate integrity (manipulate tool use and API calls)
**attack_techniques:**
- Optimization-based attacks — Gradient/search-based methods to find adversarial inputs (universal adversarial triggers, gradient-based prefixes/suffixes)
- Manual jailbreaking methods —
- Automated model-based red teaming — Use attacker LLM + judge to train jailbreaks against target model. Crescendo attack: multi-turn adaptive approach with seemingly benign prompts.

### NISTAML.015
Attacker manipulates external resources (documents, web pages, databases) ingested by GenAI model at runtime. Enabled by RESOURCE CONTROL capability. Attacks are mounted by a third party, not the primary user.
**category:** Indirect Prompt Injection Attacks and Mitigations
**mitigations:**
- Fine-tuning task-specific models to resist indirect injection
- Training models to follow hierarchical trust relationships in prompts
- Detection schemes for both direct and indirect prompt injection
- Input processing (filtering instructions from third-party data, spotlighting trusted vs untrusted data)
- Design systems assuming model will produce malicious output if exposed to untrusted input
- Use multiple LLMs with different permissions
- Allow model interaction with untrusted data only through well-defined interfaces

### ?
LLM-based agents iteratively prompt models, process outputs, select/call functions with specified inputs, and feed results back. They may have tools (web browsing, code interpreters), memory, and planning capabilities.
**category:** Security of Agents
**risks:**
- Vulnerable to all categories of GenAI attacks (direct and indirect prompt injection)
- Can take real-world actions via tools, amplifying impact of attacks
- Attackers can hijack agents to execute arbitrary code or exfiltrate data
- Security research on agents is still in early stages
**benchmarks:**
- AgentHarm
- AgentDojo

### ?
**category:** Benchmarks for AML Vulnerabilities
**benchmarks:**
- JailbreakBench —
- AdvBench —
- HarmBench —
- StrongREJECT —
- Do-Not-Answer —
- TrustLLM —
- AgentDojo —
- Garak —
- PyRIT —

---

## Key Challenges
### trustworthy_ai_tradeoffs
Inherent trade-offs between accuracy, robustness, fairness, and privacy. Pareto optimization may be needed — no single optimum across all attributes.

### theoretical_limitations
Theoretical impossibility results on AML mitigations exist. Detecting adversarial examples is equivalent to robust classification. Detecting OOD inputs has theoretical bounds. Any alignment process that attenuates (but doesn't remove) undesired behavior will remain vulnerable.

### evaluation
Lack of reliable benchmarks makes AML results incomparable. Mitigations must be tested adversarially against adaptive attacks, not just known attacks.

### scale_challenge
No single entity controls all training data for foundation models. Open-source data poisoning tools increase risk of large-scale attacks.

### supply_chain
AI models can be poisoned to persist through safety training and fine-tuning. Information-theoretically undetectable Trojans may be possible. DARPA/NIST TrojAI program addresses this.

### multimodal_models
Redundancy across modalities does not necessarily improve robustness. Single modality attacks can compromise multimodal models.

### quantized_models
Reduced computational precision introduces additional adversarial vulnerabilities. Quantization methods can be exploited to produce harmful models.

### risk_management
Many AML mitigations are empirical and lack theoretical guarantees. Pre-deployment adversarial testing is necessary but not sufficient.
