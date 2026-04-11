# NIST 800-53: AU — Audit and Accountability

## AU-1: Policy and Procedures
(au-1_smt.a) Develop, document, and disseminate to {{ insert: param, au-1_prm_1 }}:
    (au-1_smt.a.1) {{ insert: param, au-01_odp.03 }} audit and accountability policy that:
      (au-1_smt.a.1.a) Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and
      (au-1_smt.a.1.b) Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and
    (au-1_smt.a.2) Pr

**Guidance:** Audit and accountability policy and procedures address the controls in the AU family that are implemented within systems and organizations. The risk management strategy is an important factor in establishing such policies and procedures. Policies and procedures contribute to security and privacy ass

**Related:** PM-9, PS-8, SI-12

**Assessment Objectives:**
- au-1_obj.a
- au-1_obj.b the {{ insert: param, au-01_odp.04 }} is designated to manage the development, documentation, and dissemination of the audit and accountability policy and procedures;
- au-1_obj.c

---

## AU-2: Event Logging
(au-2_smt.a) Identify the types of events that the system is capable of logging in support of the audit function: {{ insert: param, au-02_odp.01 }};
  (au-2_smt.b) Coordinate the event logging function with other organizational entities requiring audit-related information to guide and inform the selection criteria for events to be logged;
  (au-2_smt.c) Specify the following event types for logging within the system: {{ insert: param, au-2_prm_2 }};
  (au-2_smt.d) Provide a rationale for why the

**Guidance:** An event is an observable occurrence in a system. The types of events that require logging are those events that are significant and relevant to the security of systems and the privacy of individuals. Event logging also supports specific monitoring and auditing needs. Event types include password ch

**Related:** AC-2, AC-3, AC-6, AC-7, AC-8, AC-16, AC-17, AU-3, AU-4, AU-5, AU-6, AU-7, AU-11, AU-12, CM-3, CM-5, CM-6, CM-13, IA-3, MA-4, MP-4, PE-3, PM-21, PT-2, PT-7, RA-8, SA-8, SC-7, SC-18, SI-3, SI-4, SI-7, SI-10, SI-11

**Assessment Objectives:**
- au-2_obj.a {{ insert: param, au-02_odp.01 }} that the system is capable of logging are identified in support of the audit logging function;
- au-2_obj.b the event logging function is coordinated with other organizational entities requiring audit-related information to guide and inform the selection criteria for events to be logged;
- au-2_obj.c
- au-2_obj.d a rationale is provided for why the event types selected for logging are deemed to be adequate to support after-the-fact investigations of incidents;
- au-2_obj.e the event types selected for logging are reviewed and updated {{ insert: param, au-02_odp.04 }}.

---

## AU-3: Content of Audit Records
Ensure that audit records contain information that establishes the following:
  (au-3_smt.a) What type of event occurred;
  (au-3_smt.b) When the event occurred;
  (au-3_smt.c) Where the event occurred;
  (au-3_smt.d) Source of the event;
  (au-3_smt.e) Outcome of the event; and
  (au-3_smt.f) Identity of any individuals, subjects, or objects/entities associated with the event.

