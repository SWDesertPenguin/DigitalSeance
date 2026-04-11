# NIST 800-53: CP — Contingency Planning

## CP-1: Policy and Procedures
(cp-1_smt.a) Develop, document, and disseminate to {{ insert: param, cp-1_prm_1 }}:
    (cp-1_smt.a.1) {{ insert: param, cp-01_odp.03 }} contingency planning policy that:
      (cp-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (cp-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (cp-1_smt.a.2) Proced

**Guidance:** Contingency planning policy and procedures address the controls in the CP family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy assuran

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- cp-1_obj.a
- cp-1_obj.b the {{ insert: param, cp-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the contingency planning policy and procedures;
- cp-1_obj.c

---

## CP-2: Contingency Plan
(cp-2_smt.a) Develop a contingency plan for the system that:
    (cp-2_smt.a.1) Identifies essential mission and business functions and associated contingency requirements;
    (cp-2_smt.a.2) Provides recovery objectives, restoration priorities, and metrics;
    (cp-2_smt.a.3) Addresses contingency roles, responsibilities, assigned individuals with contact information;
    (cp-2_smt.a.4) Addresses maintaining essential mission and business functions despite a system disruption, compromise, or fa

**Guidance:** Contingency planning for systems is part of an overall program for achieving continuity of operations for organizational mission and business functions. Contingency planning addresses system restoration and implementation of alternative mission or business processes when systems are compromised or b

**Related:** CP-3, CP-4, CP-6, CP-7, CP-8, CP-9, CP-10, CP-11, CP-13, IR-4, IR-6, IR-8, IR-9, MA-6, MP-2, MP-4, MP-5, PL-2, PM-8, PM-11, SA-15, SA-20, SC-7, SC-23, SI-12

**Assessment Objectives:**
- cp-2_obj.a
- cp-2_obj.b
- cp-2_obj.c contingency planning activities are coordinated with incident handling activities;
- cp-2_obj.d the contingency plan for the system is reviewed {{ insert: param, cp-02_odp.05 }};
- cp-2_obj.e
- cp-2_obj.f
- cp-2_obj.g
- cp-2_obj.h

---

## CP-3: Contingency Training
(cp-3_smt.a) Provide contingency training to system users consistent with assigned roles and responsibilities:
    (cp-3_smt.a.1) Within {{ insert: param, cp-03_odp.01 }} of assuming a contingency role or responsibility;
    (cp-3_smt.a.2) When required by system changes; and
    (cp-3_smt.a.3) {{ insert: param, cp-03_odp.02 }} thereafter; and
  (cp-3_smt.b) Review and update contingency training content {{ insert: param, cp-03_odp.03 }} and following {{ insert: param, cp-03_odp.04 }}.

**Guidance:** Contingency training provided by organizations is linked to the assigned roles and responsibilities of organizational personnel to ensure that the appropriate content and level of detail is included in such training. For example, some individuals may only need to know when and where to report for du

**Related:** AT-2, AT-3, AT-4, CP-2, CP-4, CP-8, IR-2, IR-4, IR-9

**Assessment Objectives:**
- cp-3_obj.a
- cp-3_obj.b

---

## CP-4: Contingency Plan Testing
(cp-4_smt.a) Test the contingency plan for the system {{ insert: param, cp-04_odp.01 }} using the following tests to determine the effectiveness of the plan and the readiness to execute the plan: {{ insert: param, cp-4_prm_2 }}.
  (cp-4_smt.b) Review the contingency plan test results; and
  (cp-4_smt.c) Initiate corrective actions, if needed.

**Guidance:** Methods for testing contingency plans to determine the effectiveness of the plans and identify potential weaknesses include checklists, walk-through and tabletop exercises, simulations (parallel or full interrupt), and comprehensive exercises. Organizations conduct testing based on the requirements

**Related:** AT-3, CP-2, CP-3, CP-8, CP-9, IR-3, IR-4, PL-2, PM-14, SR-2

**Assessment Objectives:**
- cp-4_obj.a
- cp-4_obj.b the contingency plan test results are reviewed;
- cp-4_obj.c corrective actions are initiated, if needed.

---

## CP-6: Alternate Storage Site
(cp-6_smt.a) Establish an alternate storage site, including necessary agreements to permit the storage and retrieval of system backup information; and
  (cp-6_smt.b) Ensure that the alternate storage site provides controls equivalent to that of the primary site.

**Guidance:** Alternate storage sites are geographically distinct from primary storage sites and maintain duplicate copies of information and data if the primary storage site is not available. Similarly, alternate processing sites provide processing capability if the primary processing site is not available. Geog

**Related:** CP-2, CP-7, CP-8, CP-9, CP-10, MP-4, MP-5, PE-3, SC-36, SI-13

**Assessment Objectives:**
- cp-6_obj.a
- cp-6_obj.b the alternate storage site provides controls equivalent to that of the primary site.

---

## CP-7: Alternate Processing Site
(cp-7_smt.a) Establish an alternate processing site, including necessary agreements to permit the transfer and resumption of {{ insert: param, cp-07_odp.01 }} for essential mission and business functions within {{ insert: param, cp-07_odp.02 }} when the primary processing capabilities are unavailable;
  (cp-7_smt.b) Make available at the alternate processing site, the equipment and supplies required to transfer and resume operations or put contracts in place to support delivery to the site withi

**Guidance:** Alternate processing sites are geographically distinct from primary processing sites and provide processing capability if the primary processing site is not available. The alternate processing capability may be addressed using a physical processing site or other alternatives, such as failover to a c

**Related:** CP-2, CP-6, CP-8, CP-9, CP-10, MA-6, PE-3, PE-11, PE-12, PE-17, SC-36, SI-13

**Assessment Objectives:**
- cp-7_obj.a an alternate processing site, including necessary agreements to permit the transfer and resumption of {{ insert: param, cp-07_odp.01 }} for essential mission and business functions, is established within {{ insert: param, cp-07_odp.02 }} when the primary processing capabilities are unavailable;
- cp-7_obj.b
- cp-7_obj.c controls provided at the alternate processing site are equivalent to those at the primary site.

---

## CP-8: Telecommunications Services
Establish alternate telecommunications services, including necessary agreements to permit the resumption of {{ insert: param, cp-08_odp.01 }} for essential mission and business functions within {{ insert: param, cp-08_odp.02 }} when the primary telecommunications capabilities are unavailable at either the primary or alternate processing or storage sites.

**Guidance:** Telecommunications services (for data and voice) for primary and alternate processing and storage sites are in scope for [CP-8](#cp-8) . Alternate telecommunications services reflect the continuity requirements in contingency plans to maintain essential mission and business functions despite the los

**Related:** CP-2, CP-6, CP-7, CP-11, SC-7

---

## CP-9: System Backup
(cp-9_smt.a) Conduct backups of user-level information contained in {{ insert: param, cp-09_odp.01 }} {{ insert: param, cp-09_odp.02 }};
  (cp-9_smt.b) Conduct backups of system-level information contained in the system {{ insert: param, cp-09_odp.03 }};
  (cp-9_smt.c) Conduct backups of system documentation, including security- and privacy-related documentation {{ insert: param, cp-09_odp.04 }} ; and
  (cp-9_smt.d) Protect the confidentiality, integrity, and availability of backup information.

**Guidance:** System-level information includes system state information, operating system software, middleware, application software, and licenses. User-level information includes information other than system-level information. Mechanisms employed to protect the integrity of system backups include digital signa

**Related:** CP-2, CP-6, CP-10, MP-4, MP-5, SC-8, SC-12, SC-13, SI-4, SI-13

**Assessment Objectives:**
- cp-9_obj.a backups of user-level information contained in {{ insert: param, cp-09_odp.01 }} are conducted {{ insert: param, cp-09_odp.02 }};
- cp-9_obj.b backups of system-level information contained in the system are conducted {{ insert: param, cp-09_odp.03 }};
- cp-9_obj.c backups of system documentation, including security- and privacy-related documentation are conducted {{ insert: param, cp-09_odp.04 }};
- cp-9_obj.d

---

## CP-10: System Recovery and Reconstitution
Provide for the recovery and reconstitution of the system to a known state within {{ insert: param, cp-10_prm_1 }} after a disruption, compromise, or failure.

**Guidance:** Recovery is executing contingency plan activities to restore organizational mission and business functions. Reconstitution takes place following recovery and includes activities for returning systems to fully operational states. Recovery and reconstitution operations reflect mission and business pri

**Related:** CP-2, CP-4, CP-6, CP-7, CP-9, IR-4, SA-8, SC-24, SI-13

**Assessment Objectives:**
- cp-10_obj-1 the recovery of the system to a known state is provided within {{ insert: param, cp-10_odp.01 }} after a disruption, compromise, or failure;
- cp-10_obj-2 a reconstitution of the system to a known state is provided within {{ insert: param, cp-10_odp.02 }} after a disruption, compromise, or failure.

---

## CP-11: Alternate Communications Protocols
Provide the capability to employ {{ insert: param, cp-11_odp }} in support of maintaining continuity of operations.

**Guidance:** Contingency plans and the contingency training or testing associated with those plans incorporate an alternate communications protocol capability as part of establishing resilience in organizational systems. Switching communications protocols may affect software applications and operational aspects

**Related:** CP-2, CP-8, CP-13

---

## CP-12: Safe Mode
When {{ insert: param, cp-12_odp.02 }} are detected, enter a safe mode of operation with {{ insert: param, cp-12_odp.01 }}.

**Guidance:** For systems that support critical mission and business functions—including military operations, civilian space operations, nuclear power plant operations, and air traffic control operations (especially real-time operational environments)—organizations can identify certain conditions under which thos

**Related:** CM-2, SA-8, SC-24, SI-13, SI-17

---

## CP-13: Alternative Security Mechanisms
Employ {{ insert: param, cp-13_odp.01 }} for satisfying {{ insert: param, cp-13_odp.02 }} when the primary means of implementing the security function is unavailable or compromised.

**Guidance:** Use of alternative security mechanisms supports system resiliency, contingency planning, and continuity of operations. To ensure mission and business continuity, organizations can implement alternative or supplemental security mechanisms. The mechanisms may be less effective than the primary mechani

**Related:** CP-2, CP-11, SI-13
