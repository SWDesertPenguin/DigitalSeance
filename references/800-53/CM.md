# NIST 800-53: CM — Configuration Management

## CM-1: Policy and Procedures
(cm-1_smt.a) Develop, document, and disseminate to {{ insert: param, cm-1_prm_1 }}:
    (cm-1_smt.a.1) {{ insert: param, cm-01_odp.03 }} configuration management policy that:
      (cm-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (cm-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (cm-1_smt.a.2) Pr

**Guidance:** Configuration management policy and procedures address the controls in the CM family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy ass

**Related:** PM-9, PS-8, SA-8, SI-12

**Assessment Objectives:**
- cm-1_obj.a
- cm-1_obj.b the {{ insert: param, cm-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the configuration management policy and procedures;
- cm-1_obj.c

---

## CM-2: Baseline Configuration
(cm-2_smt.a) Develop, document, and maintain under configuration control, a current baseline configuration of the system; and
  (cm-2_smt.b) Review and update the baseline configuration of the system:
    (cm-2_smt.b.1) {{ insert: param, cm-02_odp.01 }};
    (cm-2_smt.b.2) When required due to {{ insert: param, cm-02_odp.02 }} ; and
    (cm-2_smt.b.3) When system components are installed or upgraded.

**Guidance:** Baseline configurations for systems and system components include connectivity, operational, and communications aspects of systems. Baseline configurations are documented, formally reviewed, and agreed-upon specifications for systems or configuration items within those systems. Baseline configuratio

**Related:** AC-19, AU-6, CA-9, CM-1, CM-3, CM-5, CM-6, CM-8, CM-9, CP-9, CP-10, CP-12, MA-2, PL-8, PM-5, SA-8, SA-10, SA-15, SC-18

**Assessment Objectives:**
- cm-2_obj.a
- cm-2_obj.b

---

## CM-3: Configuration Change Control
(cm-3_smt.a) Determine and document the types of changes to the system that are configuration-controlled;
  (cm-3_smt.b) Review proposed configuration-controlled changes to the system and approve or disapprove such changes with explicit consideration for security and privacy impact analyses;
  (cm-3_smt.c) Document configuration change decisions associated with the system;
  (cm-3_smt.d) Implement approved configuration-controlled changes to the system;
  (cm-3_smt.e) Retain records of configura

**Guidance:** Configuration change control for organizational systems involves the systematic proposal, justification, implementation, testing, review, and disposition of system changes, including system upgrades and modifications. Configuration change control includes changes to baseline configurations, configur

**Related:** CA-7, CM-2, CM-4, CM-5, CM-6, CM-9, CM-11, IA-3, MA-2, PE-16, PT-6, RA-8, SA-8, SA-10, SC-28, SC-34, SC-37, SI-2, SI-3, SI-4, SI-7, SI-10, SR-11

**Assessment Objectives:**
- cm-3_obj.a the types of changes to the system that are configuration-controlled are determined and documented;
- cm-3_obj.b
- cm-3_obj.c configuration change decisions associated with the system are documented;
- cm-3_obj.d approved configuration-controlled changes to the system are implemented;
- cm-3_obj.e records of configuration-controlled changes to the system are retained for {{ insert: param, cm-03_odp.01 }};
- cm-3_obj.f
- cm-3_obj.g

---

## CM-4: Impact Analyses
Analyze changes to the system to determine potential security and privacy impacts prior to change implementation.

**Guidance:** Organizational personnel with security or privacy responsibilities conduct impact analyses. Individuals conducting impact analyses possess the necessary skills and technical expertise to analyze the changes to systems as well as the security or privacy ramifications. Impact analyses include reviewin

**Related:** CA-7, CM-3, CM-8, CM-9, MA-2, RA-3, RA-5, RA-8, SA-5, SA-8, SA-10, SI-2

**Assessment Objectives:**
- cm-4_obj-1 changes to the system are analyzed to determine potential security impacts prior to change implementation;
- cm-4_obj-2 changes to the system are analyzed to determine potential privacy impacts prior to change implementation.

---

## CM-5: Access Restrictions for Change
Define, document, approve, and enforce physical and logical access restrictions associated with changes to the system.

**Guidance:** Changes to the hardware, software, or firmware components of systems or the operational procedures related to the system can potentially have significant effects on the security of the systems or individuals’ privacy. Therefore, organizations permit only qualified and authorized individuals to acces

**Related:** AC-3, AC-5, AC-6, CM-9, PE-3, SC-28, SC-34, SC-37, SI-2, SI-10

**Assessment Objectives:**
- cm-5_obj-1 physical access restrictions associated with changes to the system are defined and documented;
- cm-5_obj-2 physical access restrictions associated with changes to the system are approved;
- cm-5_obj-3 physical access restrictions associated with changes to the system are enforced;
- cm-5_obj-4 logical access restrictions associated with changes to the system are defined and documented;
- cm-5_obj-5 logical access restrictions associated with changes to the system are approved;
- cm-5_obj-6 logical access restrictions associated with changes to the system are enforced.

---

## CM-6: Configuration Settings
(cm-6_smt.a) Establish and document configuration settings for components employed within the system that reflect the most restrictive mode consistent with operational requirements using {{ insert: param, cm-06_odp.01 }};
  (cm-6_smt.b) Implement the configuration settings;
  (cm-6_smt.c) Identify, document, and approve any deviations from established configuration settings for {{ insert: param, cm-06_odp.02 }} based on {{ insert: param, cm-06_odp.03 }} ; and
  (cm-6_smt.d) Monitor and control c

**Guidance:** Configuration settings are the parameters that can be changed in the hardware, software, or firmware components of the system that affect the security and privacy posture or functionality of the system. Information technology products for which configuration settings can be defined include mainframe

**Related:** AC-3, AC-19, AU-2, AU-6, CA-9, CM-2, CM-3, CM-5, CM-7, CM-11, CP-7, CP-9, CP-10, IA-3, IA-5, PL-8, PL-9, RA-5, SA-4, SA-5, SA-8, SA-9, SC-18, SC-28, SC-43, SI-2, SI-4, SI-6

**Assessment Objectives:**
- cm-6_obj.a configuration settings that reflect the most restrictive mode consistent with operational requirements are established and documented for components employed within the system using {{ insert: param, cm-06_odp.01 }};
- cm-6_obj.b the configuration settings documented in CM-06a are implemented;
- cm-6_obj.c
- cm-6_obj.d

---

## CM-7: Least Functionality
(cm-7_smt.a) Configure the system to provide only {{ insert: param, cm-07_odp.01 }} ; and
  (cm-7_smt.b) Prohibit or restrict the use of the following functions, ports, protocols, software, and/or services: {{ insert: param, cm-7_prm_2 }}.

**Guidance:** Systems provide a wide variety of functions and services. Some of the functions and services routinely provided by default may not be necessary to support essential organizational missions, functions, or operations. Additionally, it is sometimes convenient to provide multiple services from a single

**Related:** AC-3, AC-4, CM-2, CM-5, CM-6, CM-11, RA-5, SA-4, SA-5, SA-8, SA-9, SA-15, SC-2, SC-3, SC-7, SC-37, SI-4

**Assessment Objectives:**
- cm-7_obj.a the system is configured to provide only {{ insert: param, cm-07_odp.01 }};
- cm-7_obj.b

---

## CM-8: System Component Inventory
(cm-8_smt.a) Develop and document an inventory of system components that:
    (cm-8_smt.a.1) Accurately reflects the system;
    (cm-8_smt.a.2) Includes all components within the system;
    (cm-8_smt.a.3) Does not include duplicate accounting of components or components assigned to any other system;
    (cm-8_smt.a.4) Is at the level of granularity deemed necessary for tracking and reporting; and
    (cm-8_smt.a.5) Includes the following information to achieve system component accountability: {

**Guidance:** System components are discrete, identifiable information technology assets that include hardware, software, and firmware. Organizations may choose to implement centralized system component inventories that include components from all organizational systems. In such situations, organizations ensure t

**Related:** CM-2, CM-7, CM-9, CM-10, CM-11, CM-13, CP-2, CP-9, MA-2, MA-6, PE-20, PL-9, PM-5, SA-4, SA-5, SI-2, SR-4

**Assessment Objectives:**
- cm-8_obj.a
- cm-8_obj.b the system component inventory is reviewed and updated {{ insert: param, cm-08_odp.02 }}.

---

## CM-9: Configuration Management Plan
Develop, document, and implement a configuration management plan for the system that:
  (cm-9_smt.a) Addresses roles, responsibilities, and configuration management processes and procedures;
  (cm-9_smt.b) Establishes a process for identifying configuration items throughout the system development life cycle and for managing the configuration of the configuration items;
  (cm-9_smt.c) Defines the configuration items for the system and places the configuration items under configuration management;

**Guidance:** Configuration management activities occur throughout the system development life cycle. As such, there are developmental configuration management activities (e.g., the control of code and software libraries) and operational configuration management activities (e.g., control of installed components a

**Related:** CM-2, CM-3, CM-4, CM-5, CM-8, PL-2, RA-8, SA-10, SI-12

**Assessment Objectives:**
- cm-9_obj-1 a configuration management plan for the system is developed and documented;
- cm-9_obj-2 a configuration management plan for the system is implemented;
- cm-9_obj.a
- cm-9_obj.b
- cm-9_obj.c
- cm-9_obj.d the configuration management plan is reviewed and approved by {{ insert: param, cm-09_odp }};
- cm-9_obj.e

---

## CM-10: Software Usage Restrictions
(cm-10_smt.a) Use software and associated documentation in accordance with contract agreements and copyright laws;
  (cm-10_smt.b) Track the use of software and associated documentation protected by quantity licenses to control copying and distribution; and
  (cm-10_smt.c) Control and document the use of peer-to-peer file sharing technology to ensure that this capability is not used for the unauthorized distribution, display, performance, or reproduction of copyrighted work.

**Guidance:** Software license tracking can be accomplished by manual or automated methods, depending on organizational needs. Examples of contract agreements include software license agreements and non-disclosure agreements.

**Related:** AC-17, AU-6, CM-7, CM-8, PM-30, SC-7

**Assessment Objectives:**
- cm-10_obj.a software and associated documentation are used in accordance with contract agreements and copyright laws;
- cm-10_obj.b the use of software and associated documentation protected by quantity licenses is tracked to control copying and distribution;
- cm-10_obj.c the use of peer-to-peer file sharing technology is controlled and documented to ensure that peer-to-peer file sharing is not used for the unauthorized distribution, display, performance, or reproduction of copyrighted work.

---

## CM-11: User-installed Software
(cm-11_smt.a) Establish {{ insert: param, cm-11_odp.01 }} governing the installation of software by users;
  (cm-11_smt.b) Enforce software installation policies through the following methods: {{ insert: param, cm-11_odp.02 }} ; and
  (cm-11_smt.c) Monitor policy compliance {{ insert: param, cm-11_odp.03 }}.

**Guidance:** If provided the necessary privileges, users can install software in organizational systems. To maintain control over the software installed, organizations identify permitted and prohibited actions regarding software installation. Permitted software installations include updates and security patches

**Related:** AC-3, AU-6, CM-2, CM-3, CM-5, CM-6, CM-7, CM-8, PL-4, SI-4, SI-7

**Assessment Objectives:**
- cm-11_obj.a {{ insert: param, cm-11_odp.01 }} governing the installation of software by users are established;
- cm-11_obj.b software installation policies are enforced through {{ insert: param, cm-11_odp.02 }};
- cm-11_obj.c compliance with {{ insert: param, cm-11_odp.01 }} is monitored {{ insert: param, cm-11_odp.03 }}.

---

## CM-12: Information Location
(cm-12_smt.a) Identify and document the location of {{ insert: param, cm-12_odp }} and the specific system components on which the information is processed and stored;
  (cm-12_smt.b) Identify and document the users who have access to the system and system components where the information is processed and stored; and
  (cm-12_smt.c) Document changes to the location (i.e., system or system components) where the information is processed and stored.

**Guidance:** Information location addresses the need to understand where information is being processed and stored. Information location includes identifying where specific information types and information reside in system components and how information is being processed so that information flow can be underst

**Related:** AC-2, AC-3, AC-4, AC-6, AC-23, CM-8, PM-5, RA-2, SA-4, SA-8, SA-17, SC-4, SC-16, SC-28, SI-4, SI-7

**Assessment Objectives:**
- cm-12_obj.a
- cm-12_obj.b
- cm-12_obj.c

---

## CM-13: Data Action Mapping
Develop and document a map of system data actions.

**Guidance:** Data actions are system operations that process personally identifiable information. The processing of such information encompasses the full information life cycle, which includes collection, generation, transformation, use, disclosure, retention, and disposal. A map of system data actions includes

**Related:** AC-3, CM-4, CM-12, PM-5, PM-27, PT-2, PT-3, RA-3, RA-8

---

## CM-14: Signed Components
Prevent the installation of {{ insert: param, cm-14_prm_1 }} without verification that the component has been digitally signed using a certificate that is recognized and approved by the organization.

**Guidance:** Software and firmware components prevented from installation unless signed with recognized and approved certificates include software and firmware version updates, patches, service packs, device drivers, and basic input/output system updates. Organizations can identify applicable software and firmwa

**Related:** CM-7, SC-12, SC-13, SI-7

**Assessment Objectives:**
- cm-14_obj-1 the installation of {{ insert: param, cm-14_odp.01 }} is prevented unless it is verified that the software has been digitally signed using a certificate recognized and approved by the organization;
- cm-14_obj-2 the installation of {{ insert: param, cm-14_odp.02 }} is prevented unless it is verified that the firmware has been digitally signed using a certificate recognized and approved by the organization.