**Guidance:** Audit record content that may be necessary to support the auditing function includes event descriptions (item a), time stamps (item b), source and destination addresses (item c), user or process identifiers (items d and f), success or fail indications (item e), and filenames involved (items a, c, e,

**Related:** AU-2, AU-8, AU-12, AU-14, MA-4, PL-9, SA-8, SI-7, SI-11

**Assessment Objectives:**
- au-3_obj.a audit records contain information that establishes what type of event occurred;
- au-3_obj.b audit records contain information that establishes when the event occurred;
- au-3_obj.c audit records contain information that establishes where the event occurred;
- au-3_obj.d audit records contain information that establishes the source of the event;
- au-3_obj.e audit records contain information that establishes the outcome of the event;
- au-3_obj.f audit records contain information that establishes the identity of any individuals, subjects, or objects/entities associated with the event.

---

## AU-4: Audit Log Storage Capacity
Allocate audit log storage capacity to accommodate {{ insert: param, au-04_odp }}.

**Guidance:** Organizations consider the types of audit logging to be performed and the audit log processing requirements when allocating audit log storage capacity. Allocating sufficient audit log storage capacity reduces the likelihood of such capacity being exceeded and resulting in the potential loss or reduc

**Related:** AU-2, AU-5, AU-6, AU-7, AU-9, AU-11, AU-12, AU-14, SI-4

---

## AU-5: Response to Audit Logging Process Failures
(au-5_smt.a) Alert {{ insert: param, au-05_odp.01 }} within {{ insert: param, au-05_odp.02 }} in the event of an audit logging process failure; and
  (au-5_smt.b) Take the following additional actions: {{ insert: param, au-05_odp.03 }}.

**Guidance:** Audit logging process failures include software and hardware errors, failures in audit log capturing mechanisms, and reaching or exceeding audit log storage capacity. Organization-defined actions include overwriting oldest audit records, shutting down the system, and stopping the generation of audit

**Related:** AU-2, AU-4, AU-7, AU-9, AU-11, AU-12, AU-14, SI-4, SI-12

**Assessment Objectives:**
- au-5_obj.a {{ insert: param, au-05_odp.01 }} are alerted in the event of an audit logging process failure within {{ insert: param, au-05_odp.02 }};
- au-5_obj.b {{ insert: param, au-05_odp.03 }} are taken in the event of an audit logging process failure.

---

## AU-6: Audit Record Review, Analysis, and Reporting
(au-6_smt.a) Review and analyze system audit records {{ insert: param, au-06_odp.01 }} for indications of {{ insert: param, au-06_odp.02 }} and the potential impact of the inappropriate or unusual activity;
  (au-6_smt.b) Report findings to {{ insert: param, au-06_odp.03 }} ; and
  (au-6_smt.c) Adjust the level of audit record review, analysis, and reporting within the system when there is a change in risk based on law enforcement information, intelligence information, or other credible sources

**Guidance:** Audit record review, analysis, and reporting covers information security- and privacy-related logging performed by organizations, including logging that results from the monitoring of account usage, remote access, wireless connectivity, mobile device connection, configuration settings, system compon

**Related:** AC-2, AC-3, AC-5, AC-6, AC-7, AC-17, AU-7, AU-16, CA-2, CA-7, CM-2, CM-5, CM-6, CM-10, CM-11, IA-2, IA-3, IA-5, IA-8, IR-5, MA-4, MP-4, PE-3, PE-6, RA-5, SA-8, SC-7, SI-3, SI-4, SI-7

**Assessment Objectives:**
- au-6_obj.a system audit records are reviewed and analyzed {{ insert: param, au-06_odp.01 }} for indications of {{ insert: param, au-06_odp.02 }} and the potential impact of the inappropriate or unusual activity;
- au-6_obj.b findings are reported to {{ insert: param, au-06_odp.03 }};
- au-6_obj.c the level of audit record review, analysis, and reporting within the system is adjusted when there is a change in risk based on law enforcement information, intelligence information, or other credible sources of information.

---

## AU-7: Audit Record Reduction and Report Generation
Provide and implement an audit record reduction and report generation capability that:
  (au-7_smt.a) Supports on-demand audit record review, analysis, and reporting requirements and after-the-fact investigations of incidents; and
  (au-7_smt.b) Does not alter the original content or time ordering of audit records.

**Guidance:** Audit record reduction is a process that manipulates collected audit log information and organizes it into a summary format that is more meaningful to analysts. Audit record reduction and report generation capabilities do not always emanate from the same system or from the same organizational entiti

**Related:** AC-2, AU-2, AU-3, AU-4, AU-5, AU-6, AU-12, AU-16, CM-5, IA-5, IR-4, PM-12, SI-4

**Assessment Objectives:**
- au-7_obj.a
- au-7_obj.b

---

## AU-8: Time Stamps
(au-8_smt.a) Use internal system clocks to generate time stamps for audit records; and
  (au-8_smt.b) Record time stamps for audit records that meet {{ insert: param, au-08_odp }} and that use Coordinated Universal Time, have a fixed local time offset from Coordinated Universal Time, or that include the local time offset as part of the time stamp.

**Guidance:** Time stamps generated by the system include date and time. Time is commonly expressed in Coordinated Universal Time (UTC), a modern continuation of Greenwich Mean Time (GMT), or local time with an offset from UTC. Granularity of time measurements refers to the degree of synchronization between syste

**Related:** AU-3, AU-12, AU-14, SC-45

**Assessment Objectives:**
- au-8_obj.a internal system clocks are used to generate timestamps for audit records;
- au-8_obj.b timestamps are recorded for audit records that meet {{ insert: param, au-08_odp }} and that use Coordinated Universal Time, have a fixed local time offset from Coordinated Universal Time, or include the local time offset as part of the timestamp.

---

## AU-9: Protection of Audit Information
(au-9_smt.a) Protect audit information and audit logging tools from unauthorized access, modification, and deletion; and
  (au-9_smt.b) Alert {{ insert: param, au-09_odp }} upon detection of unauthorized access, modification, or deletion of audit information.

**Guidance:** Audit information includes all information needed to successfully audit system activity, such as audit records, audit log settings, audit reports, and personally identifiable information. Audit logging tools are those programs and devices used to conduct system audit and logging activities. Protecti

**Related:** AC-3, AC-6, AU-6, AU-11, AU-14, AU-15, MP-2, MP-4, PE-2, PE-3, PE-6, SA-8, SC-8, SI-4

**Assessment Objectives:**
- au-9_obj.a audit information and audit logging tools are protected from unauthorized access, modification, and deletion;
- au-9_obj.b {{ insert: param, au-09_odp }} are alerted upon detection of unauthorized access, modification, or deletion of audit information.

---

## AU-10: Non-repudiation
Provide irrefutable evidence that an individual (or process acting on behalf of an individual) has performed {{ insert: param, au-10_odp }}.

**Guidance:** Types of individual actions covered by non-repudiation include creating information, sending and receiving messages, and approving information. Non-repudiation protects against claims by authors of not having authored certain documents, senders of not having transmitted messages, receivers of not ha

**Related:** AU-9, PM-12, SA-8, SC-8, SC-12, SC-13, SC-16, SC-17, SC-23

---

## AU-11: Audit Record Retention
Retain audit records for {{ insert: param, au-11_odp }} to provide support for after-the-fact investigations of incidents and to meet regulatory and organizational information retention requirements.

**Guidance:** Organizations retain audit records until it is determined that the records are no longer needed for administrative, legal, audit, or other operational purposes. This includes the retention and availability of audit records relative to Freedom of Information Act (FOIA) requests, subpoenas, and law en

**Related:** AU-2, AU-4, AU-5, AU-6, AU-9, AU-14, MP-6, RA-5, SI-12

---

## AU-12: Audit Record Generation
(au-12_smt.a) Provide audit record generation capability for the event types the system is capable of auditing as defined in [AU-2a](#au-2_smt.a) on {{ insert: param, au-12_odp.01 }};
  (au-12_smt.b) Allow {{ insert: param, au-12_odp.02 }} to select the event types that are to be logged by specific components of the system; and
  (au-12_smt.c) Generate audit records for the event types defined in [AU-2c](#au-2_smt.c) that include the audit record content defined in [AU-3](#au-3).

**Guidance:** Audit records can be generated from many different system components. The event types specified in [AU-2d](#au-2_smt.d) are the event types for which audit logs are to be generated and are a subset of all event types for which the system can generate audit records.

**Related:** AC-6, AC-17, AU-2, AU-3, AU-4, AU-5, AU-6, AU-7, AU-14, CM-5, MA-4, MP-4, PM-12, SA-8, SC-18, SI-3, SI-4, SI-7, SI-10

**Assessment Objectives:**
- au-12_obj.a audit record generation capability for the event types the system is capable of auditing (defined in AU-02_ODP[01]) is provided by {{ insert: param, au-12_odp.01 }};
- au-12_obj.b {{ insert: param, au-12_odp.02 }} is/are allowed to select the event types that are to be logged by specific components of the system;
- au-12_obj.c audit records for the event types defined in AU-02_ODP[02] that include the audit record content defined in AU-03 are generated.

---

## AU-13: Monitoring for Information Disclosure
(au-13_smt.a) Monitor {{ insert: param, au-13_odp.01 }} {{ insert: param, au-13_odp.02 }} for evidence of unauthorized disclosure of organizational information; and
  (au-13_smt.b) If an information disclosure is discovered:
    (au-13_smt.b.1) Notify {{ insert: param, au-13_odp.03 }} ; and
    (au-13_smt.b.2) Take the following additional actions: {{ insert: param, au-13_odp.04 }}.

**Guidance:** Unauthorized disclosure of information is a form of data leakage. Open-source information includes social networking sites and code-sharing platforms and repositories. Examples of organizational information include personally identifiable information retained by the organization or proprietary infor

**Related:** AC-22, PE-3, PM-12, RA-5, SC-7, SI-20

**Assessment Objectives:**
- au-13_obj.a {{ insert: param, au-13_odp.01 }} is/are monitored {{ insert: param, au-13_odp.02 }} for evidence of unauthorized disclosure of organizational information;
- au-13_obj.b

---

## AU-14: Session Audit
(au-14_smt.a) Provide and implement the capability for {{ insert: param, au-14_odp.01 }} to {{ insert: param, au-14_odp.02 }} the content of a user session under {{ insert: param, au-14_odp.03 }} ; and
  (au-14_smt.b) Develop, integrate, and use session auditing activities in consultation with legal counsel and in accordance with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines.

**Guidance:** Session audits can include monitoring keystrokes, tracking websites visited, and recording information and/or file transfers. Session audit capability is implemented in addition to event logging and may involve implementation of specialized session capture technology. Organizations consider how sess

**Related:** AC-3, AC-8, AU-2, AU-3, AU-4, AU-5, AU-8, AU-9, AU-11, AU-12

**Assessment Objectives:**
- au-14_obj.a
- au-14_obj.b

---

## AU-16: Cross-organizational Audit Logging
Employ {{ insert: param, au-16_odp.01 }} for coordinating {{ insert: param, au-16_odp.02 }} among external organizations when audit information is transmitted across organizational boundaries.

**Guidance:** When organizations use systems or services of external organizations, the audit logging capability necessitates a coordinated, cross-organization approach. For example, maintaining the identity of individuals who request specific services across organizational boundaries may often be difficult, and

**Related:** AU-3, AU-6, AU-7, CA-3, PT-7
