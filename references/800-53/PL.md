# NIST 800-53: PL — Planning

## PL-1: Policy and Procedures
(pl-1_smt.a) Develop, document, and disseminate to {{ insert: param, pl-1_prm_1 }}:
    (pl-1_smt.a.1) {{ insert: param, pl-01_odp.03 }} planning policy that:
      (pl-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (pl-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (pl-1_smt.a.2) Procedures to faci

**Guidance:** Planning policy and procedures for the controls in the PL family implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assurance. Therefore, it is impo

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- pl-1_obj.a
- pl-1_obj.b the {{ insert: param, pl-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the planning policy and procedures;
- pl-1_obj.c

---

## PL-2: System Security and Privacy Plans
(pl-2_smt.a) Develop security and privacy plans for the system that:
    (pl-2_smt.a.1) Are consistent with the organization’s enterprise architecture;
    (pl-2_smt.a.2) Explicitly define the constituent system components;
    (pl-2_smt.a.3) Describe the operational context of the system in terms of mission and business processes;
    (pl-2_smt.a.4) Identify the individuals that fulfill system roles and responsibilities;
    (pl-2_smt.a.5) Identify the information types processed, stored, and t

**Guidance:** System security and privacy plans are scoped to the system and system components within the defined authorization boundary and contain an overview of the security and privacy requirements for the system and the controls selected to satisfy the requirements. The plans describe the intended applicatio

**Related:** AC-2, AC-6, AC-14, AC-17, AC-20, CA-2, CA-3, CA-7, CM-9, CM-13, CP-2, CP-4, IR-4, IR-8, MA-4, MA-5, MP-4, MP-5, PL-7, PL-8, PL-10, PL-11, PM-1, PM-7, PM-8, PM-9, PM-10, PM-11, RA-3, RA-8, RA-9, SA-5, SA-17, SA-22, SI-12, SR-2, SR-4

**Assessment Objectives:**
- pl-2_obj.a
- pl-2_obj.b
- pl-2_obj.c plans are reviewed {{ insert: param, pl-02_odp.03 }};
- pl-2_obj.d
- pl-2_obj.e

---

## PL-4: Rules of Behavior
(pl-4_smt.a) Establish and provide to individuals requiring access to the system, the rules that describe their responsibilities and expected behavior for information and system usage, security, and privacy;
  (pl-4_smt.b) Receive a documented acknowledgment from such individuals, indicating that they have read, understand, and agree to abide by the rules of behavior, before authorizing access to information and the system;
  (pl-4_smt.c) Review and update the rules of behavior {{ insert: param,

**Guidance:** Rules of behavior represent a type of access agreement for organizational users. Other types of access agreements include nondisclosure agreements, conflict-of-interest agreements, and acceptable use agreements (see [PS-6](#ps-6) ). Organizations consider rules of behavior based on individual user r

**Related:** AC-2, AC-6, AC-8, AC-9, AC-17, AC-18, AC-19, AC-20, AT-2, AT-3, CM-11, IA-2, IA-4, IA-5, MP-7, PS-6, PS-8, SA-5, SI-12

**Assessment Objectives:**
- pl-4_obj.a
- pl-4_obj.b before authorizing access to information and the system, a documented acknowledgement from such individuals indicating that they have read, understand, and agree to abide by the rules of behavior is received;
- pl-4_obj.c rules of behavior are reviewed and updated {{ insert: param, pl-04_odp.01 }};
- pl-4_obj.d individuals who have acknowledged a previous version of the rules of behavior are required to read and reacknowledge {{ insert: param, pl-04_odp.02 }}.

---

## PL-7: Concept of Operations
(pl-7_smt.a) Develop a Concept of Operations (CONOPS) for the system describing how the organization intends to operate the system from the perspective of information security and privacy; and
  (pl-7_smt.b) Review and update the CONOPS {{ insert: param, pl-07_odp }}.

**Guidance:** The CONOPS may be included in the security or privacy plans for the system or in other system development life cycle documents. The CONOPS is a living document that requires updating throughout the system development life cycle. For example, during system design reviews, the concept of operations is

**Related:** PL-2, SA-2, SI-12

**Assessment Objectives:**
- pl-7_obj.a a CONOPS for the system describing how the organization intends to operate the system from the perspective of information security and privacy is developed;
- pl-7_obj.b the CONOPS is reviewed and updated {{ insert: param, pl-07_odp }}.

---

## PL-8: Security and Privacy Architectures
(pl-8_smt.a) Develop security and privacy architectures for the system that:
    (pl-8_smt.a.1) Describe the requirements and approach to be taken for protecting the confidentiality, integrity, and availability of organizational information;
    (pl-8_smt.a.2) Describe the requirements and approach to be taken for processing personally identifiable information to minimize privacy risk to individuals;
    (pl-8_smt.a.3) Describe how the architectures are integrated into and support the enterprise

**Guidance:** The security and privacy architectures at the system level are consistent with the organization-wide security and privacy architectures described in [PM-7](#pm-7) , which are integral to and developed as part of the enterprise architecture. The architectures include an architectural description, the

**Related:** CM-2, CM-6, PL-2, PL-7, PL-9, PM-5, PM-7, RA-9, SA-3, SA-5, SA-8, SA-17, SC-7

**Assessment Objectives:**
- pl-8_obj.a
- pl-8_obj.b changes in the enterprise architecture are reviewed and updated {{ insert: param, pl-08_odp }} to reflect changes in the enterprise architecture;
- pl-8_obj.c

---

## PL-9: Central Management
Centrally manage {{ insert: param, pl-09_odp }}.

**Guidance:** Central management refers to organization-wide management and implementation of selected controls and processes. This includes planning, implementing, assessing, authorizing, and monitoring the organization-defined, centrally managed controls and processes. As the central management of controls is g

**Related:** PL-8, PM-9

---

## PL-10: Baseline Selection
Select a control baseline for the system.

**Guidance:** Control baselines are predefined sets of controls specifically assembled to address the protection needs of a group, organization, or community of interest. Controls are chosen for baselines to either satisfy mandates imposed by laws, executive orders, directives, regulations, policies, standards, a

**Related:** PL-2, PL-11, RA-2, RA-3, SA-8

---

## PL-11: Baseline Tailoring
Tailor the selected control baseline by applying specified tailoring actions.

**Guidance:** The concept of tailoring allows organizations to specialize or customize a set of baseline controls by applying a defined set of tailoring actions. Tailoring actions facilitate such specialization and customization by allowing organizations to develop security and privacy plans that reflect their sp

**Related:** PL-10, RA-2, RA-3, RA-9, SA-8
