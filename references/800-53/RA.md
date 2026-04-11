# NIST 800-53: RA — Risk Assessment

## RA-1: Policy and Procedures
(ra-1_smt.a) Develop, document, and disseminate to {{ insert: param, ra-1_prm_1 }}:
    (ra-1_smt.a.1) {{ insert: param, ra-01_odp.03 }} risk assessment policy that:
      (ra-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (ra-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (ra-1_smt.a.2) Procedures

**Guidance:** Risk assessment policy and procedures address the controls in the RA family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assurance. T

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- ra-1_obj.a
- ra-1_obj.b the {{ insert: param, ra-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the risk assessment policy and procedures;
- ra-1_obj.c

---

## RA-2: Security Categorization
(ra-2_smt.a) Categorize the system and information it processes, stores, and transmits;
  (ra-2_smt.b) Document the security categorization results, including supporting rationale, in the security plan for the system; and
  (ra-2_smt.c) Verify that the authorizing official or authorizing official designated representative reviews and approves the security categorization decision.

**Guidance:** Security categories describe the potential adverse impacts or negative consequences to organizational operations, organizational assets, and individuals if organizational information and systems are compromised through a loss of confidentiality, integrity, or availability. Security categorization is

**Related:** CM-8, MP-4, PL-2, PL-10, PL-11, PM-7, RA-3, RA-5, RA-7, RA-8, SA-8, SC-7, SC-38, SI-12

**Assessment Objectives:**
- ra-2_obj.a the system and the information it processes, stores, and transmits are categorized;
- ra-2_obj.b the security categorization results, including supporting rationale, are documented in the security plan for the system;
- ra-2_obj.c the authorizing official or authorizing official designated representative reviews and approves the security categorization decision.

---

## RA-3: Risk Assessment
(ra-3_smt.a) Conduct a risk assessment, including:
    (ra-3_smt.a.1) Identifying threats to and vulnerabilities in the system;
    (ra-3_smt.a.2) Determining the likelihood and magnitude of harm from unauthorized access, use, disclosure, disruption, modification, or destruction of the system, the information it processes, stores, or transmits, and any related information; and
    (ra-3_smt.a.3) Determining the likelihood and impact of adverse effects on individuals arising from the processing o

**Guidance:** Risk assessments consider threats, vulnerabilities, likelihood, and impact to organizational operations and assets, individuals, other organizations, and the Nation. Risk assessments also consider risk from external parties, including contractors who operate systems on behalf of the organization, in

**Related:** CA-3, CA-6, CM-4, CM-13, CP-6, CP-7, IA-8, MA-5, PE-3, PE-8, PE-18, PL-2, PL-10, PL-11, PM-8, PM-9, PM-28, PT-2, PT-7, RA-2, RA-5, RA-7, SA-8, SA-9, SC-38, SI-12

**Assessment Objectives:**
- ra-3_obj.a
- ra-3_obj.b risk assessment results and risk management decisions from the organization and mission or business process perspectives are integrated with system-level risk assessments;
- ra-3_obj.c risk assessment results are documented in {{ insert: param, ra-03_odp.01 }};
- ra-3_obj.d risk assessment results are reviewed {{ insert: param, ra-03_odp.03 }};
- ra-3_obj.e risk assessment results are disseminated to {{ insert: param, ra-03_odp.04 }};
- ra-3_obj.f the risk assessment is updated {{ insert: param, ra-03_odp.05 }} or when there are significant changes to the system, its environment of operation, or other conditions that may impact the security or privacy state of the system.

---

## RA-5: Vulnerability Monitoring and Scanning
(ra-5_smt.a) Monitor and scan for vulnerabilities in the system and hosted applications {{ insert: param, ra-5_prm_1 }} and when new vulnerabilities potentially affecting the system are identified and reported;
  (ra-5_smt.b) Employ vulnerability monitoring tools and techniques that facilitate interoperability among tools and automate parts of the vulnerability management process by using standards for:
    (ra-5_smt.b.1) Enumerating platforms, software flaws, and improper configurations;
    (r

**Guidance:** Security categorization of information and systems guides the frequency and comprehensiveness of vulnerability monitoring (including scans). Organizations determine the required vulnerability monitoring for system components, ensuring that the potential sources of vulnerabilities—such as infrastruct

**Related:** CA-2, CA-7, CA-8, CM-2, CM-4, CM-6, CM-8, RA-2, RA-3, SA-11, SA-15, SC-38, SI-2, SI-3, SI-4, SI-7, SR-11

**Assessment Objectives:**
- ra-5_obj.a
- ra-5_obj.b vulnerability monitoring tools and techniques are employed to facilitate interoperability among tools;
- ra-5_obj.c vulnerability scan reports and results from vulnerability monitoring are analyzed;
- ra-5_obj.d legitimate vulnerabilities are remediated {{ insert: param, ra-05_odp.03 }} in accordance with an organizational assessment of risk;
- ra-5_obj.e information obtained from the vulnerability monitoring process and control assessments is shared with {{ insert: param, ra-05_odp.04 }} to help eliminate similar vulnerabilities in other systems;
- ra-5_obj.f vulnerability monitoring tools that include the capability to readily update the vulnerabilities to be scanned are employed.

---

## RA-6: Technical Surveillance Countermeasures Survey
Employ a technical surveillance countermeasures survey at {{ insert: param, ra-06_odp.01 }} {{ insert: param, ra-06_odp.02 }}.

**Guidance:** A technical surveillance countermeasures survey is a service provided by qualified personnel to detect the presence of technical surveillance devices and hazards and to identify technical security weaknesses that could be used in the conduct of a technical penetration of the surveyed facility. Techn

---

## RA-7: Risk Response
Respond to findings from security and privacy assessments, monitoring, and audits in accordance with organizational risk tolerance.

**Guidance:** Organizations have many options for responding to risk including mitigating risk by implementing new controls or strengthening existing controls, accepting risk with appropriate justification or rationale, sharing or transferring risk, or avoiding risk. The risk tolerance of the organization influen

**Related:** CA-5, IR-9, PM-4, PM-28, RA-2, RA-3, SR-2

**Assessment Objectives:**
- ra-7_obj-1 findings from security assessments are responded to in accordance with organizational risk tolerance;
- ra-7_obj-2 findings from privacy assessments are responded to in accordance with organizational risk tolerance;
- ra-7_obj-3 findings from monitoring are responded to in accordance with organizational risk tolerance;
- ra-7_obj-4 findings from audits are responded to in accordance with organizational risk tolerance.

---

## RA-8: Privacy Impact Assessments
Conduct privacy impact assessments for systems, programs, or other activities before:
  (ra-8_smt.a) Developing or procuring information technology that processes personally identifiable information; and
  (ra-8_smt.b) Initiating a new collection of personally identifiable information that:
    (ra-8_smt.b.1) Will be processed using information technology; and
    (ra-8_smt.b.2) Includes personally identifiable information permitting the physical or virtual (online) contacting of a specific indi

**Guidance:** A privacy impact assessment is an analysis of how personally identifiable information is handled to ensure that handling conforms to applicable privacy requirements, determine the privacy risks associated with an information system or activity, and evaluate ways to mitigate privacy risks. A privacy

**Related:** CM-4, CM-9, CM-13, PT-2, PT-3, PT-5, RA-1, RA-2, RA-3, RA-7

**Assessment Objectives:**
- ra-8_obj.a privacy impact assessments are conducted for systems, programs, or other activities before developing or procuring information technology that processes personally identifiable information;
- ra-8_obj.b

---

## RA-9: Criticality Analysis
Identify critical system components and functions by performing a criticality analysis for {{ insert: param, ra-09_odp.01 }} at {{ insert: param, ra-09_odp.02 }}.

**Guidance:** Not all system components, functions, or services necessarily require significant protections. For example, criticality analysis is a key tenet of supply chain risk management and informs the prioritization of protection activities. The identification of critical system components and functions cons

**Related:** CP-2, PL-2, PL-8, PL-11, PM-1, PM-11, RA-2, SA-8, SA-15, SA-20, SR-5

---

## RA-10: Threat Hunting
(ra-10_smt.a) Establish and maintain a cyber threat hunting capability to:
    (ra-10_smt.a.1) Search for indicators of compromise in organizational systems; and
    (ra-10_smt.a.2) Detect, track, and disrupt threats that evade existing controls; and
  (ra-10_smt.b) Employ the threat hunting capability {{ insert: param, ra-10_odp }}.

**Guidance:** Threat hunting is an active means of cyber defense in contrast to traditional protection measures, such as firewalls, intrusion detection and prevention systems, quarantining malicious code in sandboxes, and Security Information and Event Management technologies and systems. Cyber threat hunting inv

**Related:** CA-2, CA-7, CA-8, RA-3, RA-5, RA-6, SI-4

**Assessment Objectives:**
- ra-10_obj.a
- ra-10_obj.b the threat hunting capability is employed {{ insert: param, ra-10_odp }}.
