# NIST 800-53: SR — Supply Chain Risk Management

## SR-1: Policy and Procedures
(sr-1_smt.a) Develop, document, and disseminate to {{ insert: param, sr-1_prm_1 }}:
    (sr-1_smt.a.1) {{ insert: param, sr-01_odp.03 }} supply chain risk management policy that:
      (sr-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (sr-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (sr-1_smt.a.2

**Guidance:** Supply chain risk management policy and procedures address the controls in the SR family as well as supply chain-related controls in other families that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures.

**Related:** PM-9, PM-30, PS-8, SI-12

**Assessment Objectives:**
- sr-1_obj.a
- sr-1_obj.b the {{ insert: param, sr-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the supply chain risk management policy and procedures;
- sr-1_obj.c

---

## SR-2: Supply Chain Risk Management Plan
(sr-2_smt.a) Develop a plan for managing supply chain risks associated with the research and development, design, manufacturing, acquisition, delivery, integration, operations and maintenance, and disposal of the following systems, system components or system services: {{ insert: param, sr-02_odp.01 }};
  (sr-2_smt.b) Review and update the supply chain risk management plan {{ insert: param, sr-02_odp.02 }} or as required, to address threat, organizational or environmental changes; and
  (sr-2_sm

**Guidance:** The dependence on products, systems, and services from external providers, as well as the nature of the relationships with those providers, present an increasing level of risk to an organization. Threat actions that may increase security or privacy risks include unauthorized production, the insertio

**Related:** CA-2, CP-4, IR-4, MA-2, MA-6, PE-16, PL-2, PM-9, PM-30, RA-3, RA-7, SA-8, SI-4

**Assessment Objectives:**
- sr-2_obj.a
- sr-2_obj.b the supply chain risk management plan is reviewed and updated {{ insert: param, sr-02_odp.02 }} or as required to address threat, organizational, or environmental changes;
- sr-2_obj.c

---

## SR-3: Supply Chain Controls and Processes
(sr-3_smt.a) Establish a process or processes to identify and address weaknesses or deficiencies in the supply chain elements and processes of {{ insert: param, sr-03_odp.01 }} in coordination with {{ insert: param, sr-03_odp.02 }};
  (sr-3_smt.b) Employ the following controls to protect against supply chain risks to the system, system component, or system service and to limit the harm or consequences from supply chain-related events: {{ insert: param, sr-03_odp.03 }} ; and
  (sr-3_smt.c) Docume

**Guidance:** Supply chain elements include organizations, entities, or tools employed for the research and development, design, manufacturing, acquisition, delivery, integration, operations and maintenance, and disposal of systems and system components. Supply chain processes include hardware, software, and firm

**Related:** CA-2, MA-2, MA-6, PE-3, PE-16, PL-8, PM-30, SA-2, SA-3, SA-4, SA-5, SA-8, SA-9, SA-10, SA-15, SC-7, SC-29, SC-30, SC-38, SI-7, SR-6, SR-9, SR-11

**Assessment Objectives:**
- sr-3_obj.a
- sr-3_obj.b {{ insert: param, sr-03_odp.03 }} are employed to protect against supply chain risks to the system, system component, or system service and to limit the harm or consequences from supply chain-related events;
- sr-3_obj.c the selected and implemented supply chain processes and controls are documented in {{ insert: param, sr-03_odp.04 }}.

---

## SR-4: Provenance
Document, monitor, and maintain valid provenance of the following systems, system components, and associated data: {{ insert: param, sr-04_odp }}.

**Guidance:** Every system and system component has a point of origin and may be changed throughout its existence. Provenance is the chronology of the origin, development, ownership, location, and changes to a system or system component and associated data. It may also include personnel and processes used to inte

**Related:** CM-8, MA-2, MA-6, RA-9, SA-3, SA-8, SI-4

**Assessment Objectives:**
- sr-4_obj-1 valid provenance is documented for {{ insert: param, sr-04_odp }};
- sr-4_obj-2 valid provenance is monitored for {{ insert: param, sr-04_odp }};
- sr-4_obj-3 valid provenance is maintained for {{ insert: param, sr-04_odp }}.

---

## SR-5: Acquisition Strategies, Tools, and Methods
Employ the following acquisition strategies, contract tools, and procurement methods to protect against, identify, and mitigate supply chain risks: {{ insert: param, sr-05_odp }}.

**Guidance:** The use of the acquisition process provides an important vehicle to protect the supply chain. There are many useful tools and techniques available, including obscuring the end use of a system or system component, using blind or filtered buys, requiring tamper-evident packaging, or using trusted or c

**Related:** AT-3, SA-2, SA-3, SA-4, SA-5, SA-8, SA-9, SA-10, SA-15, SR-6, SR-9, SR-10, SR-11

**Assessment Objectives:**
- sr-5_obj-1 {{ insert: param, sr-05_odp }} are employed to protect against supply chain risks;
- sr-5_obj-2 {{ insert: param, sr-05_odp }} are employed to identify supply chain risks;
- sr-5_obj-3 {{ insert: param, sr-05_odp }} are employed to mitigate supply chain risks.

---

## SR-6: Supplier Assessments and Reviews
Assess and review the supply chain-related risks associated with suppliers or contractors and the system, system component, or system service they provide {{ insert: param, sr-06_odp }}.

**Guidance:** An assessment and review of supplier risk includes security and supply chain risk management processes, foreign ownership, control or influence (FOCI), and the ability of the supplier to effectively assess subordinate second-tier and third-tier suppliers and contractors. The reviews may be conducted

**Related:** SR-3, SR-5

---

## SR-7: Supply Chain Operations Security
Employ the following Operations Security (OPSEC) controls to protect supply chain-related information for the system, system component, or system service: {{ insert: param, sr-07_odp }}.

**Guidance:** Supply chain OPSEC expands the scope of OPSEC to include suppliers and potential suppliers. OPSEC is a process that includes identifying critical information, analyzing friendly actions related to operations and other activities to identify actions that can be observed by potential adversaries, dete

**Related:** SC-38

---

## SR-8: Notification Agreements
Establish agreements and procedures with entities involved in the supply chain for the system, system component, or system service for the {{ insert: param, sr-08_odp.01 }}.

**Guidance:** The establishment of agreements and procedures facilitates communications among supply chain entities. Early notification of compromises and potential compromises in the supply chain that can potentially adversely affect or have adversely affected organizational systems or system components is essen

**Related:** IR-4, IR-6, IR-8

---

## SR-9: Tamper Resistance and Detection
Implement a tamper protection program for the system, system component, or system service.

**Guidance:** Anti-tamper technologies, tools, and techniques provide a level of protection for systems, system components, and services against many threats, including reverse engineering, modification, and substitution. Strong identification combined with tamper resistance and/or tamper detection is essential t

**Related:** PE-3, PM-30, SA-15, SI-4, SI-7, SR-3, SR-4, SR-5, SR-10, SR-11

---

## SR-10: Inspection of Systems or Components
Inspect the following systems or system components {{ insert: param, sr-10_odp.02 }} to detect tampering: {{ insert: param, sr-10_odp.01 }}.

**Guidance:** The inspection of systems or systems components for tamper resistance and detection addresses physical and logical tampering and is applied to systems and system components removed from organization-controlled areas. Indications of a need for inspection include changes in packaging, specifications,

**Related:** AT-3, PM-30, SI-4, SI-7, SR-3, SR-4, SR-5, SR-9, SR-11

---

## SR-11: Component Authenticity
(sr-11_smt.a) Develop and implement anti-counterfeit policy and procedures that include the means to detect and prevent counterfeit components from entering the system; and
  (sr-11_smt.b) Report counterfeit system components to {{ insert: param, sr-11_odp.01 }}.

**Guidance:** Sources of counterfeit components include manufacturers, developers, vendors, and contractors. Anti-counterfeiting policies and procedures support tamper resistance and provide a level of protection against the introduction of malicious code. External reporting organizations include CISA.

**Related:** PE-3, SA-4, SI-7, SR-9, SR-10

**Assessment Objectives:**
- sr-11_obj.a
- sr-11_obj.b counterfeit system components are reported to {{ insert: param, sr-11_odp.01 }}.

---

## SR-12: Component Disposal
Dispose of {{ insert: param, sr-12_odp.01 }} using the following techniques and methods: {{ insert: param, sr-12_odp.02 }}.

**Guidance:** Data, documentation, tools, or system components can be disposed of at any time during the system development life cycle (not only in the disposal or retirement phase of the life cycle). For example, disposal can occur during research and development, design, prototyping, or operations/maintenance a

**Related:** MP-6
